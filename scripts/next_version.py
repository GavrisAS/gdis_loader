#!/usr/bin/env python3
"""CLI wrapper for the project release-version calculator."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root / "src"))
    from gdis_loader.versioning import main as version_main

    return version_main()


if __name__ == "__main__":
    raise SystemExit(main())
