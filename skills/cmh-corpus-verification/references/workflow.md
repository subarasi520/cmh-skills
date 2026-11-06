# CMH workflow, step by step

Each step lists what it produces, who does it, and the checkpoint that must be passed before the
next step. **H** = a researcher or annotator, **M** = a model, **C** = code (the scripts or your own).

Do the steps in this order. Most failures in model-assisted corpus work come from doing them out
of order: running the models first and adding definitions, human baselines and rules afterwards.

## Step 0. Define the research object and the claim (H)

Write down:

- the **unit** (one row of the final table): a concept, a word form, a document, a speaker;
- the **property** a reader judges for each instance (a sense, a category, a stance, a frame);
- the **claim type**: how instance judgments become a claim (earliest attested instance, share
  per group, presence, comparison, coded variable in a model). See `scenarios.md`;
- the **observation window** of every source, and what a value at the edge of a window means.

Output: sections 1–4 of `templates/protocol.en.md`.
Checkpoint: the researcher signs off. Nothing below can repair a vague research object.

## Step 1. Register the corpus layers and the evidence tiers (H, C)

For every source, record what it can support:

- full text with dates → an instance-level value (a year, a share);
- a search interface that returns counts → an upper bound or a shape, never a value on its own;
- a frequency series → a trend, never a value;
- an authoritative record (an official list, a dictionary entry with a date) → a value at its own tier.

Order the tiers from strongest to weakest. A lower tier never overrides a higher one. Write down
the known gaps (periods or registers no source covers) — they become limits in the report.

Run a feasibility probe of a day or two: can you retrieve instances for a handful of units from
every layer, with dates, under the source's terms of use?

Output: section 3 of the protocol; `evidence.md` explains the tier ladder.

## Step 2. Let the corpus nominate the candidates (C, M as a sieve)

- Scan the corpus (all word forms in a period, all documents matching a frame) or take a closed,
  enumerable list in full. Fix the scan rules and filters before looking at results.
- A model may **classify** candidates (is this a real unit? which type?). It is a sieve: keep every
  one of its outputs, including rejections, with the call log.
- A model may **enumerate** candidates only where the corpus cannot nominate them (for example
  forms that have no precedent in the scanned corpus). Everything it proposes must then be
  attested in the corpus like any other candidate.
- Give every unit a stable id. Ids are never reused or renumbered.

Record the funnel: how many candidates at each stage, from the logs rather than from whichever
files happen to remain.

## Step 3. Write the definitions and have a person review them (M drafts, H approves)

Every downstream judgment depends on the definition (or codebook entry). A model may draft them;
a researcher reads and approves each one and sets `status = approved` in the definitions table.
`cmh_judge.py` refuses to run on definitions that are not approved.

There are far fewer definitions than instances. Human time spent here has the highest return.

## Step 4. Measure humans first (H, C)

Before choosing or trusting any model configuration:

1. Draw a pilot sample stratified by the classes that matter (language × positive/negative, or
   codebook category), with class shares close to what the deployment will see.
2. Make blind sheets (`cmh_sheet.py make`), two or more annotators label them independently.
3. Compute agreement **by class** (`cmh_agreement.py`: κ, AC1, positive and negative specific agreement).
4. Classes where humans do not agree: fix the definition, or keep them away from the model layer.
   Do not "solve" human disagreement by letting a model decide.
5. Run candidate model configurations on the same sheet (they are just more rater columns) and
   choose the judge per language and class against the human figures.

Output: the human baseline every later number is read against. `human-annotation.md` has the details.

## Step 5. Freeze the protocol (H, C)

Fill the rest of the protocol: retrieval rules, judge configuration, aggregation and abstention
rules, triage rules, audit configuration, spot-check size and seed, conditions and baselines,
metrics, and the **decision rules** that say what each possible result will mean.

Freeze every protocol file (`cmh_protocol.py freeze`) and commit the lock before the first
evaluation run. The commit time is the evidence that the rules came first. Analyses added
afterwards are reported as exploratory.

## Step 6. Layered verification (C, M)

1. **Retrieve** instances with code: per unit and period, capped, with context, deduplicated.
2. **Judge layer** (`cmh_judge.py run --layer judge`): one call per instance, temperature 0, every
   call appended to the ledger. A cheap local model is often enough here; the measured error rate
   decides, not the price.
3. **Aggregate with abstention** (`cmh_aggregate.py`): the claim points at its evidence instance.
   No supporting instance → no claim. Values at a window edge are marked as censored.
4. **Triage by stated rules** (`cmh_triage.py`): short or ambiguous forms, window-edge values,
   isolated early hits, single supporting instances, conflicting sources. Draw a seeded random
   spot check of the unflagged claims. Model confidence never removes a claim from the spot check.
5. **Audit layer** (`cmh_judge.py run --layer audit`): a differently configured model re-reads the
   evidence of every flagged and spot-checked claim. Rejected evidence is removed and the claim
   re-aggregated, or sent to a person, as the protocol says.

## Step 7. Humans measure every layer and rule on definitions (H, C)

1. Collect the evidence instances produced by **every** condition (judge alone, judge + audit,
   baselines), deduplicate, hide the sources, shuffle, and give them to two or three readers who
   did not build the pipeline (`cmh_sheet.py make`).
2. Check returned sheets (`cmh_sheet.py check`), unblind (`cmh_sheet.py merge`), take the majority.
3. Measure (`cmh_evaluate.py`): does triage concentrate errors (`triage`); what did the audit
   catch and what did it break (`audit`); how do conditions compare (`compare`).
4. Measure **misses**: draw a random sample from the abstained and negative pool and have it
   labelled (`cmh_evaluate.py recall`). Without this, "not found" cannot be reported as "absent".
5. For proportions, correct the model-based estimate with a human-labelled random sample
   (`cmh_evaluate.py estimate`).
6. Disagreements that turn on what counts as the research object go to the researcher, who rules
   and records the ruling. These rulings define the object; they are not noise.

## Step 8. One results table, checks, instruments, report (C, H)

- All decisions flow into one results table. Every reported number is computed from it.
- Write the evidence policy as checks (`cmh_check.py run`) and run them every time the table is
  rebuilt. Diff each rebuild against the last accepted version (`cmh_check.py diff`) so that a
  change nobody intended is seen.
- Recompute the instruments (`evidence.md`, section "Instruments") whenever the table changes.
- Ablate: remove one layer at a time, rebuild, and report what changes.
- Report every claim with its tier and the measured error rate of that tier. Check every number
  in the manuscript against the results files (`cmh_numbers.py check`), then read the sentences
  around them: a matching number does not make a sentence true.
