---
name: cmh-corpus-verification
description: Use when language models are to label, classify, date or code instances in a text corpus for linguistics or social-science research (word senses, first attestations, loanwords, neologisms, frames, stance, topics, codebook coding) and the results must hold up to scrutiny; also when planning such a study, choosing or validating a model for it, designing blind human annotation, measuring inter-annotator or human–model agreement, or checking claims and numbers before writing up. 适用于用大语言模型对语料实例做判读、分类、定年或编码，且结论要经得起检验的语言学与社会科学研究。
license: MIT
compatibility: For any agent that reads Agent Skills (SKILL.md). The scripts need Python 3.11 or later and no third-party packages.
metadata:
  version: "1.0.0"
---

# CMH: Corpus–Model–Human verification

## Overview

**Do not trust the model. Make its work reliable by design.** CMH divides verification among
three parties. The **corpus** decides what is examined, and every claim rests on an attested
instance. **Models** read instances in layers: a judge for everything, then a differently
configured audit for what stated rules flag plus a random sample. **Humans** define the object,
approve definitions, provide blind labels that measure every layer, and rule on boundary cases.
Every result carries its evidence tier and the measured error rate of that tier. Where the
evidence is insufficient, no claim is made.

Respond in the user's language. A Chinese version of this file is `SKILL.zh-CN.md`; every
reference has a `.zh-CN.md` twin. All paths below are relative to the folder that contains this file.

## When to use

- Claims rest on reading corpus instances one by one: a sense, a category, a stance, a frame.
- A model will do most of that reading, and a trained human could apply the same written definition.
- Blind human samples can be drawn.

**Not for:** frequency, collocation or embedding statistics with no instance reading; tasks where
trained humans cannot agree (fix the definition first); facts no corpus attests; decisions about
individual people; material you may not lawfully process. Details: `references/scenarios.md`.

## Roles

| Party | Does | Never does |
|---|---|---|
| Corpus (via code) | nominates candidates; supplies dated instances | — |
| Judge model | labels every retrieved instance against an approved definition | recall dates, sources or examples |
| Audit model (configured differently) | re-reads flagged and spot-checked claims | stand unmeasured |
| Humans | define the object; approve definitions; blind labels; adjudication; sign-off | get replaced by a model as the yardstick |
| Code | retrieval, aggregation, triage, sampling, statistics, checks | compute numbers by hand |

## Workflow

Details: `references/workflow.md`. Do the steps in order. **At each checkpoint, stop and get the
researcher's sign-off before going on.**

| Step | What | Checkpoint |
|---|---|---|
| 0 | Define unit, property, claim type, observation windows | researcher signs off |
| 1 | Register corpus layers and what each can support (evidence tiers); feasibility probe | — |
| 2 | Corpus nominates candidates; models only classify (or enumerate where the corpus cannot) | all screening output kept |
| 3 | Models draft definitions; a researcher approves each | definitions approved |
| 4 | Measure humans first: blind pilot by language × class; choose the judge against it | humans agree on the classes the model will judge |
| 5 | Freeze the protocol, including decision rules | lock committed before evaluation runs |
| 6 | Judge → aggregate with abstention → stated-rule triage + random spot check → audit | — |
| 7 | Blind readers judge outputs of every condition; measure each layer and misses; researcher rules on boundaries | rulings recorded |
| 8 | One results table, checks, diffs, instruments, ablations; every number verified | all checks pass |

## Rules

1. Values come from retrieved instances. Never ask a model when something happened, or for a source or an example.
2. A model's output is a label on an instance, not a fact about the world.
3. Measure humans before models. Read every model figure against the human figure for the same language and class.
4. A person approves every definition or codebook entry before a model uses it.
5. Freeze the protocol before the evaluation run. Anything added later is reported as exploratory.
6. Triage by stated rules, never by model confidence, and always spot-check unflagged claims at random.
7. Audit with a differently configured model, and measure its false overturns as well as its catches.
8. Abstain when evidence is insufficient. "Not observed" becomes "absent" only with a measured miss rate.
9. One results table. Every reported number is computed from it and checked against it.
10. Keep every model output: rejections and unreadable replies included.

## Your part as the agent

- Build and run the pipeline. Do not stand in for the human steps. When a step needs a person
  (sign-off, approving definitions, labelling sheets, ruling on a case), prepare the material,
  say exactly what is needed, and stop.
- Never fill in blind sheets, never show annotators the key or model labels, never edit returned
  sheets. Your own labels can be one more rater column, never the yardstick.
- Report results with tiers, error rates and intervals, in plain words: what was measured, on what,
  and what was not measured.

## Red flags: stop and fix

| Thought | Reality |
|---|---|
| "The model is strong; skip the human pilot." | Without human agreement there is nothing to read the model's agreement against. |
| "High confidence, no need to check." | A model cannot flag the errors it is confident about. |
| "The model wrote the definitions; they look fine." | Every judgment inherits a wrong definition. A person approves them. |
| "Write the protocol after a quick look at results." | Then the analysis is exploratory. Freeze first. |
| "The audit is the stronger model, so its overturns are right." | Measure its false overturns on human truth. |
| "Full coverage, all tests green." | Cross-wired rows pass tests. Run foreign-key, row-count and diff checks; read a sample. |
| "Not significant, so they are equivalent." | Not significant means the data cannot tell them apart. |
| "Quick hand calculation for the report." | Numbers come from scripts and are checked with `cmh_numbers.py`. |
| "One annotator will do for now." | One annotator gives no human–human baseline. |
| "The model knows when this word appeared." | Model memory is not evidence. |

## Scripts

Standard-library Python 3.11+. Run `python scripts/<name>.py --help` for options.

| Script | Use |
|---|---|
| `cmh_protocol.py` | freeze / verify protocol files (hash lock) |
| `cmh_judge.py` | run judge or audit models with an append-only ledger; `dry-run`; `summary` |
| `cmh_aggregate.py` | instance labels → claims: `earliest`, `proportion`, `presence` (with abstention, censoring) |
| `cmh_triage.py` | stated-rule flags + seeded random spot check |
| `cmh_sheet.py` | blind sheets: `make` (key kept apart), `check`, `merge` |
| `cmh_agreement.py` | κ, AC1, positive/negative specific agreement, Fleiss κ, cluster bootstrap |
| `cmh_evaluate.py` | `triage`, `audit`, `compare`, `estimate` (proportion correction), `recall` (misses) |
| `cmh_check.py` | rule checks on the results table; `diff` against the last accepted version |
| `cmh_numbers.py` | every manuscript number traced to a results file |

Templates (protocol, prompts, configs, rules, annotator guide) are in `templates/`. A complete
offline run on synthetic data is in the repository's `examples/toy/run_example.py`.

## References

- [references/workflow.md](references/workflow.md): each step, its outputs and checkpoints
- [references/scenarios.md](references/scenarios.md): claim types (dating, proportions, presence, comparison, coded variables) and what to adapt
- [references/evidence.md](references/evidence.md): tiers, windows and censoring, abstention, the results table, instruments
- [references/human-annotation.md](references/human-annotation.md): pilot, blindness, sheets, sample sizes, adjudication
- [references/statistics.md](references/statistics.md): which measure for which question, how to word results
- [references/failure-patterns.md](references/failure-patterns.md): symptoms, checks and fixes
- [references/glossary.md](references/glossary.md): English–Chinese terms
