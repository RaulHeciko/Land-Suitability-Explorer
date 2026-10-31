#!/usr/bin/env sh
# Stamp src/lsi_explorer/_build_info.py with the current git commit before `poetry build`.
# Restore the placeholder afterwards: git checkout -- src/lsi_explorer/_build_info.py
set -eu

cd "$(dirname "$0")/.."
commit=$(git rev-parse HEAD)
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then dirty=True; else dirty=False; fi

cat > src/lsi_explorer/_build_info.py <<EOF
"""Build provenance stamped by scripts/stamp-build-info.sh at build time.

Never commit non-None values: the stamp script restores this placeholder after the build.
"""

COMMIT = "$commit"
DIRTY = $dirty
EOF
echo "stamped $commit (dirty=$dirty)"
