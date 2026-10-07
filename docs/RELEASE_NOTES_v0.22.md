# GDIS Loader v0.22

Current plast comes from the newest valid Summary GDI inside the confirmed current
well history. Stale Fund/Base plast cannot override that choice. Lifecycle boundaries,
ЗБС ordinal, ПВЛГ/ПНЛГ inheritance and separate ГС/МЗС identities remain mandatory.
Equal latest dates with different plasts fail safely; missing Summary evidence uses
the diagnosed conservative Fund/Base fallback.

GDM problems use the newest finite Delta in that same current history/plast, searching
past blank, dash and invalid newer rows. Any selected Delta must be at most 730 elapsed
days old relative to calculation date (inclusive; 731 rejected); future rows are excluded.
Delta values are never subtracted. Zero and negative values remain valid. AutoFilter and
hidden state do not remove historical rows. Criteria UI shows the age in days. Existing
explicit config values are retained; missing age settings default to 730.

Structured plast provenance and grouped GDM rejection reasons explain the selection.
Validation coverage and count reconciliation use the same resolver as update.

Structural calculator v2 and rollback are byte-identical to v0.21. Template version,
capacity, formulas, protection and automatic recalculation are unchanged. Native Excel
acceptance was already confirmed by the user. No calcChain is added.

The release version is injected by the existing Windows release workflow; the source/dev
fallback remains 0.1. The workflow creates v0.22 on the exact successfully built commit,
without a version-bump commit. Review evidence is supplied in the v0.22 audit bundle.
