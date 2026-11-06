# Failure patterns and how to catch them

Patterns that recur when models are used to read corpora. Each one comes with a symptom, a check,
and the part of the workflow that prevents it.

## Evidence

| Pattern | Symptom | Check / prevention |
|---|---|---|
| **Model memory used as evidence** | dates, sources or example sentences that no retrieved instance supports | values only from retrieved instances; the judge never sees the date; `implies` check "claimed → evidence id not empty"; `foreign_key` to the instance table |
| **Substring matches counted as evidence** | the form occurs inside longer words or names (a short form inside a compound; a string that crosses a word boundary after segmentation) | instance-level judging; "part of a longer word → OTHER" in the prompt and the guide; triage rule on short forms |
| **Phantom hits from fuzzy search** | a search interface returns a count, but the sample text does not contain the form | literal check on samples ("evidence fidelity" instrument); search counts only as bounds; default to *fail* when no sample can be checked |
| **Window edge read as a first appearance** | many values at the first year of a source; apparent trends in lags that are arithmetic | `--window-start` → censored; window-edge values as bounds; keep them out of date or lag distributions |
| **A baseline that always answers** | a string match "dates" every unit, including those with no real instance | report abstentions as results; compare against the judge on the same truth |

## Candidates

| Pattern | Symptom | Check / prevention |
|---|---|---|
| **Coverage capped by enumeration** | the candidate list is what a model or a person happened to recall; a model asked for more items keeps returning variants of ones it already gave | corpus nomination and closed lists first; enumeration only where the corpus cannot nominate |
| **Screening outputs not kept** | funnel numbers that cannot be reproduced from the records; a stage whose output files were overwritten or never saved | keep every screening output and call log; count the funnel from logs |
| **Fragments admitted as units** | half-words or truncated phrases in the final table | screening labels fragments; a check on unit length or pattern; human review of definitions |

## Models

| Pattern | Symptom | Check / prevention |
|---|---|---|
| **Configuration chosen on one slice** | the judge was validated on one language or one class and deployed on all | pilot by language × class before choosing; pick per stratum |
| **Confidence used as a stopping rule** | high-confidence claims skip review; confident errors are never seen | triage by stated rules; random spot check of unflagged claims regardless of confidence |
| **Self-audit only** | the same model checks its own output and agrees with itself | audit with a differently configured model; measure the audit's precision as well as its catches |
| **A strong audit trusted blindly** | the audit overturns many valid claims | measure false overturns on human truth; report precision with the catch rate |
| **Prompt drift** | labels in one table come from several prompt versions | ledger summary shows prompt versions per layer; protocol lock blocks runs after edits |
| **Unreadable replies treated as answers** | free-text replies parsed loosely into labels | strict label matching; unparsed replies counted and reported, not guessed |

## People

| Pattern | Symptom | Check / prevention |
|---|---|---|
| **Definitions written by a model and never reviewed** | readers confirm "matches the given definition" while the definition itself is wrong | definitions need `status = approved`; `cmh_judge.py` refuses others |
| **One annotator** | no human–human agreement, so human–model numbers have no reference | two or more annotators from the pilot on |
| **Sheets that leak** | a sheet went out with model answers or source labels | `cmh_sheet.py` refuses risky columns; key in a separate folder |
| **Mixed sheets** | a sheet for one language contains items in another | `--require lang=xx` and `--summarize` before any sheet goes out |
| **Disagreement treated as noise** | boundary cases resolved by majority without anyone deciding what the object is | adjudication by the researcher, recorded, applied to all similar items |

## Process and reporting

| Pattern | Symptom | Check / prevention |
|---|---|---|
| **"All green" deliverables** | an automated run reports full coverage and passing tests, while rows are cross-wired between units | `foreign_key`, `row_count` and `implies` checks; diffs against the last accepted table; read a sample by hand |
| **Rules after results** | the protocol is written, or changed, after looking at outcomes | freeze and commit the lock before evaluation runs; deviations log |
| **Wrong denominators** | "k of n" where n counts something else than the text says | denominators computed by the scripts; state what n counts |
| **Non-random spot checks** | the "random" check came from one batch | seeded sampling over all unflagged claims, sorted before sampling |
| **Manual inputs overwritten** | a rebuild silently replaces hand-entered rulings | one entry point for manual inputs; `cmh_check.py diff --fail-on-change` |
| **Guards bypassed upstream** | a guard keyed on a label stops working after an earlier step renames the label | checks on outcomes (`implies`), not only on labels; diffs |
| **Hand-computed numbers** | numbers in the text that no script produces; rounding done twice | numbers only from scripts; `cmh_numbers.py check`, including the scan for unregistered numbers |
| **"Not significant" written as "equal"** | a non-significant difference reported as parity | `cmh_evaluate.py compare` prints the reminder; review the wording |
| **Different denominators side by side** | precision placed next to a false-overturn rate as if comparable | name the denominator of every rate |
| **Fabricated or unread citations** | a reference that does not exist, or does not say what it is cited for | cite only what you have read in full; check every reference against its source |
