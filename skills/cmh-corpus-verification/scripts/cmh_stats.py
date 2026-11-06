"""Small, dependency-free statistics used by the CMH scripts.

CMH 用到的统计函数：比例区间、风险比、精确检验、一致度系数、自助法、比例校正。

Every function is pure and documented with its formula so results can be
checked by hand. References are listed in references/statistics.md.
"""

from __future__ import annotations

import math
from collections import Counter
from statistics import NormalDist
from typing import Callable, Hashable, Sequence

NAN = float("nan")


def z_value(confidence: float = 0.95) -> float:
    return NormalDist().inv_cdf(0.5 + confidence / 2)


def is_nan(value: float) -> bool:
    return isinstance(value, float) and value != value


# --------------------------------------------------------------------------
# Proportions and two-group comparisons
# --------------------------------------------------------------------------

def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (Wilson 1927)."""
    if n <= 0:
        return (NAN, NAN)
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    z = z_value(confidence)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    low = 0.0 if successes == 0 else max(0.0, centre - half)
    high = 1.0 if successes == n else min(1.0, centre + half)
    return (low, high)


def proportion(successes: int, n: int, confidence: float = 0.95) -> dict:
    low, high = wilson_interval(successes, n, confidence)
    return {"k": successes, "n": n, "rate": successes / n if n else NAN, "ci_low": low, "ci_high": high}


def risk_ratio(a: int, n1: int, c: int, n2: int, confidence: float = 0.95) -> dict:
    """Risk ratio (a/n1)/(c/n2) with the Katz log interval (Katz et al. 1978).

    If a cell is zero, 0.5 is added to every cell (Haldane-Anscombe) and the
    result is marked `corrected`.
    """
    if n1 <= 0 or n2 <= 0:
        return {"rr": NAN, "ci_low": NAN, "ci_high": NAN, "corrected": False}
    corrected = a == 0 or c == 0
    if corrected:
        a, c, n1, n2 = a + 0.5, c + 0.5, n1 + 1, n2 + 1
    rr = (a / n1) / (c / n2)
    se = math.sqrt(1 / a - 1 / n1 + 1 / c - 1 / n2)
    z = z_value(confidence)
    return {"rr": rr, "ci_low": math.exp(math.log(rr) - z * se),
            "ci_high": math.exp(math.log(rr) + z * se), "corrected": corrected}


def _hypergeom_pmf(x: int, row1: int, col1: int, total: int) -> float:
    return math.comb(col1, x) * math.comb(total - col1, row1 - x) / math.comb(total, row1)


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test for the 2x2 table [[a, b], [c, d]].

    The p-value sums the probabilities of all tables with the same margins that
    are no more likely than the observed one.
    """
    row1, col1, total = a + b, a + c, a + b + c + d
    if total == 0:
        return 1.0
    observed = _hypergeom_pmf(a, row1, col1, total)
    low, high = max(0, row1 + col1 - total), min(row1, col1)
    p = sum(prob for x in range(low, high + 1)
            if (prob := _hypergeom_pmf(x, row1, col1, total)) <= observed * (1 + 1e-7))
    return min(1.0, p)


def mcnemar(b: int, c: int) -> dict:
    """McNemar test for paired binary outcomes, from the discordant counts.

    b: pairs where only the first condition succeeded; c: only the second.
    Returns the exact two-sided binomial p-value and the continuity-corrected
    chi-square statistic with its p-value (McNemar 1947).
    """
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "p_exact": 1.0, "chi2_cc": 0.0, "p_chi2_cc": 1.0}
    k = min(b, c)
    p_exact = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    chi2 = (abs(b - c) - 1) ** 2 / n if abs(b - c) > 1 else 0.0
    return {"b": b, "c": c, "p_exact": p_exact, "chi2_cc": chi2,
            "p_chi2_cc": math.erfc(math.sqrt(chi2 / 2))}


# --------------------------------------------------------------------------
# Agreement between raters
# --------------------------------------------------------------------------

def cohen_kappa(labels_a: Sequence[Hashable], labels_b: Sequence[Hashable]) -> float:
    """Cohen's kappa (Cohen 1960): (po - pe) / (1 - pe)."""
    n = len(labels_a)
    if n == 0 or n != len(labels_b):
        return NAN
    po = sum(x == y for x, y in zip(labels_a, labels_b)) / n
    count_a, count_b = Counter(labels_a), Counter(labels_b)
    pe = sum(count_a[k] * count_b[k] for k in set(count_a) | set(count_b)) / (n * n)
    if pe >= 1:
        return NAN
    return (po - pe) / (1 - pe)


def gwet_ac1(labels_a: Sequence[Hashable], labels_b: Sequence[Hashable], categories: Sequence[Hashable]) -> float:
    """Gwet's AC1 for two raters (Gwet 2008).

    pe = sum_k pi_k (1 - pi_k) / (q - 1), where pi_k is the mean share of
    category k across both raters and q is the number of categories. AC1 is
    less sensitive than kappa to very unbalanced categories.
    """
    n = len(labels_a)
    q = len(categories)
    if n == 0 or n != len(labels_b) or q < 2:
        return NAN
    po = sum(x == y for x, y in zip(labels_a, labels_b)) / n
    count = Counter(labels_a) + Counter(labels_b)
    pe = sum((count[k] / (2 * n)) * (1 - count[k] / (2 * n)) for k in categories) / (q - 1)
    if pe >= 1:
        return NAN
    return (po - pe) / (1 - pe)


def specific_agreement(labels_a: Sequence[Hashable], labels_b: Sequence[Hashable], positive: Hashable) -> dict:
    """Positive and negative specific agreement (Cicchetti & Feinstein 1990).

    With a = both positive, d = both negative, b + c = disagreements:
    p_pos = 2a / (2a + b + c), p_neg = 2d / (2d + b + c).
    Any label other than `positive` counts as negative.
    """
    a = sum(x == positive and y == positive for x, y in zip(labels_a, labels_b))
    d = sum(x != positive and y != positive for x, y in zip(labels_a, labels_b))
    disagree = len(labels_a) - a - d
    p_pos = 2 * a / (2 * a + disagree) if (2 * a + disagree) else NAN
    p_neg = 2 * d / (2 * d + disagree) if (2 * d + disagree) else NAN
    return {"both_positive": a, "both_negative": d, "disagree": disagree, "p_pos": p_pos, "p_neg": p_neg}


def fleiss_kappa(ratings: Sequence[Sequence[Hashable]]) -> float:
    """Fleiss' kappa (Fleiss 1971) for items that all have the same number of ratings."""
    if not ratings:
        return NAN
    m = len(ratings[0])
    if m < 2 or any(len(item) != m for item in ratings):
        return NAN
    n_items = len(ratings)
    categories = sorted({label for item in ratings for label in item}, key=str)
    totals = Counter()
    p_items = []
    for item in ratings:
        counts = Counter(item)
        totals.update(counts)
        p_items.append((sum(v * v for v in counts.values()) - m) / (m * (m - 1)))
    p_bar = sum(p_items) / n_items
    pe = sum((totals[k] / (n_items * m)) ** 2 for k in categories)
    if pe >= 1:
        return NAN
    return (p_bar - pe) / (1 - pe)


# --------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------

def cluster_bootstrap(
    clusters: dict[Hashable, list],
    statistic: Callable[[list], float],
    replicates: int,
    rng,
    confidence: float = 0.95,
) -> dict:
    """Percentile bootstrap that resamples whole clusters with replacement.

    `clusters` maps a cluster id (for example a unit or a document) to its
    items. Resampling clusters rather than items keeps correlated items
    together, which matters when one unit contributes many sentences.
    Replicates where the statistic is undefined are dropped and counted.
    """
    keys = sorted(clusters, key=str)
    if not keys or replicates <= 0:
        return {"ci_low": NAN, "ci_high": NAN, "replicates": 0, "undefined": 0}
    values = []
    undefined = 0
    for _ in range(replicates):
        sample = []
        for _ in keys:
            sample.extend(clusters[keys[rng.randrange(len(keys))]])
        value = statistic(sample)
        if is_nan(value):
            undefined += 1
        else:
            values.append(value)
    if not values:
        return {"ci_low": NAN, "ci_high": NAN, "replicates": 0, "undefined": undefined}
    values.sort()
    alpha = (1 - confidence) / 2
    return {"ci_low": percentile(values, alpha), "ci_high": percentile(values, 1 - alpha),
            "replicates": len(values), "undefined": undefined}


def percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile of an already sorted list."""
    if not sorted_values:
        return NAN
    position = q * (len(sorted_values) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[low]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


# --------------------------------------------------------------------------
# Correcting a model-based proportion with a human-labelled random sample
# --------------------------------------------------------------------------

def difference_estimate(model_all: Sequence[int], model_gold: Sequence[int], human_gold: Sequence[int],
                        confidence: float = 0.95) -> dict:
    """Difference estimator for a proportion (model-assisted estimation).

    theta = mean(model labels on all N items) - mean(model - human on the n gold
    items). The gold items must be a simple random sample of the same
    population. This is the estimator used by prediction-powered inference for
    a mean. Normal-approximation interval:
    var = var(model_all) / N + var(model_gold - human_gold) / n.
    """
    big_n, n = len(model_all), len(human_gold)
    if big_n < 2 or n < 2 or n != len(model_gold):
        return {"estimate": NAN, "ci_low": NAN, "ci_high": NAN, "naive": NAN}
    naive = sum(model_all) / big_n
    diffs = [m - h for m, h in zip(model_gold, human_gold)]
    rectifier = sum(diffs) / n
    var_all = sum((x - naive) ** 2 for x in model_all) / (big_n - 1)
    mean_diff = rectifier
    var_diff = sum((x - mean_diff) ** 2 for x in diffs) / (n - 1)
    estimate = naive - rectifier
    half = z_value(confidence) * math.sqrt(var_all / big_n + var_diff / n)
    return {"estimate": estimate, "ci_low": estimate - half, "ci_high": estimate + half,
            "naive": naive, "rectifier": rectifier, "N": big_n, "n_gold": n}


def rogan_gladen(observed_share: float, sensitivity: float, specificity: float) -> float:
    """Prevalence corrected for classifier error (Rogan & Gladen 1978).

    (observed + specificity - 1) / (sensitivity + specificity - 1), clipped to
    [0, 1]. Undefined when sensitivity + specificity <= 1.
    """
    denom = sensitivity + specificity - 1
    if denom <= 0 or is_nan(denom):
        return NAN
    return min(1.0, max(0.0, (observed_share + specificity - 1) / denom))
