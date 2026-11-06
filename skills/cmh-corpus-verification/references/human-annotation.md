# Human annotation: the yardstick

People do three things in CMH that no model layer can do for them:

1. **Provide the yardstick**: independent, blind labels against which every layer is measured.
2. **Rule on the research object**: decide the cases that turn on what counts as the object.
3. **Review definitions** before any model uses them.

## Who annotates

- At least two annotators for the pilot; two or three readers for the evaluation set.
- Readers for the evaluation set should not have built the pipeline or seen its outputs.
- Record what is known about annotators' background (language competence, training) without
  storing personal data you do not need.

## Independence and blindness

- Sheets show only the passage, the expression and the definition. Never the model label, the
  source condition, the date if the task is dating, or another annotator's answer.
  `cmh_sheet.py make` refuses to show columns whose names suggest an answer or a source.
- The key that maps sheet items to sources lives in a separate folder, outside version control.
- Each annotator gets the items in their own random order.
- No discussion until all sheets are back. No AI tools, search engines or dictionaries while judging.
- A sheet that went out with answers on it cannot be used for the yardstick, and neither can that
  annotator for the same items. Make a new sheet for a new annotator.

## Sheet hygiene

Before any sheet goes out:

- Check the composition: `--require lang=xx` refuses items from the wrong language;
  `--summarize column` prints the distribution of strata.
- Deduplicate items shown by several conditions (they are shown once and mapped back by the key).
- Formulas: cells a spreadsheet could execute are escaped.

When sheets come back: `cmh_sheet.py check` against the blank — same ids, unchanged text, valid
labels — then `merge`.

## Pilot design

- Stratify by what matters: language, expected class (target / other), codebook category, period.
- Match the class shares of the deployment, or report both. Agreement coefficients depend on
  prevalence: a kappa computed on a sample that is 85% positive is not comparable to one on a
  sample that is 30% positive.
- Report agreement by class: positive specific agreement and negative specific agreement show
  *where* people disagree. Hard negatives (an expression that is part of another word, a
  homograph) are often where humans and models both fail.

## How many items

There is no universal number. Choose the size from the interval you need. A few reference points
for a Wilson 95% interval:

| Observed rate | n = 50 | n = 100 | n = 200 | n = 400 |
|---|---|---|---|---|
| 4% | 1.1%–13.5% | 1.6%–9.8% | 2.0%–7.7% | 2.5%–6.4% |
| 10% | 4.3%–21.4% | 5.5%–17.4% | 6.6%–14.9% | 7.4%–13.3% |
| 30% | 19.1%–43.8% | 21.9%–39.6% | 24.1%–36.7% | 25.7%–34.7% |

Compute your own with `cmh_stats.wilson_interval`. Per-stratum intervals need per-stratum sizes.

## Measuring every layer

- The evaluation set contains the outputs of **every** condition, not only the deployed one, so
  that layers and baselines are compared on the same truth.
- Majority vote over readers; items without a majority are excluded and counted.
- Check that conclusions hold if any single reader is taken as the truth. If they do not, say so.
- Measure misses separately: a random sample from abstentions and negatives.

## Adjudication

Some disagreements are not errors: they show that the definition does not settle a case (does a
metaphorical or ironic use count as the target sense?). The researcher rules, writes the
ruling down with an example, and the definition is amended through the deviations log. Rulings
apply to all similar items, not only the one that raised the question.
