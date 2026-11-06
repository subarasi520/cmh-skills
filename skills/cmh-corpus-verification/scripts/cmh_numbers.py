#!/usr/bin/env python3
"""Check that every number in a manuscript comes from a results file.

数字核对：稿子里登记过的数字逐个对回结果文件；没登记的数字列出来给人看，防止手算、抄错、旧数没改。

  check  look up each registered number, format it, and find it in the text;
         then list numbers in the text that are not registered

Registry (TOML):

  [settings]
  ignore = ['^(19|20)\\d{2}$', '^[0-9]$']   # regexes for numbers the scan skips

  [[number]]
  id = "kappa_ab"
  source = "results/agreement.json"         # JSON: give `path` as a list of keys
  path = ["agreement", "pairs", "label_A|label_B", "cohen_kappa"]
  format = ".2f"                             # Python format spec
  near = "κ ="                               # optional: must appear within `window`
                                             # (default 60) characters after this text

  [[number]]
  id = "claims"
  source = "results/claims.csv"              # CSV: count rows matching conditions,
  count_where = [{ column = "status", op = "eq", value = "claimed" }]
  format = ",d"

  [[number]]
  id = "share_2010"
  source = "results/shares.csv"              # CSV: or read one cell
  row = { column = "period", equals = "2010" }
  column = "share"
  format = ".1f"
  percent = true                             # multiply by 100 before formatting

A number found in the text proves the value appears, not that the sentence
around it is right. Read the sentences too.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmh_common import CMHError, check_all, load_toml, read_table, require_columns, run_cli, validate_condition  # noqa: E402

# ASCII-only boundaries so numbers next to CJK characters are still found.
NUMBER = re.compile(r"(?<![0-9A-Za-z_.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![0-9A-Za-z_])")


def lookup(entry: dict, base: Path) -> float:
    source = base / entry["source"]
    if source.suffix.lower() == ".json":
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CMHError(f"{entry['id']}: {source} not found") from exc
        for step in entry.get("path", []):
            try:
                value = value[step] if isinstance(value, dict) else value[int(step)]
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise CMHError(f"{entry['id']}: path step {step!r} not found in {source}") from exc
    elif source.suffix.lower() == ".csv":
        header, rows = read_table(source)
        if "count_where" in entry:
            for cond in entry["count_where"]:
                validate_condition(cond, entry["id"])
            value = sum(check_all(row, entry["count_where"]) for row in rows)
        else:
            spec, column = entry.get("row"), entry.get("column")
            if not isinstance(spec, dict) or not column:
                raise CMHError(f"{entry['id']}: a CSV source needs count_where, or row and column")
            require_columns(header, [spec["column"], column], str(source))
            matches = [row for row in rows if row[spec["column"]] == str(spec["equals"])]
            if len(matches) != 1:
                raise CMHError(f"{entry['id']}: {len(matches)} rows match {spec}, expected exactly 1")
            value = matches[0][column]
    else:
        raise CMHError(f"{entry['id']}: source must be .json or .csv")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise CMHError(f"{entry['id']}: value {value!r} is not a number") from exc


def render(value: float, entry: dict) -> str:
    if entry.get("percent"):
        value *= 100
    spec = entry.get("format", "")
    if spec.endswith("d"):
        if abs(value - round(value)) > 1e-9:
            raise CMHError(f"{entry['id']}: format {spec!r} needs a whole number, got {value}")
        value = int(round(value))
    try:
        return format(value, spec)
    except ValueError as exc:
        raise CMHError(f"{entry['id']}: bad format spec {spec!r}") from exc


def find_lines(text: str, needle: str, near: str | None = None, window: int = 60) -> list[int]:
    """Lines where `needle` occurs as a whole number; with `near`, only within
    `window` characters after an occurrence of that context text."""
    pattern = re.compile(r"(?<![0-9.,])" + re.escape(needle) + r"(?![0-9])")
    if not near:
        return [text.count("\n", 0, m.start()) + 1 for m in pattern.finditer(text)]
    lines = []
    start = text.find(near)
    while start != -1:
        end = start + len(near)
        for m in pattern.finditer(text, end, end + window):
            lines.append(text.count("\n", 0, m.start()) + 1)
        start = text.find(near, start + 1)
    return sorted(set(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check")
    c.add_argument("--manuscript", required=True, help="text or Markdown file")
    c.add_argument("--registry", required=True, help="TOML registry of numbers")
    c.add_argument("--strict", action="store_true", help="also fail on unregistered numbers")
    args = parser.parse_args()

    registry = load_toml(args.registry)
    base = Path(args.registry).resolve().parent
    entries = registry.get("number", [])
    if not entries:
        raise CMHError(f"{args.registry}: no [[number]] entries")
    ignore = [re.compile(p) for p in registry.get("settings", {}).get("ignore", [])]
    text = Path(args.manuscript).read_text(encoding="utf-8")

    missing, registered = [], set()
    for entry in entries:
        if "id" not in entry or "source" not in entry:
            raise CMHError("every [[number]] needs id and source")
        rendered = render(lookup(entry, base), entry)
        registered.add(rendered)
        near = entry.get("near")
        lines = find_lines(text, rendered, near, int(entry.get("window", 60)))
        context = f" after {near!r}" if near else ""
        if lines:
            print(f"ok      {entry['id']}: {rendered}{context} (line {', '.join(map(str, lines[:5]))})")
        else:
            print(f"MISSING {entry['id']}: {rendered} does not appear in the manuscript{context}")
            missing.append(entry["id"])

    unregistered = []
    for match in NUMBER.finditer(text):
        token = match.group(1)
        if token in registered or any(p.search(token) for p in ignore):
            continue
        line = text.count("\n", 0, match.start()) + 1
        unregistered.append((line, token))
    if unregistered:
        print(f"\n{len(unregistered)} number(s) in the text are not registered (check each one or add it):")
        for line, token in unregistered:
            print(f"  line {line}: {token}")
    if missing or (args.strict and unregistered):
        return 1
    return 0


if __name__ == "__main__":
    run_cli(main)
