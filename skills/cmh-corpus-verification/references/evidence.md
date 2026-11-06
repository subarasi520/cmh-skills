# Evidence: tiers, windows, abstention, the results table, instruments

## Evidence tiers

Every claim carries the tier of the evidence it rests on. Name the tiers for your study; a typical
ladder, strongest first:

| Tier | What it is | What it can support |
|---|---|---|
| `human_verified` | a person read the instance under the protocol | a value |
| `authoritative_record` | an official list, a dated dictionary entry, an archival record | a value, at its own tier |
| `model_judged_audited` | judge-layer label confirmed by the audit layer | a value, with the measured error rate of this tier |
| `model_judged` | judge-layer label only | a value, with the measured error rate of this tier |
| `rule_matched` | a string or pattern match with no reading | a baseline; usually not a value |
| `search_count_bound` | counts returned by a search interface | an upper bound or a shape only |
| `trend_only` | a frequency series | a trend, never a value |

Rules:

1. A value comes from an attested instance. A model is never asked when something happened.
2. A lower tier never overrides a higher one.
3. Each tier's error rate is measured (workflow step 7) and reported next to the claims that rest on it.
4. Reports show how many claims sit on each tier. A table whose claims mostly sit on low tiers
   should say so in its first paragraph, not in a footnote.

## Observation windows and censoring

Every source starts and ends somewhere. If the earliest attested instance sits at the start of the
window, the true first use may be earlier: report it as a bound (`censored = left`,
`value_kind = upper_bound`). Keep censored values out of distributions and averages of dates or
lags; mixing them in creates trends that are only arithmetic.

When sources cover different periods (a newspaper from one year, a web archive from a later one),
the window is per source. A comparison between units measured in different windows needs a
sentence in the report.

## Abstention

When the evidence does not support a claim, the pipeline makes none: no positive instance, too few
supporting instances, sources in conflict, a rejected anchor without a replacement. Abstentions are
a result. Report how many units have no claim and why. A baseline that always gives an answer (a
string match always finds a "first" occurrence) looks more complete and is less correct.

## One results table

- All decisions — model labels, audit decisions, human rulings, authoritative records — flow into
  one table. Every reported number is computed from it; nobody reads a number off an intermediate file.
- Manual inputs (rulings, hand-verified anchors) live in one file with one entry point. A rebuild
  script must not overwrite them from another source.
- The evidence policy is written as checks (`templates/table_checks.toml`) and run on every rebuild.
- Each rebuild is diffed against the last accepted version (`cmh_check.py diff --fail-on-change`).
  A guard that depends on a label can be bypassed when an earlier step renames the label; a diff
  shows the effect even when the cause is elsewhere.

## Provenance

Keep, for every call to a model: the layer, the model name, the parameters, the hash of the prompt
template and of the rendered prompt, the protocol lock, the raw output and the parsed label
(`cmh_judge.py` does this). Keep screening outputs too, including rejections. Funnel numbers must
be counted from these records, not from whichever result files survived.

## Instruments

Read-only views recomputed whenever the results table changes. They are defined on artefacts that
any pipeline of this kind produces, so they carry over to other studies.

| Instrument | What it shows | Computed from |
|---|---|---|
| Candidate funnel | candidates at each stage, from the scan to the final table | scan output, screening ledger, results table |
| Exclusive contribution | what each source or nomination route contributed that no other did | results table with a source column |
| Evidence fidelity | how often instance text actually contains the queried form (catches phantom hits from fuzzy search) | instances, search samples |
| Censoring guard | how many values sit at a window edge, and how many conclusions they would change | results table |
| Human–judge agreement | per language and class | blind sheets + judge labels (`cmh_agreement.py`) |
| Annotator agreement | per language and class | blind sheets (`cmh_agreement.py`) |
| Cost and scale | calls per layer and model, instances judged, human items read | ledger (`cmh_judge.py summary`), sheets |
| Issue log | every known problem, its effect on numbers, and its status | a plain file kept with the table |
