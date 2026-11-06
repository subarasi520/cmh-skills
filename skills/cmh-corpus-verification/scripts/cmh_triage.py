#!/usr/bin/env python3
"""Flag risky claims by stated rules and draw a seeded random spot check of the rest.

分流：按事先写明的规则（不是按模型的置信度）把可疑结论送去复核，并从未标记的结论里带种子随机抽查。

Rules live in a TOML file. Each [[rule]] has a name and a list of conditions;
conditions inside one rule must all hold (AND), and a claim is flagged when
any rule fires (OR). Example:

  [[rule]]
  name = "short_form"
  conditions = [{ column = "form", op = "len_le", value = 2 }]

  [[rule]]
  name = "window_edge"
  conditions = [{ column = "censored", op = "eq", value = "left" }]

Ops: eq ne in not_in empty not_empty regex not_regex lt le gt ge
len_lt len_le len_gt len_ge len_eq. Numeric ops are false on empty cells.

Why not model confidence: a model cannot flag the errors it is confident
about. Confidence may add items to review; it must never take items out of
the random spot check.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmh_common import (  # noqa: E402
    CMHError, check_all, index_unique, load_toml, manifest, read_table, require_columns, run_cli, sample_rows,
    validate_condition, write_json, write_table,
)


def load_rules(path: str) -> list[dict]:
    raw = load_toml(path)
    rules = raw.get("rule")
    if not isinstance(rules, list) or not rules:
        raise CMHError(f"{path}: no [[rule]] entries")
    names = set()
    for i, rule in enumerate(rules, start=1):
        where = f"{path}: rule {i}"
        name = rule.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise CMHError(f"{where}: each rule needs a unique name")
        names.add(name)
        conditions = rule.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise CMHError(f"{where} ({name}): needs a non-empty conditions list")
        for cond in conditions:
            validate_condition(cond, f"{where} ({name})")
    return rules


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--claims", required=True, help="claims CSV (for example from cmh_aggregate.py)")
    parser.add_argument("--rules", required=True, help="TOML file with [[rule]] entries")
    parser.add_argument("--out", required=True)
    parser.add_argument("--units", help="optional CSV of unit attributes joined on the key column")
    parser.add_argument("--key-column", default="unit_id")
    parser.add_argument("--status-column", default="status", help="only rows with this column = --claimed-value "
                                                                   "are triaged; others pass through unflagged")
    parser.add_argument("--claimed-value", default="claimed")
    parser.add_argument("--seed", required=True, help="seed for the spot check; record it in the protocol")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--spot-check-n", type=int, help="number of unflagged claims to spot-check")
    group.add_argument("--spot-check-fraction", type=float, help="fraction of unflagged claims to spot-check")
    parser.add_argument("--strata", help="column to stratify the spot check by")
    args = parser.parse_args()

    rules = load_rules(args.rules)
    header, rows = read_table(args.claims)
    require_columns(header, [args.key_column, args.status_column], args.claims)
    index_unique(rows, args.key_column, args.claims)
    if args.units:
        u_header, u_rows = read_table(args.units)
        units = index_unique(u_rows, args.key_column, args.units)
        clash = [c for c in u_header if c in header and c != args.key_column]
        if clash:
            raise CMHError(f"columns in both --claims and --units: {', '.join(clash)}")
        for row in rows:
            extra = units.get(row[args.key_column])
            if extra is None:
                raise CMHError(f"unit '{row[args.key_column]}' is missing from {args.units}")
            row.update({k: v for k, v in extra.items() if k != args.key_column})
        header = header + [c for c in u_header if c != args.key_column]

    claimed = [row for row in rows if row[args.status_column] == args.claimed_value]
    claimed_keys = {row[args.key_column] for row in claimed}
    for row in rows:
        reasons = []
        if row[args.key_column] in claimed_keys:
            reasons = [rule["name"] for rule in rules if check_all(row, rule["conditions"])]
        row["flagged"] = bool(reasons)
        row["flag_reasons"] = ";".join(reasons)
        row["spot_check"] = False

    unflagged = [row for row in claimed if not row["flagged"]]
    picked = []
    if args.spot_check_n is not None or args.spot_check_fraction is not None:
        if args.strata and args.strata not in header:
            raise CMHError(f"--strata column '{args.strata}' not found")
        picked = sample_rows(unflagged, id_column=args.key_column, seed=args.seed, n=args.spot_check_n,
                             fraction=args.spot_check_fraction, strata_column=args.strata)
        for row in picked:
            row["spot_check"] = True
    else:
        print("warning: no spot check requested; errors in unflagged claims will go unmeasured", file=sys.stderr)
    for row in rows:
        row["review"] = row["flagged"] or row["spot_check"]

    out_header = header + ["flagged", "flag_reasons", "spot_check", "review"]
    write_table(args.out, out_header, rows)
    counts = {rule["name"]: sum(rule["name"] in row["flag_reasons"].split(";") for row in rows) for rule in rules}
    write_json(args.out + ".manifest.json",
               manifest("cmh_triage.py", vars(args), {"claims": args.claims, "rules": args.rules},
                        counts={"claims": len(claimed), "flagged": sum(r["flagged"] for r in rows),
                                "spot_check": len(picked), "per_rule": counts}))
    print(f"{len(claimed)} claim(s): {sum(r['flagged'] for r in rows)} flagged, {len(picked)} spot-checked "
          f"(seed {args.seed}); written to {args.out}")
    return 0


if __name__ == "__main__":
    run_cli(main)
