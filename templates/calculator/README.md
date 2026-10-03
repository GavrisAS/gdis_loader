# Calculator assets (tracked, immutable baseline)

Storage option A. Both XLSX files survive a clean clone; no external retrieval.
`SHA256SUMS.txt` uses repository-root paths; run `sha256sum -c` from root.

Version2 is a candidate pending native Excel acceptance. Capacity1000; model
weighted_geometric_active_mask. Runtime never modifies template formulas.
Archive version1 is exactly the pinned pre-structural v0.19 calculator, capacity100.
Do not regenerate or modify archive. Choose it in the same loader for rollback.

Version/hash metadata: docs/CALCULATOR_TEMPLATE_VERSION.toml.
