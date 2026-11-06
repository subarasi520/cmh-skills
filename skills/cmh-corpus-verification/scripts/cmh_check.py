#!/usr/bin/env python3
"""Check a results table against written rules, and diff it against an earlier snapshot.

核对结论表（真值表）：按写好的规则逐条检查；与旧快照比对，查出悄悄变掉的结论。

  run   apply the checks in a TOML file; exit 1 if any check fails
  diff  compare two versions of a table by key; exit 1 with --fail-on-change

Checks ([[check]] entries, `type` = ...):

  unique       columns   = ["unit_id"]                 values (or value tuples) are unique
  not_empty    columns   = ["unit_id", "tier"]          no empty cells
  allowed      column, values = [...]                   only these values (empty allowed with allow_empty)
  pattern      column, regex                            every non-empty cell matches (re.fullmatch)
  implies      when = [conditions], then = [conditions] rows meeting `when` must meet `then`
  foreign_key  column, table, table_column              every value exists in another file
               (separator = ";" splits multi-valued cells; allow_empty = true skips blanks)
  row_count    min / max, or same_as = "units.csv"      the table has the expected number of rows

Conditions use the same ops as triage rules. Paths in `table` / `same_as` are
relative to the rules file. Write the rules that encode your evidence policy
(for example "a search-count tier only ever gives an upper bound") and run them
every time the table is rebuilt.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmh_common import (  # noqa: E402
    CMHError, check_all, index_unique, load_toml, read_table, require_columns, run_cli, split_list,
    validate_condition,
)

MAX_SHOWN = 10


def describe(row_numbers: list[int], keys: list[str]) -> str:
    shown = ", ".join(f"line {n}" + (f" ({k})" if k else "") for n, k in list(zip(row_numbers, keys))[:MAX_SHOWN])
    more = f" and {len(row_numbers) - MAX_SHOWN} more" if len(row_numbers) > MAX_SHOWN else ""
    return shown + more


def run_checks(table_path: str, rules_path: str, key_column: str | None) -> list[str]:
    rules = load_toml(rules_path)
    checks = rules.get("check")
    if not isinstance(checks, list) or not checks:
        raise CMHError(f"{rules_path}: no [[check]] entries")
    base = Path(rules_path).resolve().parent
    header, rows = read_table(table_path)
    if key_column:
        require_columns(header, [key_column], table_path)
    failures = []

    def key(row):
        return row.get(key_column, "") if key_column else ""

    for number, check in enumerate(checks, start=1):
        kind = check.get("type")
        name = check.get("name") or f"check {number} ({kind})"
        where = f"{rules_path}: {name}"
        bad: list[int] = []
        bad_keys: list[str] = []

        def mark(line_no, row):
            bad.append(line_no)
            bad_keys.append(key(row))

        if kind == "unique":
            columns = check.get("columns") or []
            require_columns(header, columns, table_path)
            seen = {}
            for line_no, row in enumerate(rows, start=2):
                value = tuple(row[c] for c in columns)
                if value in seen:
                    mark(line_no, row)
                seen.setdefault(value, line_no)
        elif kind == "not_empty":
            columns = check.get("columns") or []
            require_columns(header, columns, table_path)
            for line_no, row in enumerate(rows, start=2):
                if any(not row[c].strip() for c in columns):
                    mark(line_no, row)
        elif kind == "allowed":
            column, values = check.get("column"), check.get("values")
            if not isinstance(values, list):
                raise CMHError(f"{where}: 'values' must be a list")
            require_columns(header, [column], table_path)
            allowed = {str(v) for v in values}
            for line_no, row in enumerate(rows, start=2):
                cell = row[column]
                if cell == "" and check.get("allow_empty", False):
                    continue
                if cell not in allowed:
                    mark(line_no, row)
        elif kind == "pattern":
            column = check.get("column")
            require_columns(header, [column], table_path)
            try:
                regex = re.compile(check.get("regex", ""))
            except re.error as exc:
                raise CMHError(f"{where}: bad regex: {exc}") from exc
            for line_no, row in enumerate(rows, start=2):
                if row[column] and not regex.fullmatch(row[column]):
                    mark(line_no, row)
        elif kind == "implies":
            when, then = check.get("when"), check.get("then")
            if not isinstance(when, list) or not isinstance(then, list) or not when or not then:
                raise CMHError(f"{where}: 'when' and 'then' must be non-empty lists of conditions")
            for cond in [*when, *then]:
                validate_condition(cond, where)
                require_columns(header, [cond["column"]], table_path)
            for line_no, row in enumerate(rows, start=2):
                if check_all(row, when) and not check_all(row, then):
                    mark(line_no, row)
        elif kind == "foreign_key":
            column, other, other_column = check.get("column"), check.get("table"), check.get("table_column")
            if not other or not other_column:
                raise CMHError(f"{where}: needs 'table' and 'table_column'")
            require_columns(header, [column], table_path)
            o_header, o_rows = read_table(base / other)
            require_columns(o_header, [other_column], str(base / other))
            known = {row[other_column] for row in o_rows}
            for line_no, row in enumerate(rows, start=2):
                sep = check.get("separator")
                values = [v.strip() for v in row[column].split(sep)] if sep else [row[column]]
                values = [v for v in values if v] if check.get("allow_empty", False) else values
                if any(v not in known for v in values):
                    mark(line_no, row)
        elif kind == "row_count":
            count = len(rows)
            expected_min, expected_max = check.get("min"), check.get("max")
            if check.get("same_as"):
                _, other_rows = read_table(base / check["same_as"])
                expected_min = expected_max = len(other_rows)
            if (expected_min is not None and count < expected_min) or (expected_max is not None and count > expected_max):
                failures.append(f"{name}: {count} row(s), expected between {expected_min} and {expected_max}")
            continue
        else:
            raise CMHError(f"{where}: unknown check type '{kind}'")
        if bad:
            failures.append(f"{name}: {len(bad)} row(s) fail — {describe(bad, bad_keys)}")
    return failures


def command_run(args) -> int:
    failures = run_checks(args.table, args.rules, args.key_column)
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        print(f"{len(failures)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


def command_diff(args) -> int:
    o_header, old_rows = read_table(args.old)
    n_header, new_rows = read_table(args.new)
    for header, path in ((o_header, args.old), (n_header, args.new)):
        require_columns(header, [args.key], path)
    old = index_unique(old_rows, args.key, args.old)
    new = index_unique(new_rows, args.key, args.new)
    columns = split_list(args.columns) or [c for c in n_header if c in o_header and c != args.key]
    for header, path in ((o_header, args.old), (n_header, args.new)):
        require_columns(header, columns, path)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changes = []
    for key in sorted(set(old) & set(new)):
        for column in columns:
            if old[key][column] != new[key][column]:
                changes.append((key, column, old[key][column], new[key][column]))
    print(f"added {len(added)}, removed {len(removed)}, changed cells {len(changes)}")
    for key in added[:MAX_SHOWN]:
        print(f"+ {key}")
    for key in removed[:MAX_SHOWN]:
        print(f"- {key}")
    for key, column, before, after in changes[: args.show]:
        print(f"~ {key} [{column}]: {before!r} -> {after!r}")
    if len(changes) > args.show:
        print(f"... {len(changes) - args.show} more change(s)")
    if args.fail_on_change and (added or removed or changes):
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="apply the checks in a rules file")
    r.add_argument("--table", required=True)
    r.add_argument("--rules", required=True)
    r.add_argument("--key-column", help="column shown next to failing line numbers, e.g. unit_id")
    d = sub.add_parser("diff", help="compare two versions of a table")
    d.add_argument("--old", required=True)
    d.add_argument("--new", required=True)
    d.add_argument("--key", required=True)
    d.add_argument("--columns", help="columns to compare (default: all shared columns)")
    d.add_argument("--show", type=int, default=50, help="how many changed cells to print")
    d.add_argument("--fail-on-change", action="store_true")
    args = parser.parse_args()
    return command_run(args) if args.command == "run" else command_diff(args)


if __name__ == "__main__":
    run_cli(main)
