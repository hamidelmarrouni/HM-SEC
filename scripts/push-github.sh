#!/usr/bin/env bash
# Run this yourself after creating an EMPTY public HM-SEC repository on GitHub.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
owner="${1:-hamidelmarrouni}"
[[ "$owner" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] || { echo 'Pass a valid GitHub username.' >&2; exit 1; }
remote="git@github.com:${owner}/HM-SEC.git"
[[ "$(git branch --show-current)" == main ]] || { echo 'Switch to your prepared main branch first.' >&2; exit 1; }
git rev-parse --verify HEAD >/dev/null
[[ -z "$(git status --porcelain)" ]] || { echo 'Review and commit local changes before uploading.' >&2; exit 1; }
if git remote get-url origin >/dev/null 2>&1; then
  [[ "$(git remote get-url origin)" == "$remote" ]] || { echo 'origin points elsewhere; inspect git remote -v before changing it.' >&2; exit 1; }
else
  git remote add origin "$remote"
fi
# SSH performs authentication. Never force-push or overwrite remote history.
git push -u origin main
