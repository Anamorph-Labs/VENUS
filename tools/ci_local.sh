#!/usr/bin/env bash
# Run what GitHub's "Community checks" run, before any push. Every step must pass.
#   tools/ci_local.sh            security scans + tests + test render on a clean install
# The clean install has only what `pip install .` brings (no cut-out models, no extras),
# exactly like the test machine. Gitleaks runs only if docker is here (CI runs it always).
# Semgrep needs its rule packs from semgrep.dev; where that is blocked it says so plainly and
# the script ends "NOT the same as the test machine" -- then open a pull request to main and
# wait for its checks before main or community move (they run there exactly as on a push).
set -euo pipefail
cd "$(dirname "$0")/.."
ok() { printf '  ok  %s\n' "$1"; }

echo "1. Security scans"
bandit -r alvenus tools -ll -q 2>/dev/null; ok bandit
SAME=yes
if curl -sf -o /dev/null -m 10 https://semgrep.dev/c/p/python; then
  semgrep scan --config p/python --config p/secrets --config p/github-actions --error --metrics off -q; ok semgrep
else
  echo "  !!  semgrep could not download its rules here (semgrep.dev is blocked)"; SAME=no
fi
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.21.2 detect --source /repo --redact -v; ok gitleaks
else
  echo "  !!  gitleaks skipped (no docker here)"; SAME=no
fi
pip-audit -r requirements.txt; ok pip-audit

echo "2. Clean install (only Venus's own dependencies)"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
git ls-files -z | xargs -0 -I{} cp --parents {} "$T/" 2>/dev/null || true
python3 -m venv "$T/venv"
"$T/venv/bin/pip" install -q "$T" >/dev/null
ok "pip install ."
cd "$T"
PATH="$T/venv/bin:$PATH"
export VENUS_HOME="$T/home"

echo "3. Every test"
python -m unittest discover -s tests 2>&1 | tail -3

echo "4. Add-ons load and the test render"
alvenus suggest --addons >/dev/null; ok "add-ons load"
cp tools/ci-storyboard.json "$T/sb.json"
alvenus approve "$T/sb.json" --by "the test machine (a test render only)" >/dev/null
alvenus make "$T/sb.json" --draft --no-fix --out "$T/base.mp4" >/dev/null
for f in alvenus/addons/styles/*.json; do
  [ -e "$f" ] || continue
  n=$(basename "$f" .json)
  alvenus make "$T/sb.json" --draft --no-fix --style "$n" --out "$T/$n.mp4" >/dev/null
done
ok "test render"
if [ "$SAME" = yes ]; then echo "All checks passed: same as the test machine."
else echo "Everything that could run here passed, but this is NOT the same as the test machine:"
     echo "open a pull request to main and wait for its checks before moving main or community."; fi
