# Exact runtime ZIP evidence — corrective v0.21

```json
{
  "structural_v2": {
    "template_sha256": "645a3e5ba9303c42f441598e71fb7da261c9738789638cb5a0e7fceaf97d2578",
    "source_sha256": "bb046cc365749a546d1bbe141165b08a664ba427ab9493b678ddce008fc85c6a",
    "capacity": 1000,
    "calculation_date": "2026-10-02",
    "validation_errors": 0,
    "fields": {
      "Береговое": {
        "rows": 78,
        "errors": 0,
        "changed_entries": [
          "xl/worksheets/sheet3.xml",
          "xl/tables/table2.xml"
        ],
        "formula_cells": 146537,
        "customer_examples": "PASS",
        "non_target_byte_identity": "PASS",
        "capacity_warning": false,
        "stale_migration_message": false
      },
      "Пырейное": {
        "rows": 5,
        "errors": 0,
        "changed_entries": [
          "xl/worksheets/sheet3.xml",
          "xl/tables/table2.xml"
        ],
        "formula_cells": 146537,
        "customer_examples": "PASS",
        "non_target_byte_identity": "PASS",
        "capacity_warning": false,
        "stale_migration_message": false
      },
      "Хадырьяхинское": {
        "rows": 10,
        "errors": 0,
        "changed_entries": [
          "xl/worksheets/sheet3.xml",
          "xl/tables/table2.xml"
        ],
        "formula_cells": 146537,
        "customer_examples": "PASS",
        "non_target_byte_identity": "PASS",
        "capacity_warning": false,
        "stale_migration_message": false
      }
    }
  },
  "rollback": {
    "template_sha256": "bb046cc365749a546d1bbe141165b08a664ba427ab9493b678ddce008fc85c6a",
    "source_sha256": "bb046cc365749a546d1bbe141165b08a664ba427ab9493b678ddce008fc85c6a",
    "capacity": 100,
    "calculation_date": "2026-10-02",
    "validation_errors": 0,
    "fields": {
      "Береговое": {
        "rows": 78,
        "errors": 0,
        "changed_entries": [
          "xl/worksheets/sheet3.xml",
          "xl/tables/table2.xml"
        ],
        "formula_cells": 12802,
        "customer_examples": "PASS",
        "non_target_byte_identity": "PASS",
        "capacity_warning": false,
        "stale_migration_message": false
      },
      "Пырейное": {
        "rows": 5,
        "errors": 0,
        "changed_entries": [
          "xl/worksheets/sheet3.xml",
          "xl/tables/table2.xml"
        ],
        "formula_cells": 12802,
        "customer_examples": "PASS",
        "non_target_byte_identity": "PASS",
        "capacity_warning": false,
        "stale_migration_message": false
      },
      "Хадырьяхинское": {
        "rows": 10,
        "errors": 0,
        "changed_entries": [
          "xl/worksheets/sheet3.xml",
          "xl/tables/table2.xml"
        ],
        "formula_cells": 12802,
        "customer_examples": "PASS",
        "non_target_byte_identity": "PASS",
        "capacity_warning": false,
        "stale_migration_message": false
      }
    }
  }
}
```

All three fields on both templates: only xl/worksheets/sheet3.xml and
xl/tables/table2.xml changed. Runtime styles, settings, formulas, charts and
workbook remain byte-identical. Native Excel opening/recalc is PENDING.
