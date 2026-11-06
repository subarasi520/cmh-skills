"""Shared helpers for the CMH scripts.

CMH 脚本共用的工具函数：读写表格、哈希、条件判断、带种子的抽样、运行清单。

Standard library only. Requires Python 3.11+ (for tomllib).
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import os
import random
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterable, Sequence

__version__ = "0.1.0"

# Cells starting with these characters can be interpreted as formulas by
# spreadsheet programs (CSV/formula injection). Sheets meant for humans are
# escaped with a leading apostrophe.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

TRUE_VALUES = {"true", "1", "yes", "y"}
FALSE_VALUES = {"false", "0", "no", "n", ""}

_EXTRA = "__extra_cells__"

# Documents (speeches, articles) can exceed the csv module's default cell limit.
try:
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
except OverflowError:  # pragma: no cover - platform dependent
    csv.field_size_limit(2**31 - 1)


class CMHError(Exception):
    """A user-facing error: bad input, a failed check, or a refused action."""


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

def read_table(path: str | os.PathLike) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV file (UTF-8, BOM tolerated) into (header, rows).

    Every cell is a string. Short rows are padded with "". Rows with more cells
    than the header, duplicate column names and empty files are errors.
    """
    path = Path(path)
    if not path.is_file():
        raise CMHError(f"{path}: file not found")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, restkey=_EXTRA, restval="")
        header = reader.fieldnames
        if not header:
            raise CMHError(f"{path}: empty file or missing header row")
        header = [name.strip() for name in header]
        seen: set[str] = set()
        for name in header:
            if name in seen:
                raise CMHError(f"{path}: duplicate column name '{name}'")
            seen.add(name)
        reader.fieldnames = header
        rows: list[dict[str, str]] = []
        for line_no, raw in enumerate(reader, start=2):
            if raw.get(_EXTRA):
                raise CMHError(f"{path}: line {line_no} has more cells than the header")
            raw.pop(_EXTRA, None)
            rows.append({key: ("" if value is None else value) for key, value in raw.items()})
    return list(header), rows


def write_table(
    path: str | os.PathLike,
    header: Sequence[str],
    rows: Iterable[dict[str, Any]],
    *,
    excel_safe: bool = False,
    bom: bool = False,
) -> None:
    """Write rows to CSV. Unknown keys are an error; missing keys become ""."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if bom else "utf-8"
    with path.open("w", newline="", encoding=encoding) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(header), extrasaction="raise", restval="")
        writer.writeheader()
        for row in rows:
            out = {key: as_str(value) for key, value in row.items()}
            if excel_safe:
                out = {key: escape_formula(value) for key, value in out.items()}
            writer.writerow(out)


def require_columns(header: Sequence[str], needed: Iterable[str], where: str) -> None:
    missing = [name for name in needed if name not in header]
    if missing:
        raise CMHError(f"{where}: missing column(s): {', '.join(missing)}")


def index_unique(rows: Sequence[dict[str, str]], column: str, where: str) -> dict[str, dict[str, str]]:
    """Map column value -> row, refusing empty or duplicate keys."""
    out: dict[str, dict[str, str]] = {}
    for line_no, row in enumerate(rows, start=2):
        key = row.get(column, "")
        if key == "":
            raise CMHError(f"{where}: empty '{column}' on line {line_no}")
        if key in out:
            raise CMHError(f"{where}: duplicate '{column}' value '{key}' (line {line_no})")
        out[key] = row
    return out


def escape_formula(value: str) -> str:
    """Prefix an apostrophe to cells a spreadsheet could run as a formula."""
    if value and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def unescape_formula(value: str) -> str:
    if value.startswith("'") and value[1:2] and value[1:].startswith(FORMULA_PREFIXES):
        return value[1:]
    return value


def as_str(value: Any) -> str:
    """Canonical string form used in every CSV the scripts write."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        return repr(value) if abs(value) >= 1e-4 or value == 0 else f"{value:.6g}"
    return str(value)


def parse_bool(value: str, where: str = "") -> bool:
    lowered = value.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    raise CMHError(f"{where}: cannot read '{value}' as true/false")


def split_list(value: str | None) -> list[str]:
    """Split a comma-separated command-line value, dropping empty items."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


# --------------------------------------------------------------------------
# Files, hashes, manifests
# --------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | os.PathLike) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_toml(path: str | os.PathLike) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise CMHError(f"{path}: file not found")
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise CMHError(f"{path}: invalid TOML: {exc}") from exc


def json_safe(obj: Any) -> Any:
    """Replace NaN and infinities (not valid JSON) with None, recursively."""
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return None
    if isinstance(obj, dict):
        return {key: json_safe(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(value) for value in obj]
    if isinstance(obj, set):
        return sorted(json_safe(value) for value in obj)
    return obj


def write_json(path: str | os.PathLike, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(json_safe(obj), ensure_ascii=False, indent=2, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def manifest(tool: str, arguments: dict[str, Any], inputs: dict[str, str | os.PathLike], **extra: Any) -> dict[str, Any]:
    """A record of how an output was produced: tool, arguments, input hashes."""
    return {
        "tool": tool,
        "tool_version": __version__,
        "created_utc": utc_now(),
        "python": sys.version.split()[0],
        "arguments": {key: as_str(value) if not isinstance(value, (list, dict)) else value
                      for key, value in arguments.items()},
        "inputs": {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in inputs.items()},
        **extra,
    }


def find_git_root(path: str | os.PathLike) -> Path | None:
    current = Path(path).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def is_within(child: str | os.PathLike, parent: str | os.PathLike) -> bool:
    child_path = Path(child).resolve()
    parent_path = Path(parent).resolve()
    return child_path == parent_path or parent_path in child_path.parents


# --------------------------------------------------------------------------
# Conditions (used by triage rules and table checks)
# --------------------------------------------------------------------------

NUMERIC_OPS = {"lt", "le", "gt", "ge"}
LENGTH_OPS = {"len_lt", "len_le", "len_gt", "len_ge", "len_eq"}
CONDITION_OPS = {"eq", "ne", "in", "not_in", "empty", "not_empty", "regex", "not_regex"} | NUMERIC_OPS | LENGTH_OPS


def to_number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_condition(cond: dict[str, Any], where: str) -> None:
    if not isinstance(cond, dict):
        raise CMHError(f"{where}: a condition must be a table like {{ column = ..., op = ... }}")
    if "column" not in cond or "op" not in cond:
        raise CMHError(f"{where}: a condition needs 'column' and 'op'")
    op = cond["op"]
    if op not in CONDITION_OPS:
        raise CMHError(f"{where}: unknown op '{op}' (known: {', '.join(sorted(CONDITION_OPS))})")
    if op not in {"empty", "not_empty"} and "value" not in cond:
        raise CMHError(f"{where}: op '{op}' needs a 'value'")
    if op in {"in", "not_in"} and not isinstance(cond["value"], list):
        raise CMHError(f"{where}: op '{op}' needs a list value")
    if op in NUMERIC_OPS and to_number(as_str(cond["value"])) is None:
        raise CMHError(f"{where}: op '{op}' needs a numeric value")
    if op in LENGTH_OPS and not isinstance(cond["value"], int):
        raise CMHError(f"{where}: op '{op}' needs an integer value")
    if op in {"regex", "not_regex"}:
        try:
            re.compile(str(cond["value"]))
        except re.error as exc:
            raise CMHError(f"{where}: bad regex: {exc}") from exc


def check_condition(row: dict[str, str], cond: dict[str, Any]) -> bool:
    """Evaluate one condition against a row of strings.

    Numeric comparisons are False when the cell is empty or not a number, so a
    rule never fires on missing data by accident.
    """
    column = cond["column"]
    if column not in row:
        raise CMHError(f"condition refers to missing column '{column}'")
    cell = row[column]
    op = cond["op"]
    value = cond.get("value")
    if op == "eq":
        return cell == as_str(value)
    if op == "ne":
        return cell != as_str(value)
    if op == "in":
        return cell in {as_str(item) for item in value}
    if op == "not_in":
        return cell not in {as_str(item) for item in value}
    if op == "empty":
        return cell.strip() == ""
    if op == "not_empty":
        return cell.strip() != ""
    if op == "regex":
        return re.search(str(value), cell) is not None
    if op == "not_regex":
        return re.search(str(value), cell) is None
    if op in NUMERIC_OPS:
        left = to_number(cell)
        right = to_number(as_str(value))
        if left is None or right is None:
            return False
        return {"lt": left < right, "le": left <= right, "gt": left > right, "ge": left >= right}[op]
    if op in LENGTH_OPS:
        size = len(cell)
        limit = int(value)
        return {"len_lt": size < limit, "len_le": size <= limit, "len_gt": size > limit,
                "len_ge": size >= limit, "len_eq": size == limit}[op]
    raise CMHError(f"unknown op '{op}'")


def check_all(row: dict[str, str], conditions: Sequence[dict[str, Any]]) -> bool:
    return all(check_condition(row, cond) for cond in conditions)


# --------------------------------------------------------------------------
# Seeded sampling
# --------------------------------------------------------------------------

def make_rng(seed: int | str) -> random.Random:
    """A random generator whose output does not depend on PYTHONHASHSEED."""
    return random.Random(str(seed))


def allocate_proportional(sizes: dict[str, int], total: int) -> dict[str, int]:
    """Split `total` across strata in proportion to size (largest remainder)."""
    population = sum(sizes.values())
    if total > population:
        raise CMHError(f"cannot sample {total} from {population} rows")
    quotas = {name: total * size / population for name, size in sizes.items()}
    alloc = {name: int(quota) for name, quota in quotas.items()}
    remaining = total - sum(alloc.values())
    order = sorted(quotas, key=lambda name: (-(quotas[name] - alloc[name]), name))
    for name in order[:remaining]:
        alloc[name] += 1
    return alloc


def sample_rows(
    rows: Sequence[dict[str, str]],
    *,
    id_column: str,
    seed: int | str,
    n: int | None = None,
    fraction: float | None = None,
    strata_column: str | None = None,
) -> list[dict[str, str]]:
    """Draw a reproducible simple or stratified random sample without replacement.

    Rows are sorted by `id_column` before sampling, so the result depends only on
    the data and the seed, never on file order or set iteration order.
    """
    if (n is None) == (fraction is None):
        raise CMHError("give exactly one of n or fraction")
    ordered = sorted(rows, key=lambda row: row[id_column])
    total = n if n is not None else round(len(ordered) * fraction)
    if total < 0 or total > len(ordered):
        raise CMHError(f"cannot sample {total} from {len(ordered)} rows")
    rng = make_rng(seed)
    if not strata_column:
        return rng.sample(ordered, total)
    groups: dict[str, list[dict[str, str]]] = {}
    for row in ordered:
        groups.setdefault(row[strata_column], []).append(row)
    alloc = allocate_proportional({name: len(members) for name, members in groups.items()}, total)
    picked: list[dict[str, str]] = []
    for name in sorted(groups):
        picked.extend(rng.sample(groups[name], alloc[name]))
    return picked


def run_cli(main) -> None:
    """Run a CLI entry point, turning CMHError into a clean message and exit code 2."""
    try:
        code = main()
    except CMHError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(code or 0)
