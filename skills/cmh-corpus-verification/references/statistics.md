# Statistics used by the scripts

All functions are in `scripts/cmh_stats.py`, standard library only, each with its formula in the
docstring so results can be checked by hand.

| Question | Measure | Script |
|---|---|---|
| How uncertain is this rate? | Wilson score interval | everywhere |
| Do people (or a person and a model) agree, and on which class? | Cohen's κ, Gwet's AC1, positive / negative specific agreement, Fleiss' κ for 3+ raters | `cmh_agreement.py` |
| Is the interval robust to items from the same unit being correlated? | cluster bootstrap (resample units, not items) | `cmh_agreement.py --cluster --bootstrap` |
| Does triage concentrate errors? | error rate flagged vs unflagged, risk ratio with Katz interval, Fisher exact test, label-noise check | `cmh_evaluate.py triage` |
| Is one audit configuration better than another on the same claims? | McNemar test on the discordant pairs (exact and continuity-corrected) | `cmh_evaluate.py audit` |
| Do two conditions leave different residual error? | Fisher exact test | `cmh_evaluate.py compare` |
| What is the share once the model's error is accounted for? | difference estimator (prediction-powered style), Rogan–Gladen correction | `cmh_evaluate.py estimate` |
| How much did we miss? | true-positive share in a random sample of negatives, scaled to the pool | `cmh_evaluate.py recall` |

## Notes on reading the numbers

- **Kappa depends on prevalence.** With one class rare, kappa can be low while raters agree on
  almost every item. Report AC1 and the class-specific agreements next to it, and the class shares.
- **Class-specific agreement says where the problem is.** High positive and low negative agreement
  means people agree on clear instances and disagree on hard negatives (parts of other words,
  homographs, borderline senses).
- **Paired designs need paired tests.** Two audits run on the same claims are compared with
  McNemar, not with two independent proportions.
- **The label-noise check** flips a share of truth labels at random many times and recomputes the
  risk ratio. If a small flip rate (larger than the disagreement you observed between readers)
  leaves the ratio well above 1, the triage result does not hinge on a few contested labels.
- **Correcting a proportion** needs a simple random gold sample from the same population (or from
  each group). The difference estimator subtracts the model's average error measured on the gold
  sample; its interval combines both sources of variance. Rogan–Gladen uses sensitivity and
  specificity from the gold sample and is undefined when sensitivity + specificity ≤ 1.
- **Several comparisons** inflate the chance of a spurious "significant" result. Decide the
  confirmatory comparisons in the protocol; report the rest as exploratory.

## How to write results

- Give counts with rates: "12 of 150 (8.0%, 95% CI 4.6–13.5%)" rather than "about 8%".
- A p-value above the threshold means the data cannot tell the conditions apart. Write "not
  significantly different", never "equal", "the same" or "matches".
- Do not place rates with different denominators side by side as if they were comparable
  (precision is computed over overturns, a false-overturn rate over valid claims).
- Every number in the manuscript is checked against the results files with `cmh_numbers.py`.

## References

- Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement*.
- Fleiss, J. L. (1971). Measuring nominal scale agreement among many raters. *Psychological Bulletin*.
- Gwet, K. L. (2008). Computing inter-rater reliability and its variance in the presence of high agreement. *British Journal of Mathematical and Statistical Psychology*.
- Cicchetti, D. V., & Feinstein, A. R. (1990). High agreement but low kappa: II. Resolving the paradoxes. *Journal of Clinical Epidemiology*.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *Journal of the American Statistical Association*.
- McNemar, Q. (1947). Note on the sampling error of the difference between correlated proportions or percentages. *Psychometrika*.
- Katz, D., Baptista, J., Azen, S. P., & Pike, M. C. (1978). Obtaining confidence intervals for the risk ratio in cohort studies. *Biometrics*.
- Rogan, W. J., & Gladen, B. (1978). Estimating prevalence from the results of a screening test. *American Journal of Epidemiology*.
- Artstein, R., & Poesio, M. (2008). Inter-coder agreement for computational linguistics. *Computational Linguistics*.
- Angelopoulos, A. N., Bates, S., Fannjiang, C., Jordan, M. I., & Zrnic, T. (2023). Prediction-powered inference. *Science*.
- Egami, N., Hinck, M., Stewart, B. M., & Wei, H. (2023). Using imperfect surrogates for downstream inference: Design-based supervised learning for social science applications of large language models. *Advances in Neural Information Processing Systems*.
