# Corrective v2 diff (v0.20 → v0.21)

Previous candidate SHA256: 8d3a21c237f2af250053664752d55edc0ef7f8ef79a6f3abe7930fabfca8e8d6.

Changed entries: `xl/worksheets/sheet2.xml`, `xl/styles.xml`.
Unexpected OOXML changes: **0**. No added or removed entries.
Formula sheets4/5/6, tables3/4, charts, workbook and all other parts are byte-identical.
Explicit general inputs B5:B11,B16 use cloned unlocked styles.
All cells in retired rows28/34 locked; rows stay hidden.
Visual style attributes preserved; no yellow-fill inference.

cellXfs: 101 → 106. New clones:101 (B5/B6/B10),102 (B7/B8/B9/B11),
103 (B16),104/105 (retired styles10/11 locked). Existing style protection
attributes normalized at indices5,10,22,23; no visual attributes changed.
