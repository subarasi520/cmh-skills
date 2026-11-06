# Scenarios: what changes with the claim type

CMH applies when a claim is built from instance-by-instance reading of a corpus: code retrieves
instances, someone decides for each instance whether it has a property, and the decisions are
aggregated into a claim. **How they are aggregated decides which error hurts the claim most**, and
so where the audit and the human samples should go.

## The five claim types

| Claim type | Linguistics examples | Social-science examples | The error that hurts most | What to adapt |
|---|---|---|---|---|
| **Earliest instance** (dating) | first attestation of a loanword or a new sense; antedating dictionary citations | the first appearance of a policy term or slogan in parliament or the press | a single false positive moves the date earlier | audit every anchor that triage flags plus a random share of the rest; isolated early hits are a triage rule |
| **Share per group** (proportion, trend) | share of an old vs a new sense per decade; spread of a construction | framing or stance shares per year; topic shares in speeches | one class judged wrong systematically (random errors average out, bias does not) | measure agreement per class; correct estimates with a human-labelled random sample; stratify spot checks by period |
| **Presence / absence** | "this sense is not attested before year X" | "this topic is not raised in period P" | misses (false negatives) | never report "absent" without a miss rate from a random sample of the negative pool |
| **Comparison between groups** | sense distribution across registers; translation equivalents in a parallel corpus | how two outlets or two parliaments frame the same event | different judging quality in the two groups creates a fake difference | measure human–model agreement separately in each group (each language, each outlet) |
| **Coded variable in a statistical model** | — | model-coded variables used in regression or correlation | measurement error carried into coefficients | correct with a human-labelled sample (difference / prediction-powered style estimators); report sensitivity |

## Defaults per claim type

**Earliest instance.** `cmh_aggregate.py earliest` with `--window-start`. Triage rules: short or
ambiguous forms, window edge, isolated early anchor, single supporting instance. Do not show the
date to the judge: it should decide the sense from the passage, not from when it believes the sense
appeared. Report window-edge values as bounds. Errors cut both ways: a false positive makes the date
too early, a missed true instance in the years before the anchor makes it too late. Draw part of the
miss sample (`cmh_evaluate.py recall`) from the negatives in those earlier years.

**Share per group.** `cmh_aggregate.py proportion`. Decide in the protocol whether uncertain labels
are excluded or counted as negative. Draw the human gold sample at random within each group and
correct each group's share (`cmh_evaluate.py estimate`). A trend in uncorrected model shares can be
an artefact of the model's error rate changing across periods (older spelling, different genres).

**Presence / absence.** `cmh_aggregate.py presence` reports `not_observed`, never `absent`. Sample
the negative pool at random, have it labelled, and report the miss rate (`cmh_evaluate.py recall`).

**Comparison.** Run the pilot (workflow step 4) in every group. If the judge is good in one group
and weak in the other, the comparison measures the judge, not the groups. Use the stronger
configuration for the weaker group, or correct each group separately.

**Coded variable in a model.** Treat model codes as measurements with error. Keep a random
human-coded subsample large enough to estimate the error per category and to correct the
estimates you report. Report the uncorrected and corrected results side by side.

## Where it does not apply

- **Claims that never require reading instances**: raw frequencies, collocation strength, word
  embeddings, topic models used descriptively. Standard methods are enough; there is nothing for
  the human yardstick to measure.
- **Tasks where trained humans cannot agree**: there is no yardstick. Rework the definition first,
  or study the disagreement itself.
- **Facts that are not in any corpus**: a model's memory is not evidence. If no source attests it,
  the claim cannot be made at a tier above "not attested".
- **Decisions about individual people** (clinical, legal, hiring, moderation, surveillance): out of
  scope. The workflow measures aggregate error rates; it does not make any single decision safe.
- **Material you may not process**: copyright, terms of use, personal data and ethics approval come
  first. The workflow does not make processing lawful.
- **No human time at all**: CMH needs blind human labels, though far fewer than reading everything.
