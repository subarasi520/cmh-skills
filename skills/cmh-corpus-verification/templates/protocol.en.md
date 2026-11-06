# Study protocol (template)

Fill this in before any model labels the data that the study will report. Freeze it with
`cmh_protocol.py freeze` together with the definitions, prompts, configurations and rule files,
and commit the lock. Change it afterwards only through the deviations log at the end.

## 1. Question and claim

- **Unit of analysis**: what one row of the results table is (a concept, a word form, a document, a speaker, ...).
- **Property judged per instance**: what a reader decides for each retrieved instance.
- **How judgments become a claim**: earliest attested instance / share per group / presence /
  comparison between groups / coded variable used in a statistical model.
- **The claim as one sentence**, with blanks: e.g. "Unit ___ is first attested in ___ in ___ (evidence: ___)".

## 2. Research object

- What is in scope and out of scope. Known boundary cases.
- Who rules on boundary cases, and where rulings are recorded.

## 3. Corpus layers and evidence tiers

| Layer | Source | Coverage (years, registers) | Licence / access | Can support | Tier name |
|---|---|---|---|---|---|
| e.g. full text | | | | a value from an attested instance | |
| e.g. search interface | | | | an upper bound only | |
| e.g. frequency series | | | | a trend only, never a value | |

- Tier order from strongest to weakest. A lower tier never overrides a higher one.
- Known gaps: periods or registers no source covers.

## 4. Observation window and censoring

- First and last period covered by each layer.
- A value at the window edge is reported as a bound, not as a first attestation.

## 5. Candidates and sampling frame

- Corpus nomination: scan rules and filters, fixed before looking at results.
- Closed lists used in full (which, which edition).
- Model enumeration, only where the corpus cannot nominate; everything enumerated must then be attested.
- Screening model, if any (a sieve, not a judge). All of its outputs are kept.

## 6. Retrieval

- Query rules per unit; maximum instances per unit and period; context shown; deduplication.
- Retrieval is done by code. No model is asked for dates, sources or examples.

## 7. Definitions or codebook

- Who drafts, who reviews. Only rows with status = approved are used.

## 8. Judge layer

- Model and version, backend, parameters (temperature 0), prompt file, label set, parse rule.
- What the judge does not see and why (for example the date, so that it cannot reason from when it thinks a sense appeared).

## 9. Aggregation and abstention

- The exact rule (for example: earliest instance labelled TARGET; at least N supporting instances).
- When no claim is made (abstention), and how abstentions are reported.

## 10. Triage

- Rules file. Spot-check size of unflagged claims and the seed.

## 11. Audit layer

- Model and configuration (different from the judge), what it sees, decision labels.
- What happens to rejected evidence (removed and re-aggregated, or sent to a person).

## 12. Human annotation

- **Pilot**: items, strata (language × class), two or more independent annotators, agreement by class.
- **Evaluation**: which items (outputs of every condition, deduplicated, sources hidden, shuffled), readers, majority rule.
- Independence: annotators do not see model outputs, each other's answers, or the key.
- Adjudication: who decides, how decisions are recorded.

## 13. Conditions and baselines

- Confirmatory comparisons (decided now) and exploratory ones (labelled as such when reported).
- A simple baseline (for example string matching) to show what the model layer adds.

## 14. Metrics

- Per layer: residual error, catch rate, false overturn rate, precision (Wilson intervals).
- Triage: error rate flagged vs unflagged, risk ratio.
- Agreement: κ, AC1, positive and negative specific agreement, by language and class.
- Misses: sample size drawn from the abstained/negative pool.
- Cost and scale: calls per layer and model.

## 15. Decision rules (written before any result)

- For each confirmatory comparison: what result leads to which conclusion.
- When a model layer may stand without full human review (for example: per stratum, agreement with humans at least ___).

## 16. Reporting

- Every number comes from a results file and is checked with `cmh_numbers.py`.
- Each claim is reported with its tier and the measured error rate of that tier.
- "Not significantly different" is never written as "equal".

## 17. Data handling

- Copyright and terms of use of each source; personal data; ethics approval if needed.
- What is stored where; what is never committed (corpora, answer keys, API keys).

## 18. Deviations log

| Date | Change | Reason | Results seen before the change? |
|---|---|---|---|
