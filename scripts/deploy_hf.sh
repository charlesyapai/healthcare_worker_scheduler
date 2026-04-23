#!/usr/bin/env bash
# Deploy the current `react-ui` HEAD to the HF Space with docs/ stripped.
#
# The GitHub repo is canonical and keeps the full docs/ tree. The HF
# Space is public-facing and should only ship what the running app
# actually needs. We reconcile the two by maintaining a local
# `hf-deploy` branch that mirrors `react-ui` minus `docs/`, then
# force-pushing that branch onto HF's `main`.
#
# Usage:
#   ./scripts/deploy_hf.sh              # deploys react-ui
#   ./scripts/deploy_hf.sh <branch>     # deploys a custom branch
#
# Requires:
#   - `.hf_access_token` in repo root (gitignored; token has write on
#     the HF Space — see memory hf_token_usage.md).
#   - `hf_v2` remote configured (no credentials baked in).
#
# After pushing, this script polls the HF runtime API until the Space
# reports RUNNING so you know the rebuild is live.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SOURCE_BRANCH="${1:-react-ui}"
HF_SPACE="charlesyapai/healthcare_workforce_scheduler_v2"
HF_REMOTE_URL_BASE="https://huggingface.co/spaces/${HF_SPACE}"

if [[ ! -f .hf_access_token ]]; then
  echo "FATAL: .hf_access_token not found at repo root" >&2
  exit 1
fi
TOKEN=$(tr -d '[:space:]' < .hf_access_token)

# Remember where we were so we can return the user's checkout to it.
ORIGINAL_BRANCH=$(git symbolic-ref --short HEAD)

# Fail fast if there are uncommitted changes — deploying a half-edited
# tree is a common foot-gun.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "FATAL: working tree has uncommitted changes; commit or stash first" >&2
  exit 1
fi

# Resolve the source commit for a clearer audit trail in the squash msg.
SOURCE_SHA=$(git rev-parse --short "$SOURCE_BRANCH")
echo "[deploy_hf] source: $SOURCE_BRANCH @ $SOURCE_SHA"

# Rebuild hf-deploy from scratch — one commit per deploy keeps HF's
# history focused on what is actually running.
git checkout -B hf-deploy "$SOURCE_BRANCH" >/dev/null
if [[ -d docs ]]; then
  git rm -r docs >/dev/null
  git commit -m "Deploy ${SOURCE_SHA} to HF (docs stripped — canonical in GitHub)" >/dev/null
  echo "[deploy_hf] stripped docs/ and committed"
else
  echo "[deploy_hf] no docs/ to strip; pushing source as-is"
fi

# Force-push hf-deploy → main on the HF remote. Force is required
# because HF's prior history includes commits we don't reproduce
# locally (manual deletions, prior deploys). The canonical history
# lives on GitHub; HF's history is disposable.
PUSH_URL="https://charlesyapai:${TOKEN}@huggingface.co/spaces/${HF_SPACE}"
git push "$PUSH_URL" hf-deploy:main --force 2>&1 | sed "s|${TOKEN}|<REDACTED>|g"

# Return to whatever branch the caller started on.
git checkout "$ORIGINAL_BRANCH" >/dev/null
echo "[deploy_hf] returned to $ORIGINAL_BRANCH"

echo "[deploy_hf] polling runtime until RUNNING…"
while true; do
  STAGE=$(curl -s -H "Authorization: Bearer $TOKEN" \
    "https://huggingface.co/api/spaces/${HF_SPACE}" \
    | python -c "import json,sys;print(json.load(sys.stdin).get('runtime',{}).get('stage',''))")
  if [[ "$STAGE" == "RUNNING" ]]; then
    echo "[deploy_hf] READY: $STAGE"
    break
  fi
  echo "[deploy_hf] still $STAGE"
  sleep 15
done
