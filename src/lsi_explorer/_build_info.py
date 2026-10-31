"""Build provenance stamped by scripts/stamp-build-info.sh at build time.

Never commit non-None values: the stamp script restores this placeholder after the build.
"""

COMMIT = None
DIRTY = None
