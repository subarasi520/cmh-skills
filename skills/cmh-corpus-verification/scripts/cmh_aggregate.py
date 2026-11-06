#!/usr/bin/env python3
"""Turn instance-level labels into unit-level claims, abstaining when evidence is missing.

把逐条判定汇总成结论：定年（最早一例）、比例（逐组占比）、有无（是否观察到）。证据不足就不下结论。

  earliest    first attested positive instance per unit (dating, first attestation)
  proportion  share of positive instances per group (sense shares, framing, stance)
  presence    whether any positive instance was observed per group

A claim always points at its evidence: `earliest` records the instance id of
the anchor; `presence` never says "absent", only "not_observed", because an
absence claim needs a measured miss rate (see cmh_evaluate.py recall).
Time values must be ISO-like: YYYY, YYYY-MM or YYYY-MM-DD.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmh_common import (  # noqa: E402
    CMHError, index_unique, manifest, read_table, require_columns, run_cli, split_list, write_json, write_table,
)
from cmh_stats import wilson_interval  # noqa: E402

TIME_PATTERN = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def joined(labels_path: str, instances_path: str, id_column: str, require_complete: bool):
    """Join labels to instances; returns (instance rows with `label` and `label_status`, counts)."""
    l_header, l_rows = read_table(labels_path)
    require_columns(l_header, ["instance_id", "label", "status"], labels_path)
    labels = index_unique(l_rows, "instance_id", labels_path)
    i_header, i_rows = read_table(instances_path)
    require_columns(i_header, [id_column], instances_path)
    index_unique(i_rows, id_column, instances_path)
    known = {row[id_column] for row in i_rows}
    stray = sorted(set(labels) - known)
    if stray:
        raise CMHError(f"{len(stray)} labelled instance(s) are not in the instances table, e.g. {', '.join(stray[:5])}")
    unlabelled = [row[id_column] for row in i_rows if row[id_column] not in labels]
    if unlabelled and require_complete:
        raise CMHError(f"{len(unlabelled)} instance(s) have no label, e.g. {', '.join(unlabelled[:5])}")
    if unlabelled:
        print(f"warning: {len(unlabelled)} instance(s) have no label and are left out", file=sys.stderr)
    rows = []
    for row in i_rows:
        lab = labels.get(row[id_column])
        if lab is None:
            continue
        merged = dict(row)
        merged["label"] = lab["label"] if lab["status"] == "ok" else ""
        merged["label_status"] = lab["status"]
        rows.append(merged)
    return rows, i_header


def check_times(rows, time_column: str, where: str) -> None:
    bad = [row[time_column] for row in rows if not TIME_PATTERN.match(row[time_column])]
    if bad:
        raise CMHError(f"{where}: {len(bad)} time value(s) are not YYYY, YYYY-MM or YYYY-MM-DD, e.g. {bad[:3]}")


def earliest(rows, *, unit_column, id_column, time_column, positive, window_start, min_positive, tier):
    check_times(rows, time_column, "instances")
    if window_start and not TIME_PATTERN.match(window_start):
        raise CMHError("--window-start must be YYYY, YYYY-MM or YYYY-MM-DD")
    by_unit = defaultdict(list)
    for row in rows:
        by_unit[row[unit_column]].append(row)
    claims = []
    for unit in sorted(by_unit):
        members = by_unit[unit]
        valid = [r for r in members if r["label_status"] == "ok"]
        hits = sorted((r for r in valid if r["label"] == positive), key=lambda r: (r[time_column], r[id_column]))
        claim = {"unit_id": unit, "n_instances": len(members), "n_valid_labels": len(valid),
                 "n_positive": len(hits), "tier": tier}
        if not valid:
            claim.update(status="abstained", reason="no_valid_labels")
        elif len(hits) < min_positive:
            claim.update(status="abstained", reason="too_few_positive" if hits else "no_positive_instance")
        else:
            anchor = hits[0]
            claim.update(status="claimed", reason="", value=anchor[time_column],
                         evidence_instance_id=anchor[id_column],
                         n_positive_at_value=sum(r[time_column] == anchor[time_column] for r in hits))
            later = [r[time_column] for r in hits if r[time_column] > anchor[time_column]]
            if later:
                claim["next_positive_time"] = later[0]
                claim["gap_to_next_positive"] = int(later[0][:4]) - int(anchor[time_column][:4])
            # Earliest instance in the corpus at all, positive or not: shows how close
            # the anchor sits to where the record begins.
            claim["earliest_instance_time"] = min(r[time_column] for r in members)
            # Compare at the precision of --window-start: with "1950", an anchor of
            # "1950-03" also sits at the window edge.
            at_edge = bool(window_start) and anchor[time_column][: len(window_start)] <= window_start
            claim["censored"] = "left" if at_edge else ""
        claims.append(claim)
    header = ["unit_id", "status", "reason", "value", "evidence_instance_id", "censored", "n_instances",
              "n_valid_labels", "n_positive", "n_positive_at_value", "next_positive_time", "gap_to_next_positive",
              "earliest_instance_time", "tier"]
    return header, claims


def proportion(rows, *, group_columns, positive, uncertain_labels, uncertain_policy, min_n, tier):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[c] for c in group_columns)].append(row)
    out = []
    for key in sorted(groups):
        members = groups[key]
        valid = [r for r in members if r["label_status"] == "ok"]
        n_pos = sum(r["label"] == positive for r in valid)
        n_unsure = sum(r["label"] in uncertain_labels for r in valid)
        denom = len(valid) - (n_unsure if uncertain_policy == "exclude" else 0)
        low, high = wilson_interval(n_pos, denom) if denom else (float("nan"), float("nan"))
        record = dict(zip(group_columns, key))
        record.update({
            "n_instances": len(members), "n_valid_labels": len(valid), "n_positive": n_pos,
            "n_uncertain": n_unsure, "denominator": denom,
            "share": n_pos / denom if denom else float("nan"), "ci_low": low, "ci_high": high,
            "status": "ok" if denom >= min_n else "insufficient_n", "tier": tier,
        })
        out.append(record)
    header = [*group_columns, "status", "share", "ci_low", "ci_high", "n_positive", "denominator", "n_uncertain",
              "n_valid_labels", "n_instances", "tier"]
    return header, out


def presence(rows, *, group_columns, positive, tier):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[c] for c in group_columns)].append(row)
    out = []
    for key in sorted(groups):
        members = groups[key]
        valid = [r for r in members if r["label_status"] == "ok"]
        n_pos = sum(r["label"] == positive for r in valid)
        record = dict(zip(group_columns, key))
        record.update({"status": "observed" if n_pos else "not_observed", "n_positive": n_pos,
                       "n_valid_labels": len(valid), "n_instances": len(members), "tier": tier})
        out.append(record)
    return [*group_columns, "status", "n_positive", "n_valid_labels", "n_instances", "tier"], out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("earliest", "proportion", "presence"):
        p = sub.add_parser(name)
        p.add_argument("--labels", required=True, help="labels CSV from cmh_judge.py")
        p.add_argument("--instances", required=True, help="the instances CSV that was judged")
        p.add_argument("--out", required=True)
        p.add_argument("--positive", required=True, help="the label that counts as evidence, e.g. TARGET")
        p.add_argument("--id-column", default="instance_id")
        p.add_argument("--tier", default="model_judged", help="evidence tier recorded on each claim")
        p.add_argument("--require-complete", action="store_true", help="fail if any instance has no label")
        if name == "earliest":
            p.add_argument("--unit-column", default="unit_id")
            p.add_argument("--time-column", default="time")
            p.add_argument("--window-start", help="first period the corpus covers; anchors at or before it are "
                                                  "marked censored=left (the sense may be older)")
            p.add_argument("--min-positive", type=int, default=1, help="positive instances needed to claim")
        else:
            p.add_argument("--group-columns", required=True, help="comma-separated, e.g. unit_id,period")
        if name == "proportion":
            p.add_argument("--uncertain-labels", default="", help="labels treated as uncertain, e.g. UNSURE")
            p.add_argument("--uncertain-policy", choices=["negative", "exclude"], default="exclude",
                           help="count uncertain as negative, or leave them out of the denominator")
            p.add_argument("--min-n", type=int, default=10, help="smallest denominator reported as ok")

    args = parser.parse_args()
    rows, header = joined(args.labels, args.instances, args.id_column, args.require_complete)
    if args.command == "earliest":
        require_columns(header, [args.unit_column, args.time_column], args.instances)
        out_header, out = earliest(rows, unit_column=args.unit_column, id_column=args.id_column,
                                   time_column=args.time_column, positive=args.positive,
                                   window_start=args.window_start, min_positive=args.min_positive, tier=args.tier)
    else:
        groups = split_list(args.group_columns)
        require_columns(header, groups, args.instances)
        if args.command == "proportion":
            out_header, out = proportion(rows, group_columns=groups, positive=args.positive,
                                         uncertain_labels=set(split_list(args.uncertain_labels)),
                                         uncertain_policy=args.uncertain_policy, min_n=args.min_n, tier=args.tier)
        else:
            out_header, out = presence(rows, group_columns=groups, positive=args.positive, tier=args.tier)
    write_table(args.out, out_header, out)
    write_json(str(args.out) + ".manifest.json",
               manifest("cmh_aggregate.py " + args.command, vars(args),
                        {"labels": args.labels, "instances": args.instances}))
    statuses = defaultdict(int)
    for row in out:
        statuses[row["status"]] += 1
    print(f"{len(out)} row(s) written to {args.out}: " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())))
    return 0


if __name__ == "__main__":
    run_cli(main)
