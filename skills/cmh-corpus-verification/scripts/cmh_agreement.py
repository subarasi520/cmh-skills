#!/usr/bin/env python3
"""Agreement between raters (humans or models), by class, with cluster bootstrap intervals.

一致度：两两 Cohen's κ、Gwet AC1、正类／负类特异一致率，三人以上加 Fleiss' κ；可按单元做聚类自助法区间。

Measure humans against each other first. Without a human-human baseline a
human-model number has nothing to be read against.

A model is just another rater column: join its labels to the merged sheet
and name the column in --raters.

Class-specific agreement (p_pos, p_neg) is reported because a single
coefficient hides where raters disagree. Kappa drops when one class is rare
even if raters agree on almost every item; AC1 is less affected. Report both
and say which class is hard.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmh_common import (  # noqa: E402
    CMHError, make_rng, manifest, read_table, require_columns, run_cli, split_list, write_json,
)
from cmh_stats import NAN, cluster_bootstrap, cohen_kappa, fleiss_kappa, gwet_ac1, is_nan, specific_agreement  # noqa: E402


def parse_recode(items: list[str]) -> dict[str, str]:
    mapping = {}
    for item in items:
        if "=" not in item:
            raise CMHError(f"--recode expects FROM=TO, got '{item}'")
        source, target = item.split("=", 1)
        mapping[source.strip()] = target.strip()
    return mapping


def pair_stats(pairs: list[tuple[str, str]], categories: list[str], positive: str | None) -> dict:
    a = [x for x, _ in pairs]
    b = [y for _, y in pairs]
    n = len(pairs)
    out = {"n": n, "observed_agreement": (sum(x == y for x, y in pairs) / n) if n else NAN,
           "cohen_kappa": cohen_kappa(a, b), "gwet_ac1": gwet_ac1(a, b, categories)}
    if positive is not None:
        spec = specific_agreement(a, b, positive)
        out.update(p_pos=spec["p_pos"], p_neg=spec["p_neg"],
                   positive_share_first=sum(x == positive for x in a) / n if n else NAN,
                   positive_share_second=sum(y == positive for y in b) / n if n else NAN)
    out["confusion"] = {f"{x}|{y}": count for (x, y), count in sorted(Counter(pairs).items())}
    return out


def fmt(value) -> str:
    if isinstance(value, float):
        return "–" if is_nan(value) else f"{value:.3f}"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--table", required=True, help="CSV with one row per item and one column per rater")
    parser.add_argument("--raters", required=True, help="comma-separated rater columns")
    parser.add_argument("--pairs", help="only these pairs, e.g. label_A:label_B,model:label_A (default: all pairs)")
    parser.add_argument("--categories", help="full label set after recoding, e.g. TARGET,OTHER "
                                             "(default: labels observed). AC1 depends on it")
    parser.add_argument("--positive", help="label treated as the positive class for p_pos/p_neg")
    parser.add_argument("--recode", action="append", default=[], metavar="FROM=TO",
                        help="recode a label before computing, e.g. UNSURE=OTHER (repeatable)")
    parser.add_argument("--cluster", help="column whose values are resampled as clusters (e.g. unit_id)")
    parser.add_argument("--bootstrap", type=int, default=0, help="bootstrap replicates (e.g. 2000); 0 = none")
    parser.add_argument("--seed", default="0")
    parser.add_argument("--out", required=True, help="JSON output")
    parser.add_argument("--markdown", help="also write a Markdown table")
    args = parser.parse_args()

    header, rows = read_table(args.table)
    raters = split_list(args.raters)
    if len(raters) < 2:
        raise CMHError("--raters needs at least two columns")
    require_columns(header, raters, args.table)
    if args.cluster:
        require_columns(header, [args.cluster], args.table)
    recode = parse_recode(args.recode)

    def label(row, column):
        value = row[column].strip()
        return recode.get(value, value)

    observed = sorted({label(row, r) for row in rows for r in raters} - {""})
    categories = split_list(args.categories) or observed
    unknown = set(observed) - set(categories)
    if unknown:
        raise CMHError(f"labels {sorted(unknown)} are not in --categories {categories}")
    if args.positive is not None and args.positive not in categories:
        raise CMHError(f"--positive {args.positive} is not one of the categories {categories}")

    if args.pairs:
        pairs = []
        for item in split_list(args.pairs):
            if ":" not in item:
                raise CMHError(f"--pairs expects first:second, got '{item}'")
            first, second = item.split(":", 1)
            if first not in raters or second not in raters:
                raise CMHError(f"pair {item}: both columns must be listed in --raters")
            pairs.append((first, second))
    else:
        pairs = list(itertools.combinations(raters, 2))

    rng = make_rng(args.seed)
    results = {"categories": categories, "positive": args.positive, "recode": recode, "pairs": {}}
    for first, second in pairs:
        items = [(row.get(args.cluster, "") if args.cluster else str(i), label(row, first), label(row, second))
                 for i, row in enumerate(rows)]
        items = [it for it in items if it[1] and it[2]]
        stats = pair_stats([(x, y) for _, x, y in items], categories, args.positive)
        if args.bootstrap:
            clusters = defaultdict(list)
            for cluster, x, y in items:
                clusters[cluster].append((x, y))
            names = ["cohen_kappa", "gwet_ac1"] + (["p_pos", "p_neg"] if args.positive is not None else [])
            stats["bootstrap"] = {"replicates_requested": args.bootstrap,
                                  "resampled": "clusters:" + args.cluster if args.cluster else "items"}
            for name in names:
                stats["bootstrap"][name] = cluster_bootstrap(
                    clusters, lambda sample, name=name: pair_stats(sample, categories, args.positive)[name],
                    args.bootstrap, rng)
        results["pairs"][f"{first}|{second}"] = stats

    if len(raters) >= 3 and not args.pairs:
        complete = [[label(row, r) for r in raters] for row in rows if all(label(row, r) for r in raters)]
        results["fleiss_kappa"] = {"raters": raters, "n": len(complete), "kappa": fleiss_kappa(complete)}

    out = {"agreement": results,
           "manifest": manifest("cmh_agreement.py", vars(args), {"table": args.table})}
    write_json(args.out, out)

    lines = ["| pair | n | agreement | κ | AC1 | p_pos | p_neg |", "|---|---|---|---|---|---|---|"]
    for name, stats in results["pairs"].items():
        kappa = fmt(stats["cohen_kappa"])
        if "bootstrap" in stats:
            ci = stats["bootstrap"]["cohen_kappa"]
            kappa += f" [{fmt(ci['ci_low'])}, {fmt(ci['ci_high'])}]"
        lines.append(f"| {name} | {stats['n']} | {fmt(stats['observed_agreement'])} | {kappa} | "
                     f"{fmt(stats['gwet_ac1'])} | {fmt(stats.get('p_pos', NAN))} | {fmt(stats.get('p_neg', NAN))} |")
    if "fleiss_kappa" in results:
        fk = results["fleiss_kappa"]
        lines.append(f"\nFleiss' κ over {', '.join(fk['raters'])}: {fmt(fk['kappa'])} (n = {fk['n']})")
    text = "\n".join(lines) + "\n"
    print(text, end="")
    if args.markdown:
        Path(args.markdown).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    run_cli(main)
