# GDIS Loader v0.24

Обновление источника дебита на сентябрьский суточный рапорт и исправление
сопоставления по месторождению.

The debit input now uses `09.2026 Cуточный рапорт БГП.xlsm`, sheet `Добыча телеметрия`. The reader derives field scope from dated daily-sheet links, checks well identity and lifecycle, and limits the source period to September 2026. It leaves unsupported or conflicting rows blank with source-coordinate diagnostics. Arithmetic mean, positive working-day rule, and the default threshold remain unchanged.

The production audit resolved the September field ambiguity from dated source-row evidence. Candidate rows with a proven different field are rejected by the matching contract. Three Beregovoe rows remain blank because their selected September rows contain no positive working-day values. The structural v3 calculator remains a non-canonical candidate pending native Excel acceptance.

The standalone Windows x64 build requires no installed Python. This release includes its SHA-256 file and a source-and-test review bundle. No production workbooks are included.
