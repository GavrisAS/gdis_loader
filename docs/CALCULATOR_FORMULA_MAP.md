# Formula model — structural v2

The exact original cell formulas and every migrated formula are preserved in
local `artifacts/calculator/audit-pre.json` and `formula-map.json`.
Region mappings and explanations: [structural diff](CALCULATOR_STRUCTURAL_DIFF.md).

Let the enabled retained criteria be i, original weight wᵢ, transformed value μᵢ.
The default retained weights are .20, .14, .12, .12, .12, .10, .10, .05
(settings rows21:27 and29), total .95. Optional retained criteria stay disabled.

Old (including ADD if enabled):

```text
nᵢ = ISNUMBER(μᵢ)
H = Σ nᵢ wᵢ
λold = exp(Σ nᵢ wᵢ ln(μᵢ) / H)
```

λold is blank when the well is absent, H=0, or ANY criterion reports missing
input, missing field or invalid configuration. Default ADD enabled with missing
input therefore blocked all scoring. CaseA compares the retained subset, with
ADD disabled in the old model; it does not claim equality with ADD included.

New:

```text
activeᵢ = 1 when enabled, required raw inputs are present/valid,
            and the criterion's μ is numeric; otherwise0
μunknown = 0
w_effectiveᵢ = activeᵢ wᵢ
Hnew = Σ activeᵢ wᵢ
λnew = exp(Σ activeᵢ wᵢ ln(max(minimum_μ, μᵢ)) / Hnew)
```

If the well is absent or Hnew=0, λ is blank. Configuration errors remain explicit
and block calculation; they are not silently converted to missing data.
Known raw0 is valid. Known `Нет` gives default μ=.1, active=1; `Да` gives μ=1,
active=1. Unknown gives μ=0, active=0. Only numeric required inputs enter sigmoid;
blank, nonnumeric and unresolved-derived blanks bypass sigmoid.

No individual remaining weight is rewritten. Division by participating weight
sum preserves normalized weighted geometric aggregation. Equal criterion
quality gives the same λ with1,6 or10 participating criteria. Fewer observations
can still change the estimate when quality differs; coverage stays visible in
Расчет/Рейтинг and is not an extra score multiplier.

## Sorting and empty results

Existing numeric rank remains count of strictly greater scores plus running tie
count: descending λ, ties in source order. Auxiliary O keeps numeric ranks and
assigns unknown rows successive ordering keys after all numeric λ. Rating M
matches this key; displayed rank stays blank for unknown rows. Empty unused
capacity has empty keys and does not become rank1. The chart retains its
final-score TOP-N data source, not criterion series.

## Recalculation

Changed formulas have no stale value caches. Automatic full recalculation is
forced and calcChain is removed with its relationship/content type. Existing
unmodified caches, including chart caches, are not acceptance evidence. No Excel
engine is available in this environment. Tests evaluate emitted μ, mask, λ and
ordering-key formula subsets with controlled expected values, plus structural
OOXML and runtime identity checks. This is not an Excel-rendering test.
