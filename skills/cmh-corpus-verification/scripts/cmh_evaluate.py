#!/usr/bin/env python3
"""Measure each layer against human ground truth.

用人的盲判真值测量每一层：分流是否把错误集中起来、审计捉到多少错又误推翻多少、
两种配置的剩余错误率、用人工随机样本校正模型给出的比例、估计漏报。

  triage    error rate of flagged vs unflagged claims, risk ratio, label-noise check
  audit     per audit configuration: caught, missed, false overturns, precision;
            McNemar between configurations on the same claims
  compare   residual error of two conditions (Fisher exact test)
  estimate  correct a model-labelled proportion with a human-labelled random sample
  recall    misses: share of true positives among sampled negatives or abstentions

Every rate comes with a Wilson 95% interval. A difference that is not
significant is reported as "not significantly different", never as "equal".
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmh_common import (  # noqa: E402
    CMHError, make_rng, manifest, parse_bool, read_table, require_columns, run_cli, split_list, write_json,
)
from cmh_stats import (  # noqa: E402
    NAN, difference_estimate, fisher_exact, is_nan, mcnemar, percentile, proportion, risk_ratio, rogan_gladen,
    wilson_interval,
)

NOT_EQUAL_NOTE = ("A p-value above the threshold means the data cannot tell the conditions apart; "
                  "it does not show that they are equal.")


def pct(value: float) -> str:
    return "–" if is_nan(value) else f"{100 * value:.1f}%"


def rate_text(stats: dict) -> str:
    return f"{stats['k']}/{stats['n']} = {pct(stats['rate'])} [{pct(stats['ci_low'])}, {pct(stats['ci_high'])}]"


def truth_value(row: dict[str, str], column: str, valid_values: set[str], invalid_values: set[str]) -> bool | None:
    """True = the claim is supported, False = not supported, None = no ground truth."""
    value = row[column].strip()
    if value in valid_values:
        return True
    if value in invalid_values:
        return False
    if value == "":
        return None
    raise CMHError(f"truth value '{value}' is in neither --valid-values nor --invalid-values")


def load_truth_rows(path: str, truth_column: str, valid: str, invalid: str):
    header, rows = read_table(path)
    require_columns(header, [truth_column], path)
    valid_set, invalid_set = set(split_list(valid)), set(split_list(invalid))
    if not valid_set or not invalid_set or valid_set & invalid_set:
        raise CMHError("--valid-values and --invalid-values must be non-empty and disjoint")
    for row in rows:
        row["_truth"] = truth_value(row, truth_column, valid_set, invalid_set)
    skipped = sum(row["_truth"] is None for row in rows)
    if skipped:
        print(f"note: {skipped} row(s) without ground truth are left out", file=sys.stderr)
    return header, [row for row in rows if row["_truth"] is not None]


def command_triage(args) -> dict:
    header, rows = load_truth_rows(args.table, args.truth_column, args.valid_values, args.invalid_values)
    require_columns(header, [args.flag_column], args.table)
    flagged = [r for r in rows if parse_bool(r[args.flag_column], args.flag_column)]
    unflagged = [r for r in rows if not parse_bool(r[args.flag_column], args.flag_column)]
    err_f = sum(not r["_truth"] for r in flagged)
    err_u = sum(not r["_truth"] for r in unflagged)
    result = {
        "flagged": proportion(err_f, len(flagged)),
        "unflagged": proportion(err_u, len(unflagged)),
        "risk_ratio": risk_ratio(err_f, len(flagged), err_u, len(unflagged)),
        "fisher_p": fisher_exact(err_f, len(flagged) - err_f, err_u, len(unflagged) - err_u),
    }
    if args.noise:
        rng = make_rng(args.seed)
        ratios = []
        for _ in range(args.reps):
            def flips(group):
                return sum((not r["_truth"]) != (rng.random() < args.noise) for r in group)
            ratio = risk_ratio(flips(flagged), len(flagged), flips(unflagged), len(unflagged))["rr"]
            if not is_nan(ratio):
                ratios.append(ratio)
        ratios.sort()
        result["label_noise_check"] = {"flip_rate": args.noise, "replicates": len(ratios),
                                       "rr_median": percentile(ratios, 0.5), "rr_p05": percentile(ratios, 0.05),
                                       "rr_p95": percentile(ratios, 0.95)}
    rr = result["risk_ratio"]
    print(f"error rate, flagged:   {rate_text(result['flagged'])}")
    print(f"error rate, unflagged: {rate_text(result['unflagged'])}")
    print(f"risk ratio {rr['rr']:.2f} [{rr['ci_low']:.2f}, {rr['ci_high']:.2f}]"
          + (" (0.5 added to every cell)" if rr["corrected"] else "") + f"; Fisher p = {result['fisher_p']:.4g}")
    if "label_noise_check" in result:
        nc = result["label_noise_check"]
        print(f"with {pct(args.noise)} of truth labels flipped at random: median risk ratio {nc['rr_median']:.2f} "
              f"(5–95%: {nc['rr_p05']:.2f}–{nc['rr_p95']:.2f})")
    return result


def command_audit(args) -> dict:
    header, rows = load_truth_rows(args.table, args.truth_column, args.valid_values, args.invalid_values)
    columns = split_list(args.decision_columns)
    require_columns(header, columns, args.table)
    overturn = set(split_list(args.overturn_values))
    accept = set(split_list(args.accept_values))
    if not overturn or not accept or overturn & accept:
        raise CMHError("--overturn-values and --accept-values must be non-empty and disjoint")
    per = {}
    decided: dict[str, dict[int, bool]] = {}
    for column in columns:
        decisions = {}
        for i, row in enumerate(rows):
            value = row[column].strip()
            if value in overturn:
                decisions[i] = True
            elif value in accept:
                decisions[i] = False
            elif value:
                raise CMHError(f"{column}: decision '{value}' is in neither --overturn-values nor --accept-values")
        decided[column] = decisions
        valid = [i for i in decisions if rows[i]["_truth"]]
        invalid = [i for i in decisions if not rows[i]["_truth"]]
        caught = sum(decisions[i] for i in invalid)
        false_overturns = sum(decisions[i] for i in valid)
        kept = [i for i in decisions if not decisions[i]]
        residual = sum(not rows[i]["_truth"] for i in kept)
        per[column] = {
            "n_decided": len(decisions), "n_valid": len(valid), "n_invalid": len(invalid),
            "catch_rate": proportion(caught, len(invalid)),
            "false_overturn_rate": proportion(false_overturns, len(valid)),
            "precision": proportion(caught, caught + false_overturns),
            "residual_error_after_audit": proportion(residual, len(kept)),
        }
    comparisons = {}
    for a_index, first in enumerate(columns):
        for second in columns[a_index + 1:]:
            both = sorted(set(decided[first]) & set(decided[second]))
            inv = [i for i in both if not rows[i]["_truth"]]
            val = [i for i in both if rows[i]["_truth"]]
            comparisons[f"{first}|{second}"] = {
                "catches_on_invalid": mcnemar(sum(decided[first][i] and not decided[second][i] for i in inv),
                                              sum(decided[second][i] and not decided[first][i] for i in inv)),
                "false_overturns_on_valid": mcnemar(sum(decided[first][i] and not decided[second][i] for i in val),
                                                    sum(decided[second][i] and not decided[first][i] for i in val)),
                "n_invalid_paired": len(inv), "n_valid_paired": len(val),
            }
    for column, stats in per.items():
        print(f"{column}: caught {rate_text(stats['catch_rate'])}; false overturns "
              f"{rate_text(stats['false_overturn_rate'])}; precision {rate_text(stats['precision'])}; "
              f"residual error {rate_text(stats['residual_error_after_audit'])}")
    for name, comp in comparisons.items():
        c = comp["catches_on_invalid"]
        print(f"{name}: catches differ on {c['b'] + c['c']} invalid claim(s) ({c['b']} vs {c['c']}), "
              f"McNemar exact p = {c['p_exact']:.4g}")
    return {"per_configuration": per, "paired_comparisons": comparisons}


def parse_count(spec: str) -> tuple[str, int, int]:
    try:
        name, frac = spec.split(":", 1)
        k, n = frac.split("/", 1)
        return name, int(k), int(n)
    except ValueError as exc:
        raise CMHError(f"expected NAME:errors/total, got '{spec}'") from exc


def command_compare(args) -> dict:
    name_a, k_a, n_a = parse_count(args.a)
    name_b, k_b, n_b = parse_count(args.b)
    p = fisher_exact(k_a, n_a - k_a, k_b, n_b - k_b)
    result = {name_a: proportion(k_a, n_a), name_b: proportion(k_b, n_b), "fisher_p": p, "note": NOT_EQUAL_NOTE}
    print(f"{name_a}: {rate_text(result[name_a])}")
    print(f"{name_b}: {rate_text(result[name_b])}")
    print(f"Fisher exact p = {p:.4g}. {NOT_EQUAL_NOTE if p >= args.alpha else ''}".rstrip())
    return result


def binary(value: str, positive: str) -> int:
    return 1 if value.strip() == positive else 0


def command_estimate(args) -> dict:
    p_header, population = read_table(args.population)
    g_header, gold = read_table(args.gold)
    require_columns(p_header, [args.model_column], args.population)
    require_columns(g_header, [args.model_column, args.human_column], args.gold)
    group_column = args.group_column
    if group_column:
        require_columns(p_header, [group_column], args.population)
        require_columns(g_header, [group_column], args.gold)
    groups_pop, groups_gold = defaultdict(list), defaultdict(list)
    for row in population:
        groups_pop[row[group_column] if group_column else "all"].append(binary(row[args.model_column], args.positive))
    for row in gold:
        if not row[args.human_column].strip():
            continue
        key = row[group_column] if group_column else "all"
        groups_gold[key].append((binary(row[args.model_column], args.positive),
                                 binary(row[args.human_column], args.positive)))
    out = {}
    for key in sorted(groups_pop):
        model_all = groups_pop[key]
        pairs = groups_gold.get(key, [])
        est = difference_estimate(model_all, [m for m, _ in pairs], [h for _, h in pairs])
        pos = [m for m, h in pairs if h == 1]
        neg = [m for m, h in pairs if h == 0]
        sens = proportion(sum(pos), len(pos))
        spec = proportion(sum(1 - m for m in neg), len(neg))
        corrected = rogan_gladen(sum(model_all) / len(model_all), sens["rate"], spec["rate"]) if model_all else NAN
        out[key] = {"N": len(model_all), "n_gold": len(pairs),
                    "model_share": sum(model_all) / len(model_all) if model_all else NAN,
                    "difference_estimate": est, "sensitivity": sens, "specificity": spec,
                    "rogan_gladen": corrected}
        warn = " (fewer than 30 gold items: wide interval)" if len(pairs) < 30 else ""
        print(f"{key}: model share {pct(out[key]['model_share'])}; corrected {pct(est['estimate'])} "
              f"[{pct(est['ci_low'])}, {pct(est['ci_high'])}] from {len(pairs)} gold item(s){warn}; "
              f"Rogan–Gladen {pct(corrected)}")
    print("note: the gold items must be a simple random sample of the same population (or of each group).")
    return {"groups": out}


def command_recall(args) -> dict:
    header, rows = read_table(args.sample)
    require_columns(header, [args.truth_column], args.sample)
    labelled = [row for row in rows if row[args.truth_column].strip()]
    hits = sum(row[args.truth_column].strip() == args.positive for row in labelled)
    rate = proportion(hits, len(labelled))
    result = {"sampled": len(labelled), "true_positives_found": hits, "miss_rate_in_pool": rate}
    if args.pool_size:
        low, high = wilson_interval(hits, len(labelled))
        result["expected_misses_in_pool"] = {"estimate": rate["rate"] * args.pool_size,
                                             "ci_low": low * args.pool_size, "ci_high": high * args.pool_size,
                                             "pool_size": args.pool_size}
    print(f"true positives among sampled negatives: {rate_text(rate)}")
    if args.pool_size:
        em = result["expected_misses_in_pool"]
        print(f"expected misses in a pool of {args.pool_size}: {em['estimate']:.1f} "
              f"[{em['ci_low']:.1f}, {em['ci_high']:.1f}]")
    print("note: valid only if the sample was drawn at random from that pool.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def truth_args(p):
        p.add_argument("--table", required=True, help="one row per claim with its ground truth")
        p.add_argument("--truth-column", required=True, help="column holding the human verdict on the claim")
        p.add_argument("--valid-values", required=True, help="values meaning the claim is supported, e.g. 1")
        p.add_argument("--invalid-values", required=True, help="values meaning it is not supported, e.g. 2")

    t = sub.add_parser("triage", help="flagged vs unflagged error rates")
    truth_args(t)
    t.add_argument("--flag-column", default="flagged")
    t.add_argument("--noise", type=float, default=0.0, help="also flip this share of truth labels at random")
    t.add_argument("--reps", type=int, default=1000)
    t.add_argument("--seed", default="0")

    a = sub.add_parser("audit", help="what each audit configuration caught and broke")
    truth_args(a)
    a.add_argument("--decision-columns", required=True, help="comma-separated audit decision columns")
    a.add_argument("--overturn-values", default="overturn", help="values meaning the audit rejected the claim")
    a.add_argument("--accept-values", default="accept", help="values meaning the audit kept the claim")

    c = sub.add_parser("compare", help="residual error of two conditions")
    c.add_argument("--a", required=True, metavar="NAME:errors/total")
    c.add_argument("--b", required=True, metavar="NAME:errors/total")
    c.add_argument("--alpha", type=float, default=0.05)

    e = sub.add_parser("estimate", help="correct a model-labelled proportion with a gold sample")
    e.add_argument("--population", required=True, help="all items with model labels")
    e.add_argument("--gold", required=True, help="random sample with model and human labels")
    e.add_argument("--model-column", required=True)
    e.add_argument("--human-column", required=True)
    e.add_argument("--positive", required=True)
    e.add_argument("--group-column", help="estimate per group, e.g. period")

    r = sub.add_parser("recall", help="misses among negatives or abstentions")
    r.add_argument("--sample", required=True, help="random sample from the negative/abstained pool, human-labelled")
    r.add_argument("--truth-column", required=True)
    r.add_argument("--positive", required=True)
    r.add_argument("--pool-size", type=int, help="size of the pool the sample came from")

    for p in (t, a, c, e, r):
        p.add_argument("--out", help="write the result as JSON")

    args = parser.parse_args()
    handler = {"triage": command_triage, "audit": command_audit, "compare": command_compare,
               "estimate": command_estimate, "recall": command_recall}[args.command]
    result = handler(args)
    if args.out:
        inputs = {name: getattr(args, name) for name in ("table", "population", "gold", "sample")
                  if getattr(args, name, None)}
        write_json(args.out, {"result": result, "manifest": manifest(f"cmh_evaluate.py {args.command}",
                                                                     vars(args), inputs)})
    return 0


if __name__ == "__main__":
    run_cli(main)
