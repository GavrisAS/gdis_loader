#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$ROOT"

timestamp=$(date '+%Y%m%d_%H%M%S')
short_sha=$(git rev-parse --short HEAD 2>/dev/null || printf '%s' 'nogit')
audit_dir="$ROOT/audit"
output="$audit_dir/gdis_loader_audit_${timestamp}_${short_sha}.tar.xz"
stage=$(mktemp -d "${TMPDIR:-/tmp}/gdis-loader-audit.XXXXXX")
trap 'rm -rf "$stage"' EXIT

mkdir -p "$audit_dir" "$stage/.github/workflows"

copy_path() {
    if [ -e "$ROOT/$1" ]; then
        cp -a "$ROOT/$1" "$stage/$1"
    fi
}

for file in \
    AGENTS.md README.md Makefile pyproject.toml uv.lock .python-version \
    .editorconfig .gitignore .gitattributes config.example.toml; do
    copy_path "$file"
done

for directory in src tests docs scripts prompts .github/workflows; do
    if [ -d "$ROOT/$directory" ]; then
        mkdir -p "$stage/$directory"
        cp -a "$ROOT/$directory/." "$stage/$directory/"
    fi
done

if [ -f "$ROOT/data/README.md" ]; then
    mkdir -p "$stage/data"
    cp -a "$ROOT/data/README.md" "$stage/data/README.md"
fi

find "$stage" -type d \( \
    -name .git -o -name .venv -o -name __pycache__ -o -name .pytest_cache -o \
    -name .ruff_cache -o -name .ty_cache -o -name build -o -name dist -o -name audit \) \
    -prune -exec rm -rf -- {} +

branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || printf '%s' 'DETACHED')
head_sha=$(git rev-parse HEAD 2>/dev/null || printf '%s' 'unavailable')
{
    printf 'Local timestamp: %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'UTC timestamp: %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    printf 'Branch: %s\n' "$branch"
    printf 'HEAD: %s\n' "$head_sha"
    printf 'System Python: '
    python --version 2>&1 || true
    printf 'Project Python (uv): '
    if command -v uv >/dev/null 2>&1; then
        uv run python --version 2>&1 || true
    else
        printf '%s\n' 'unavailable (uv is not installed)'
    fi
    printf 'uv: '
    uv --version 2>&1 || true
    printf '%s\n' 'Production data policy: real files under data/ are intentionally excluded; only data/README.md is bundled.'
} > "$stage/AUDIT_INFO.txt"

git status --short --branch --untracked-files=all > "$stage/GIT_STATUS.txt"
git diff --binary -- . ':(exclude)data' > "$stage/GIT_DIFF.patch"
git diff --cached --binary -- . ':(exclude)data' > "$stage/GIT_DIFF_CACHED.patch"
git log --oneline --decorate -20 > "$stage/GIT_LOG.txt"

if find "$stage" -type f \( \
    -path '*/data/*' ! -name 'README.md' -o \
    -name 'config.toml' -o -name '*.xlsx' -o -name '*.xlsm' -o -name '*.xls' -o \
    -name '*.csv' -o -name '*.json' -o -name '*.log' -o -name '*.pyc' -o -name '*.spec' -o \
    -path '*/build/*' -o -path '*/dist/*' -o -path '*/audit/*' -o \
    -path '*/.git/*' -o -path '*/.venv/*' -o -path '*/__pycache__/*' \) \
    -print -quit | grep -q .; then
    printf '%s\n' 'Audit bundle contains a forbidden generated or production-data file.' >&2
    exit 1
fi

tar -cJf "$output" -C "$stage" .
if tar -tJf "$output" | grep -E '(^|/)(\.git|\.venv|build|dist|audit)(/|$)|(^|/)data/.*\.(xlsx|xlsm|xls|csv|json)$|(^|/)config\.toml$|(^|/).*\.pyc$|(^|/).*__pycache__(/|$)' >/dev/null; then
    printf '%s\n' 'Audit archive self-check failed: forbidden path found.' >&2
    exit 1
fi

printf '%s\n' "$output"
