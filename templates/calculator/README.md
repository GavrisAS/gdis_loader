# Calculator assets (tracked, immutable baseline)

Delivery option B: both templates, SHA256SUMS.txt and CALCULATOR_TEMPLATE_VERSION.toml
are separate GitHub Release assets alongside the Windows loader ZIP (v0.21).
Both XLSX files also survive a clean clone.
`SHA256SUMS.txt` uses repository-root paths; run `sha256sum -c` from root.

Version2 is a candidate pending native Excel acceptance. Capacity1000; model
weighted_geometric_active_mask. Runtime never modifies template formulas.
Archive version1 is exactly the pinned pre-structural v0.19 calculator, capacity100.
Do not regenerate or modify archive. Choose it in the same loader for rollback.

Version/hash metadata: docs/CALCULATOR_TEMPLATE_VERSION.toml.

Windows: download both XLSX assets into any folder, compare `Get-FileHash
-Algorithm SHA256 <filename>` with SHA256SUMS.txt, then select the required
calculator through Обзор in the loader. The checksum file uses repository-root
paths; match downloaded assets by basename. No Python is needed on Windows.
