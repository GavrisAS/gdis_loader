#!/usr/bin/env bash
set -euo pipefail

repo_name="${1:-gdis_loader}"

command -v gh >/dev/null || {
  echo "gh CLI не найден" >&2
  exit 1
}

gh auth status

if [[ ! -d .git ]]; then
  git init -b main
fi

git add .
if ! git diff --cached --quiet; then
  git commit -m "chore: initialize gdis_loader project"
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  gh repo create "$repo_name" --private --source=. --remote=origin --push
else
  git push -u origin main
fi
