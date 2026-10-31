"""Localization helper and build provenance."""

import re

import pytest
import yaml

from lsi_explorer import _build_info, i18n
from lsi_explorer.version import format_version_string


def _keys(node, prefix=""):
    if isinstance(node, dict):
        return {k for key, v in node.items() for k in _keys(v, f"{prefix}{key}.")}
    return {prefix.rstrip(".")}


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"EOCUBE_LANG": "ro"}, "ro"),
        ({"LC_ALL": "ro_RO.UTF-8"}, "ro"),
        ({"LC_ALL": "C", "LANG": "ro_RO"}, "ro"),
        ({"LANG": "en_US.UTF-8"}, "en"),
    ],
)
def test_detection_order(monkeypatch, env, expected):
    for var in ("EOCUBE_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    assert i18n.detect_language() == expected


def test_lookup_interpolation_and_fallbacks():
    i18n.set_language("ro")
    assert i18n.t("app.tabs.map") == "Hart\u0103"
    assert i18n.t("app.region.judet", name="Alba") == "Jude\u021bul Alba"
    i18n.set_language("xx")  # unknown language -> English
    assert i18n.t("app.tabs.map") == "Map"
    assert i18n.t("no.such.key") == "no.such.key"


def test_locales_have_the_same_keys():
    cat = {
        lang: _keys(
            yaml.safe_load((i18n.LOCALES_DIR / f"{lang}.yml").read_text("utf-8"))[lang]
        )
        for lang in i18n.available_languages()
    }
    assert set(cat) == {"en", "ro"}
    assert cat["en"] == cat["ro"]


def test_version_string():
    assert re.match(
        r"^lsi-explorer \S+(, commit [0-9a-f]{12} \((clean|dirty)\))?$",
        format_version_string(),
    )


def test_build_info_placeholder_is_never_committed_stamped():
    assert _build_info.COMMIT is None and _build_info.DIRTY is None


def test_placeholder_named_like_a_parameter():
    assert i18n.t("cli.written", path="out.json") == "Written: out.json"


def test_crop_names_follow_the_language():
    from lsi_explorer.utils import crop_label

    assert crop_label("GR") == "Wheat (GR)"
    i18n.set_language("ro")
    assert crop_label("PB") == "Porumb (PB)"


def test_language_override_is_thread_local():
    import threading

    i18n.set_language("ro")
    seen = {}
    worker = threading.Thread(target=lambda: seen.update(lang=i18n.get_language()))
    worker.start()
    worker.join()
    assert i18n.get_language() == "ro"
    assert seen["lang"] == i18n.detect_language() or seen["lang"] == "en"
