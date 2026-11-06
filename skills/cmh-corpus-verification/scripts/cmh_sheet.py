#!/usr/bin/env python3
"""Make blind annotation sheets, check returned sheets, and unblind them.

盲判卷：生成卷子（隐去来源、打乱顺序、答案键另存）、核对交回的卷子、揭盲合并。

  make   one sheet per rater: shuffled, deduplicated, sources hidden; the key
         that maps sheet items back to the original rows goes to a separate folder
  check  compare a returned sheet with its blank: ids, unchanged text, valid labels
  merge  join returned sheets with the key; majority label per item

Blindness rules built in:
  * only the columns named in --show reach annotators; columns whose names
    suggest an answer or a source (label, model, truth, source, ...) are refused
  * the key folder must not be the sheet folder or inside it
  * existing sheets are never overwritten without --force (regenerating sheets
    after seeing results is a way to fish for a better sample)
  * cells a spreadsheet could execute as formulas are escaped
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import string
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmh_common import (  # noqa: E402
    CMHError, find_git_root, index_unique, is_within, make_rng, manifest, read_table, require_columns, run_cli,
    sample_rows, sha256_file, sha256_text, split_list, unescape_formula, write_json, write_table,
)

# Column-name tokens that suggest an answer, a model output or a source.
RISKY_NAME_TOKENS = {"label", "labels", "model", "judge", "judgment", "judgement", "audit", "answer", "truth",
                     "gold", "source", "condition", "layer", "pred", "prediction", "score", "confidence", "flag",
                     "flagged", "status", "tier", "majority", "verdict", "decision"}
SHEET_FIXED = ("sheet_item_id", "label", "note")


def content_hash(row: dict[str, str], show: list[str]) -> str:
    return sha256_text(json.dumps([row[c].strip() for c in show], ensure_ascii=False))


def git_ignored(path: Path) -> bool | None:
    root = find_git_root(path.parent if not path.exists() else path)
    if root is None:
        return None
    try:
        result = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=root, capture_output=True,
                                timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0


def parse_requirements(items: list[str]) -> list[tuple[str, str]]:
    out = []
    for item in items:
        if "=" not in item:
            raise CMHError(f"--require expects column=value, got '{item}'")
        column, value = item.split("=", 1)
        out.append((column.strip(), value.strip()))
    return out


def command_make(args) -> int:
    header, rows = read_table(args.items)
    require_columns(header, [args.id_column], args.items)
    index_unique(rows, args.id_column, args.items)
    show = split_list(args.show)
    if not show:
        raise CMHError("--show needs at least one column")
    require_columns(header, show, args.items)
    clash = [c for c in show if c in SHEET_FIXED]
    if clash:
        raise CMHError(f"--show cannot include reserved column(s): {', '.join(clash)}")
    risky = [c for c in show if set(re.split(r"[^a-z0-9]+", c.lower())) & RISKY_NAME_TOKENS]
    if risky and not args.allow_risky_columns:
        raise CMHError(f"refusing to show column(s) {', '.join(risky)}: the names suggest an answer, a model "
                       "output or a source. Rename them or pass --allow-risky-columns after checking")
    raters = split_list(args.raters)
    if not raters or len(set(raters)) != len(raters):
        raise CMHError("--raters needs distinct names, e.g. A,B")
    if any(not set(r) <= set(string.ascii_letters + string.digits + "_-") for r in raters):
        raise CMHError("rater names may only use letters, digits, '_' and '-'")

    for column, value in parse_requirements(args.require):
        require_columns(header, [column], args.items)
        bad = [row[args.id_column] for row in rows if row[column] != value]
        if bad:
            raise CMHError(f"{len(bad)} item(s) do not have {column}={value}, e.g. {', '.join(bad[:5])}. "
                           "Fix the item list before any sheet goes out")
    for column in args.summarize:
        require_columns(header, [column], args.items)
        counts = Counter(row[column] for row in rows)
        print(f"{column}: " + ", ".join(f"{k or '(empty)'} {v}" for k, v in counts.most_common()))

    out_dir, key_dir = Path(args.out_dir).resolve(), Path(args.key_dir).resolve()
    if is_within(key_dir, out_dir) or is_within(out_dir, key_dir):
        raise CMHError("--key-dir and --out-dir must be separate folders, neither inside the other")
    sheet_paths = {r: out_dir / f"sheet_{r}.csv" for r in raters}
    key_path, key_manifest = key_dir / "key.csv", key_dir / "key_manifest.json"
    existing = [p for p in [*sheet_paths.values(), key_path, key_manifest] if p.exists()]
    if existing and not args.force:
        raise CMHError(f"{existing[0]} exists. Blind sheets are made once; keep the first set "
                       "(use --force only if no sheet has been sent out)")

    dedupe = split_list(args.dedupe_on) or show
    require_columns(header, dedupe, args.items)
    if args.strata:
        require_columns(header, [args.strata], args.items)
    groups: dict[tuple, list[dict[str, str]]] = defaultdict(list)
    for row in sorted(rows, key=lambda r: r[args.id_column]):
        groups[tuple(row[c].strip() for c in dedupe)].append(row)
    items = []
    for members in groups.values():
        first = members[0]
        hashes = {content_hash(m, show) for m in members}
        if len(hashes) > 1:
            raise CMHError(f"items {', '.join(m[args.id_column] for m in members)} share --dedupe-on values but "
                           "differ in shown columns; include those columns in --dedupe-on")
        items.append({"_ids": [m[args.id_column] for m in members], "_first": first,
                      "_group": ";".join(m[args.id_column] for m in members),
                      **({args.strata: first[args.strata]} if args.strata else {})})
    if args.sample_n is not None or args.sample_fraction is not None:
        items = sample_rows(items, id_column="_group", seed=args.seed, n=args.sample_n,
                            fraction=args.sample_fraction, strata_column=args.strata)

    rng = make_rng(f"{args.seed}:ids")
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    used = set()
    for item in sorted(items, key=lambda it: it["_group"]):
        while True:
            code = "S" + "".join(rng.choice(alphabet) for _ in range(6))
            if code not in used:
                used.add(code)
                item["sheet_item_id"] = code
                break

    sheet_header = ["sheet_item_id", *show, "label", "note"]
    outputs = {}
    for rater in raters:
        order = sorted(items, key=lambda it: it["sheet_item_id"])
        make_rng(f"{args.seed}:order:{rater}").shuffle(order)
        sheet_rows = [{"sheet_item_id": it["sheet_item_id"], **{c: it["_first"][c] for c in show},
                       "label": "", "note": ""} for it in order]
        write_table(sheet_paths[rater], sheet_header, sheet_rows, excel_safe=True, bom=not args.no_bom)
        outputs[f"sheet_{rater}"] = {"path": str(sheet_paths[rater]), "sha256": sha256_file(sheet_paths[rater])}
    key_rows = [{"sheet_item_id": it["sheet_item_id"], "item_ids": ";".join(it["_ids"]),
                 "content_sha256": content_hash(it["_first"], show)}
                for it in sorted(items, key=lambda it: it["sheet_item_id"])]
    write_table(key_path, ["sheet_item_id", "item_ids", "content_sha256"], key_rows)
    if args.instructions:
        shutil.copyfile(args.instructions, out_dir / Path(args.instructions).name)
    write_json(key_manifest, manifest(
        "cmh_sheet.py make", vars(args), {"items": args.items},
        raters=raters, show=show, labels=split_list(args.labels), n_sheet_items=len(items),
        n_source_items=sum(len(it["_ids"]) for it in items), outputs=outputs))

    ignored = git_ignored(key_path)
    if ignored is False:
        print(f"warning: {key_path} is inside a git repository and not ignored. "
              "Committing the key next to the data defeats the blinding", file=sys.stderr)
    print(f"{len(items)} sheet item(s) for rater(s) {', '.join(raters)} in {out_dir}; key in {key_dir}")
    if args.labels:
        print(f"allowed answers: {args.labels}")
    return 0


def read_sheet(path: str) -> tuple[list[str], dict[str, dict[str, str]], list[str]]:
    header, rows = read_table(path)
    require_columns(header, ["sheet_item_id", "label"], path)
    by_id: dict[str, dict[str, str]] = {}
    duplicates = []
    for row in rows:
        sid = row["sheet_item_id"].strip()
        if sid in by_id:
            duplicates.append(sid)
        by_id[sid] = row
    return header, by_id, duplicates


def normalise(value: str) -> str:
    return unescape_formula(value.strip())


def command_check(args) -> int:
    allowed = set(split_list(args.labels))
    b_header, blank, _ = read_sheet(args.blank)
    r_header, returned, duplicates = read_sheet(args.returned)
    shown = [c for c in b_header if c not in SHEET_FIXED]
    missing_cols = [c for c in shown if c not in r_header]
    problems, warnings = [], []
    if missing_cols:
        problems.append(f"returned sheet lost column(s): {', '.join(missing_cols)}")
    missing = sorted(set(blank) - set(returned))
    extra = sorted(set(returned) - set(blank))
    if missing:
        problems.append(f"{len(missing)} item(s) missing, e.g. {', '.join(missing[:5])}")
    if extra:
        problems.append(f"{len(extra)} unknown item id(s), e.g. {', '.join(extra[:5])}")
    if duplicates:
        problems.append(f"duplicate item id(s): {', '.join(sorted(set(duplicates))[:5])}")
    changed, invalid, empty = [], [], []
    for sid, row in returned.items():
        if sid not in blank:
            continue
        if not missing_cols and any(normalise(row[c]) != normalise(blank[sid][c]) for c in shown):
            changed.append(sid)
        label = row["label"].strip()
        if not label:
            empty.append(sid)
        elif allowed and label not in allowed:
            invalid.append(sid)
    if changed:
        problems.append(f"{len(changed)} item(s) with edited text, e.g. {', '.join(changed[:5])}")
    if invalid:
        problems.append(f"{len(invalid)} label(s) outside {sorted(allowed)}, e.g. {', '.join(invalid[:5])}")
    if empty:
        (problems if args.require_complete else warnings).append(f"{len(empty)} item(s) without a label")
    for message in warnings:
        print(f"warning: {message}")
    for message in problems:
        print(f"problem: {message}")
    if not problems:
        print(f"{args.returned}: {len(returned)} item(s), structure ok")
    return 1 if problems else 0


def command_merge(args) -> int:
    allowed = set(split_list(args.labels))
    k_header, key_rows = read_table(args.key)
    require_columns(k_header, ["sheet_item_id", "item_ids"], args.key)
    key = index_unique(key_rows, "sheet_item_id", args.key)
    sheets = {}
    for spec in args.returned:
        if "=" not in spec:
            raise CMHError(f"--returned expects RATER=path, got '{spec}'")
        rater, path = spec.split("=", 1)
        _, by_id, duplicates = read_sheet(path)
        if duplicates:
            raise CMHError(f"{path}: duplicate item ids; run 'check' first")
        unknown = set(by_id) - set(key)
        if unknown:
            raise CMHError(f"{path}: {len(unknown)} id(s) not in the key; run 'check' first")
        sheets[rater] = by_id
    raters = list(sheets)
    carried: dict[str, dict[str, str]] = {}
    carry = split_list(args.carry)
    if carry:
        if not args.items:
            raise CMHError("--carry needs --items")
        i_header, i_rows = read_table(args.items)
        require_columns(i_header, [args.id_column, *carry], args.items)
        carried = index_unique(i_rows, args.id_column, args.items)

    merged, expanded = [], []
    for sid in sorted(key):
        ids = key[sid]["item_ids"].split(";")
        row = {"sheet_item_id": sid, "item_ids": key[sid]["item_ids"]}
        votes = []
        for rater in raters:
            entry = sheets[rater].get(sid, {})
            label = entry.get("label", "").strip()
            if label and allowed and label not in allowed:
                raise CMHError(f"rater {rater}: label '{label}' on {sid} is not allowed; run 'check' first")
            row[f"label_{rater}"] = label
            row[f"note_{rater}"] = entry.get("note", "").strip()
            if label:
                votes.append(label)
        counts = Counter(votes)
        top, top_n = (counts.most_common(1)[0] if counts else ("", 0))
        if votes and len(votes) == len(raters) and top_n == len(raters):
            status = "unanimous"
        elif top_n > len(raters) / 2:
            status = "majority"
        else:
            status = "no_majority"
        row.update(majority=top if status != "no_majority" else "", agreement=status,
                   n_labels=len(votes), n_majority=top_n if status != "no_majority" else 0)
        for column in carry:
            values = sorted({carried[i][column] for i in ids if i in carried})
            row[column] = ";".join(values)
        merged.append(row)
        for item_id in ids:
            expanded.append({"item_id": item_id, "sheet_item_id": sid, "majority": row["majority"],
                             "agreement": status, **{f"label_{r}": row[f"label_{r}"] for r in raters}})
    header = ["sheet_item_id", "item_ids", *[f"label_{r}" for r in raters], "majority", "agreement", "n_labels",
              "n_majority", *carry, *[f"note_{r}" for r in raters]]
    write_table(args.out, header, merged)
    if args.expanded_out:
        write_table(args.expanded_out, ["item_id", "sheet_item_id", "majority", "agreement",
                                        *[f"label_{r}" for r in raters]], expanded)
    counts = Counter(row["agreement"] for row in merged)
    print(f"{len(merged)} item(s) merged: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("make", help="make blind sheets and a separate key")
    p.add_argument("--items", required=True, help="CSV of items to judge (any mix of conditions)")
    p.add_argument("--id-column", default="item_id")
    p.add_argument("--show", required=True, help="comma-separated columns annotators see, e.g. text,definition")
    p.add_argument("--dedupe-on", help="columns that identify the same item (default: the --show columns)")
    p.add_argument("--raters", required=True, help="comma-separated rater names, e.g. A,B,C")
    p.add_argument("--out-dir", required=True, help="folder for the sheets (these go to annotators)")
    p.add_argument("--key-dir", required=True, help="folder for the key (keep it away from annotators and git)")
    p.add_argument("--seed", required=True)
    p.add_argument("--labels", default="", help="allowed answers, recorded in the key manifest, e.g. 1,2,3")
    p.add_argument("--sample-n", type=int)
    p.add_argument("--sample-fraction", type=float)
    p.add_argument("--strata", help="column to stratify the sample by")
    p.add_argument("--require", action="append", default=[], metavar="COLUMN=VALUE",
                   help="every item must have this value (repeatable), e.g. lang=ja")
    p.add_argument("--summarize", action="append", default=[], metavar="COLUMN",
                   help="print the distribution of a column before writing (repeatable)")
    p.add_argument("--instructions", help="a file copied next to the sheets, e.g. the annotator guide")
    p.add_argument("--allow-risky-columns", action="store_true")
    p.add_argument("--no-bom", action="store_true", help="write UTF-8 without BOM (spreadsheets prefer the BOM)")
    p.add_argument("--force", action="store_true")

    c = sub.add_parser("check", help="check a returned sheet against its blank")
    c.add_argument("--blank", required=True)
    c.add_argument("--returned", required=True)
    c.add_argument("--labels", default="", help="allowed answers, e.g. 1,2,3")
    c.add_argument("--require-complete", action="store_true", help="treat unlabelled items as a problem")

    m = sub.add_parser("merge", help="unblind: join returned sheets with the key")
    m.add_argument("--key", required=True)
    m.add_argument("--returned", nargs="+", required=True, metavar="RATER=PATH")
    m.add_argument("--labels", default="")
    m.add_argument("--out", required=True)
    m.add_argument("--expanded-out", help="also write one row per original item")
    m.add_argument("--items", help="original items CSV, for --carry")
    m.add_argument("--id-column", default="item_id")
    m.add_argument("--carry", help="columns copied from --items after unblinding, e.g. unit_id,condition")

    args = parser.parse_args()
    return {"make": command_make, "check": command_check, "merge": command_merge}[args.command](args)


if __name__ == "__main__":
    run_cli(main)
