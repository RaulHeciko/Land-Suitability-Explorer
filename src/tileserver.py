"""Local XYZ tile server rendering the LSI rasters at their native 100 m resolution.

Each registered layer is kept in memory as a uint8 colour-index array on the source grid plus a
2x-reduced pyramid (block means for continuous data, nearest for classes) used at low zoom, so the
browser always receives full-detail 256x256 PNG tiles in Web Mercator instead of one resampled image.

Endpoints (CORS enabled):
  /tile/<layer>/<region>/<z>/<x>/<y>.png
  /value/<region>?lat=..&lon=..&layers=k1,k2   -> JSON list of {label, text}, read from the source files
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from pyproj import Transformer

from .preprocessing import clean_categorical, clean_continuous
from .raster_ops import Grid, read_aligned
from .utils import (
    CHANGE_CLASSES,
    CLASS_COLORS,
    CLASS_RANGES,
    DRIVER_NODATA,
    DRIVERS,
    change_class,
    hex_to_rgb,
)

NODATA = 255
MAX_LEVEL = 6  # pyramid down to 1/64
TILE = 256
WEB_MERC_RES0 = 2 * math.pi * 6378137 / TILE


# ------------------------------------------------------------------ palettes


def _lut_continuous(cmap_name: str, fn) -> np.ndarray:
    lut = np.zeros((256, 4), np.uint8)
    cmap = colormaps[cmap_name]
    for i in range(251):
        lut[i] = (np.array(cmap(fn(i))) * 255).astype(np.uint8)
        lut[i, 3] = 255
    return lut


def _lut_classes(colors: dict[int, tuple]) -> np.ndarray:
    lut = np.zeros((256, 4), np.uint8)
    for k, rgb in colors.items():
        lut[k] = (*rgb, 255)
    return lut


LUTS = {
    "score": _lut_continuous("RdYlGn", lambda i: i / 250),
    "delta": _lut_classes({k: hex_to_rgb(c) for k, (_, c) in CHANGE_CLASSES.items()}),
    "classes": _lut_classes(
        {c: hex_to_rgb(h) for c, h in zip(range(1, 11), CLASS_COLORS)}
    ),
    "driver": _lut_classes({k: hex_to_rgb(v[2]) for k, v in DRIVERS.items()}),
}


def lut(kind: str) -> np.ndarray:
    return LUTS[kind]


def encode(values: np.ndarray, kind: str) -> np.ndarray:
    """Physical values -> uint8 colour index (255 = NoData)."""
    if kind == "score":
        with np.errstate(invalid="ignore"):
            idx = np.clip(np.rint(values * 2.5), 0, 250)
        return np.where(np.isfinite(idx), idx, NODATA).astype(np.uint8)
    if kind == "delta":  # 5 change classes
        out = change_class(values)
        out[out == 0] = NODATA
        return out
    out = values.astype(np.uint8, copy=True)
    if kind == "classes":
        out[out == 0] = NODATA
    return out


def _block_mean(a: np.ndarray) -> np.ndarray:
    h, w = a.shape
    a = np.pad(a, ((0, h % 2), (0, w % 2)), constant_values=np.nan)
    b = a.reshape(a.shape[0] // 2, 2, a.shape[1] // 2, 2)
    with np.errstate(invalid="ignore"):
        valid = np.isfinite(b)
        s = np.where(valid, b, 0).sum(axis=(1, 3))
        n = valid.sum(axis=(1, 3))
        return np.where(n >= 2, s / np.maximum(n, 1), np.nan).astype(np.float32)


def build_pyramid(values: np.ndarray, kind: str) -> list[np.ndarray]:
    levels = [encode(values, kind)]
    if kind in ("score", "delta"):
        cur = values
        for _ in range(MAX_LEVEL):
            cur = _block_mean(cur)
            levels.append(encode(cur, kind))
    else:
        for i in range(1, MAX_LEVEL + 1):
            levels.append(levels[0][:: 2**i, :: 2**i])
    return levels


# ------------------------------------------------------------------ registry


@dataclass
class Layer:
    label: str
    kind: str  # score | delta | classes | driver
    paths: tuple[Path, ...]  # (path,) or (present, future) for delta
    grid: Grid
    pyramid: list[np.ndarray] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def nbytes(self) -> int:
        return sum(p.nbytes for p in self.pyramid)


@dataclass
class Region:
    r0: int
    c0: int
    mask: np.ndarray | None  # bool, window-sized; None = whole grid
    shape: tuple[int, int]


class Registry:
    def __init__(self, budget_bytes: int = 900_000_000):
        self.layers: OrderedDict[str, Layer] = OrderedDict()
        self.regions: dict[str, Region] = {"all": Region(0, 0, None, (0, 0))}
        self.budget = budget_bytes
        self.lock = threading.Lock()

    def add_layer(
        self, label: str, kind: str, paths: tuple[Path, ...], grid: Grid
    ) -> str:
        key = hashlib.md5(
            f"{kind}|{'|'.join(map(str, paths))}|"
            f"{[p.stat().st_mtime for p in paths]}".encode()
        ).hexdigest()[:12]
        with self.lock:
            if key in self.layers:
                self.layers.move_to_end(key)
                return key
        with self.lock:
            self.layers[key] = Layer(label, kind, paths, grid)
        return key

    def ensure_built(self, layer: Layer) -> None:
        """Build the colour-index pyramid on first use (tiles of different layers build in parallel)."""
        if layer.pyramid:
            return
        with layer.lock:
            if not layer.pyramid:
                layer.pyramid = build_pyramid(self._load(layer), layer.kind)
        with self.lock:
            built = [k for k, l in self.layers.items() if l.pyramid]
            while (
                sum(self.layers[k].nbytes for k in built) > self.budget
                and len(built) > 8
            ):
                old = self.layers[built.pop(0)]
                if old is not layer:
                    old.pyramid = []

    @staticmethod
    def _load(layer: Layer) -> np.ndarray:
        g = layer.grid
        if layer.kind == "score":
            return clean_continuous(read_aligned(layer.paths[0], g))
        if layer.kind == "delta":
            return clean_continuous(read_aligned(layer.paths[1], g)) - clean_continuous(
                read_aligned(layer.paths[0], g)
            )
        if layer.kind == "classes":
            return clean_categorical(read_aligned(layer.paths[0], g))
        a = read_aligned(layer.paths[0], g)
        return np.where(np.isfinite(a) & (a >= 0) & (a <= 8), a, DRIVER_NODATA).astype(
            np.uint8
        )

    def add_region(self, key: str, r0: int, c0: int, mask: np.ndarray) -> str:
        with self.lock:
            self.regions[key] = Region(r0, c0, mask, mask.shape)
            if len(self.regions) > 30:
                self.regions.pop(next(k for k in self.regions if k != "all"))
        return key


REGISTRY = Registry()
_local = threading.local()


def _transformer(src: str, dst) -> Transformer:
    cache = getattr(_local, "tr", None)
    if cache is None:
        cache = _local.tr = {}
    k = (src, str(dst))
    if k not in cache:
        cache[k] = Transformer.from_crs(src, dst, always_xy=True)
    return cache[k]


def _inside_region(
    region: Region, rows: np.ndarray, cols: np.ndarray, ok: np.ndarray
) -> np.ndarray:
    if region.mask is None:
        return ok
    rr, cc = rows - region.r0, cols - region.c0
    inside = (
        ok & (rr >= 0) & (cc >= 0) & (rr < region.shape[0]) & (cc < region.shape[1])
    )
    res = np.zeros_like(ok)
    res[inside] = region.mask[rr[inside], cc[inside]]
    return res


def render_tile(layer: Layer, region: Region, z: int, x: int, y: int) -> bytes | None:
    REGISTRY.ensure_built(layer)
    g = layer.grid
    res = WEB_MERC_RES0 / 2**z
    x0 = -math.pi * 6378137 + x * TILE * res
    y0 = math.pi * 6378137 - y * TILE * res
    centers = (np.arange(TILE) + 0.5) * res
    mx, my = np.meshgrid(x0 + centers, y0 - centers)
    gx, gy = _transformer("EPSG:3857", g.crs).transform(mx, my)
    t = g.transform
    cols = np.floor((gx - t.c) / t.a).astype(np.int64)
    rows = np.floor((gy - t.f) / t.e).astype(np.int64)
    ok = (rows >= 0) & (cols >= 0) & (rows < g.height) & (cols < g.width)
    ok = _inside_region(region, rows, cols, ok)
    if not ok.any():
        return None
    # ground size of a tile pixel (Mercator scale factor at the tile centre) vs native pixel size
    lat = math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / 2**z)))
    ratio = res * math.cos(lat) / abs(t.a)
    level = int(
        np.clip(math.floor(math.log2(max(ratio, 1))), 0, len(layer.pyramid) - 1)
    )
    arr = layer.pyramid[level]
    f = 2**level
    idx = np.full((TILE, TILE), NODATA, np.uint8)
    idx[ok] = arr[
        np.minimum(rows[ok] // f, arr.shape[0] - 1),
        np.minimum(cols[ok] // f, arr.shape[1] - 1),
    ]
    rgba = lut(layer.kind)[idx]
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=False, compress_level=3)
    return buf.getvalue()


def _read_pixel(path: Path, row: int, col: int) -> float:
    with rasterio.open(path) as src:
        v = float(src.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])
        if src.nodata is not None and v == src.nodata:
            return float("nan")
    return v


def point_values(
    keys: list[str], region_key: str, lat: float, lon: float
) -> list[dict]:
    out = []
    for k in keys:
        layer = REGISTRY.layers.get(k)
        if layer is None:
            continue
        g = layer.grid
        gx, gy = _transformer("EPSG:4326", g.crs).transform(lon, lat)
        col = int((gx - g.transform.c) // g.transform.a)
        row = int((gy - g.transform.f) // g.transform.e)
        ok = 0 <= row < g.height and 0 <= col < g.width
        region = REGISTRY.regions.get(region_key, REGISTRY.regions["all"])
        if ok:
            ok = bool(
                _inside_region(
                    region, np.array([row]), np.array([col]), np.array([True])
                )[0]
            )
        text = "-"
        if ok:
            if layer.kind == "score":
                v = clean_continuous(
                    np.array([_read_pixel(layer.paths[0], row, col)], "f4")
                )[0]
                text = f"{v:.1f}" if np.isfinite(v) else "-"
            elif layer.kind == "delta":
                a, b = (
                    clean_continuous(np.array([_read_pixel(p, row, col)], "f4"))[0]
                    for p in layer.paths
                )
                text = (
                    f"{b - a:+.1f} ({CHANGE_CLASSES[int(change_class(b - a))][0]})"
                    if np.isfinite(a) and np.isfinite(b)
                    else "-"
                )
            elif layer.kind == "classes":
                c = int(
                    clean_categorical(
                        np.array([_read_pixel(layer.paths[0], row, col)], "f4")
                    )[0]
                )
                text = f"C{c} ({CLASS_RANGES[c]})" if c else "-"
            else:
                v = _read_pixel(layer.paths[0], row, col)
                text = DRIVERS[int(v)][0] if np.isfinite(v) and 0 <= v <= 8 else "-"
        out.append({"label": layer.label, "text": text})
    return out


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Cache-Control",
            "max-age=3600" if code == 200 and ctype == "image/png" else "no-store",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            u = urlparse(self.path)
            parts = u.path.strip("/").split("/")
            if parts[0] == "tile" and len(parts) == 6:
                _, lk, rk, z, x, y = parts
                layer = REGISTRY.layers.get(lk)
                region = REGISTRY.regions.get(rk)
                png = (
                    render_tile(layer, region, int(z), int(x), int(y.split(".")[0]))
                    if layer and region
                    else None
                )
                if png is None:
                    return self._send(204, b"", "image/png")
                return self._send(200, png, "image/png")
            if parts[0] == "value" and len(parts) == 2:
                q = parse_qs(u.query)
                vals = point_values(
                    q.get("layers", [""])[0].split(","),
                    parts[1],
                    float(q["lat"][0]),
                    float(q["lon"][0]),
                )
                return self._send(200, json.dumps(vals).encode(), "application/json")
            self._send(404, b"", "text/plain")
        except ConnectionError:  # browser cancelled the request (panning / zooming)
            pass
        except Exception as e:  # keep the server alive
            try:
                self._send(500, str(e).encode(), "text/plain")
            except ConnectionError:
                pass


_server: ThreadingHTTPServer | None = None


def start(port: int | None = None) -> int:
    """Start (once) the tile server in a daemon thread; returns its port (env LSI_TILE_PORT, else free)."""
    global _server
    if _server is None:
        port = int(os.environ.get("LSI_TILE_PORT", 0)) if port is None else port
        _server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        _server.daemon_threads = True
        threading.Thread(target=_server.serve_forever, daemon=True).start()
    return _server.server_address[1]


def public_url(port: int) -> str:
    """Base URL under which the browser reaches the tile server.

    LSI_TILE_BASE_URL (may contain {port}) wins; on JupyterHub (EOCube.Ro) the server is reached through
    jupyter-server-proxy at <JUPYTERHUB_SERVICE_PREFIX>proxy/<port>; locally at http://127.0.0.1:<port>.
    """
    base = os.environ.get("LSI_TILE_BASE_URL")
    if base:
        return base.format(port=port).rstrip("/")
    prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX")
    if prefix:
        return f"{prefix.rstrip('/')}/proxy/{port}"
    return f"http://127.0.0.1:{port}"
