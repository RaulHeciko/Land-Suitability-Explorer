"""Land Suitability Index (LSI) processing pipeline."""

import os
import sys

# A system-wide PROJ_LIB/PROJ_DATA (e.g. from PostGIS or ArcGIS) points at an incompatible proj.db.
# Drop it so rasterio and pyproj fall back to the databases bundled with their wheels.
for _var in ("PROJ_LIB", "PROJ_DATA"):
    _val = os.environ.get(_var, "")
    if _val and not os.path.abspath(_val).startswith(os.path.abspath(sys.prefix)):
        del os.environ[_var]
