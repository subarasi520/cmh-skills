#!/usr/bin/env python3
"""Run a judge or audit model over corpus instances and keep every call.

逐条调用判读层或审计层模型，每一次调用都追加写入台账（JSONL），不覆盖、不丢弃。

  run      label each instance and write a labels table
  dry-run  render the first prompts without calling any model
  summary  count calls per layer, model and prompt version in a ledger

The model only labels instances that code has retrieved from the corpus. It is
never asked to recall dates, sources or facts. Backends:

  openai_compatible  POST {base_url}/chat/completions (local servers such as
                     Ollama, vLLM or llama.cpp, or a hosted API)
  command            run a local program; the prompt is sent on stdin and the
                     reply is read from stdout. No shell is involved.

Only run configuration files you have read: a `command` backend executes the
program named in the file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import string
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmh_common import (  # noqa: E402
    CMHError, __version__, index_unique, load_toml, read_table, require_columns, run_cli,
    sha256_file, sha256_text, utc_now, write_table,
)
from cmh_protocol import locked_files, verify_lock  # noqa: E402

THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S | re.I)
STRIP_CHARS = " \t\r\n\"'`.,:;!?()[]{}<>*_~"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
MAX_CONSECUTIVE_FAILURES = 5


class TransientError(Exception):
    """A failure worth retrying (timeout, connection error, HTTP 429/5xx)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: urllib would forward the Authorization header to the new location."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path).resolve()
    raw = load_toml(path)
    base = path.parent
    backend = dict(raw.get("backend") or {})
    kind = backend.get("type")
    if kind not in {"openai_compatible", "command"}:
        raise CMHError(f"{path}: [backend] type must be 'openai_compatible' or 'command'")
    if not isinstance(backend.get("model"), str) or not backend["model"]:
        raise CMHError(f"{path}: [backend] model is required (for a command backend it is the name recorded in the ledger)")
    backend.setdefault("temperature", 0)
    backend.setdefault("max_tokens", 16)
    backend.setdefault("timeout_seconds", 120)
    backend.setdefault("max_retries", 2)
    backend.setdefault("extra_body", {})
    if kind == "openai_compatible":
        url = backend.get("base_url", "")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise CMHError(f"{path}: [backend] base_url must be an http(s) URL")
        if not isinstance(backend["extra_body"], dict):
            raise CMHError(f"{path}: [backend] extra_body must be a table")
    else:
        argv = backend.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
            raise CMHError(f"{path}: [backend] argv must be a non-empty list of strings")
        backend["argv"] = [sys.executable if item == "${PYTHON}" else item for item in argv]
        backend["cwd"] = str((base / backend.get("cwd", ".")).resolve())

    prompt = raw.get("prompt") or {}
    if "template" not in prompt:
        raise CMHError(f"{path}: [prompt] template is required")
    template_path = (base / prompt["template"]).resolve()
    system_path = (base / prompt["system"]).resolve() if prompt.get("system") else None
    for item in (template_path, system_path):
        if item is not None and not item.is_file():
            raise CMHError(f"{path}: prompt file not found: {item}")
    # [prompt.files]: fixed texts inserted into every prompt, e.g. a codebook.
    prompt_files = {}
    for name, rel in (prompt.get("files") or {}).items():
        file_path = (base / rel).resolve()
        if not file_path.is_file():
            raise CMHError(f"{path}: [prompt.files] {name}: file not found: {file_path}")
        prompt_files[name] = file_path

    labels = raw.get("labels") or {}
    allowed = labels.get("allowed")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(x, str) and x for x in allowed):
        raise CMHError(f"{path}: [labels] allowed must be a non-empty list of strings")
    aliases = labels.get("aliases", {})
    if not isinstance(aliases, dict) or any(target not in allowed for target in aliases.values()):
        raise CMHError(f"{path}: [labels] aliases must map strings to allowed labels")
    match = labels.get("match", "exact")
    if match not in {"exact", "first_line", "search"}:
        raise CMHError(f"{path}: [labels] match must be 'exact', 'first_line' or 'search'")

    columns = raw.get("input") or {}
    definitions = raw.get("definitions") or {}
    run = raw.get("run") or {}
    return {
        "path": path,
        "backend": backend,
        "template_path": template_path,
        "system_path": system_path,
        "prompt_files": prompt_files,
        "allowed": allowed,
        "aliases": aliases,
        "match": match,
        "id_column": columns.get("id_column", "instance_id"),
        "unit_column": columns.get("unit_column", "unit_id"),
        "def_unit_column": definitions.get("unit_column", "unit_id"),
        "def_text_column": definitions.get("text_column", "definition"),
        "def_status_column": definitions.get("status_column", "status"),
        "def_approved": definitions.get("approved_value", "approved"),
        "sleep_seconds": float(run.get("sleep_seconds", 0)),
        "store_prompts": bool(run.get("store_prompts", False)),
    }


# --------------------------------------------------------------------------
# Prompts and labels
# --------------------------------------------------------------------------

def render(template: string.Template, mapping: dict[str, str]) -> str:
    try:
        return template.substitute(mapping)
    except KeyError as exc:
        raise CMHError(f"the prompt template uses ${exc.args[0]}, which is not a column of the input") from exc
    except ValueError as exc:
        raise CMHError(f"bad placeholder in the prompt template: {exc}") from exc


def parse_label(output: str | None, allowed: list[str], aliases: dict[str, str], match: str = "exact") -> str | None:
    """Map raw model output to one allowed label, or None if it cannot be read.

    exact       the whole reply (ignoring surrounding punctuation) is a label
    first_line  the first non-empty line is a label
    search      exactly one distinct label occurs as a separate token; if
                several occur, the one at the very start wins, else None
    `<think>...</think>` blocks are removed first.
    """
    text = THINK_BLOCK.sub("", output or "").strip()
    if not text:
        return None
    vocab = {label.lower(): label for label in allowed}
    vocab.update({alias.lower(): target for alias, target in aliases.items()})

    def lookup(fragment: str) -> str | None:
        return vocab.get(fragment.strip(STRIP_CHARS).lower())

    if match == "exact":
        return lookup(text)
    if match == "first_line":
        first = next((line for line in text.splitlines() if line.strip()), "")
        return lookup(first)
    hits: list[tuple[int, str]] = []
    for token, target in vocab.items():
        pattern = r"(?<![0-9A-Za-z_])" + re.escape(token) + r"(?![0-9A-Za-z_])"
        hits.extend((m.start(), target) for m in re.finditer(pattern, text, flags=re.I))
    if not hits:
        return None
    targets = {target for _, target in hits}
    if len(targets) == 1:
        return targets.pop()
    hits.sort()
    lead = len(text) - len(text.lstrip(STRIP_CHARS))
    return hits[0][1] if hits[0][0] == lead else None


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------

def call_openai_compatible(backend: dict[str, Any], prompt: str, system: str | None) -> str:
    url = backend["base_url"].rstrip("/") + "/chat/completions"
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": backend["model"], "messages": messages, "temperature": backend["temperature"],
            "max_tokens": backend["max_tokens"], **backend["extra_body"]}
    headers = {"Content-Type": "application/json"}
    key_env = backend.get("api_key_env") or ""
    if key_env:
        key = os.environ.get(key_env)
        if not key:
            raise CMHError(f"environment variable {key_env} is not set")
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with _OPENER.open(request, timeout=backend["timeout_seconds"]) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429 or exc.code >= 500:
            raise TransientError(f"HTTP {exc.code}") from exc
        if 300 <= exc.code < 400:
            raise CMHError(f"the server answered with a redirect (HTTP {exc.code}); set base_url to the final "
                           "address. Redirects are not followed so that the API key is not sent elsewhere") from exc
        raise CMHError(f"the model server refused the request: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise TransientError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise TransientError("the server reply was not JSON") from exc
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TransientError("unexpected reply shape (no choices[0].message.content)") from exc
    return content or ""


def call_command(backend: dict[str, Any], prompt: str, system: str | None) -> str:
    text = f"{system}\n\n{prompt}" if system else prompt
    try:
        result = subprocess.run(backend["argv"], input=text, capture_output=True, text=True, encoding="utf-8",
                                timeout=backend["timeout_seconds"], cwd=backend["cwd"], check=False)
    except subprocess.TimeoutExpired as exc:
        raise TransientError("command timed out") from exc
    except OSError as exc:
        raise CMHError(f"cannot run {backend['argv'][0]}: {exc}") from exc
    if result.returncode != 0:
        raise TransientError(f"command exited with {result.returncode}: {result.stderr.strip()[-300:]}")
    return result.stdout


def call_with_retries(backend: dict[str, Any], prompt: str, system: str | None) -> tuple[str | None, str | None]:
    """Return (output, error). Permanent errors raise CMHError and stop the run."""
    caller = call_openai_compatible if backend["type"] == "openai_compatible" else call_command
    attempts = 1 + int(backend["max_retries"])
    last_error = None
    for attempt in range(attempts):
        try:
            return caller(backend, prompt, system), None
        except TransientError as exc:
            last_error = str(exc)
            if attempt + 1 < attempts:
                time.sleep(min(30, 2 ** attempt))
    return None, last_error


def warn_insecure_transport(backend: dict[str, Any]) -> None:
    if backend["type"] != "openai_compatible" or not backend.get("api_key_env"):
        return
    parsed = urllib.parse.urlparse(backend["base_url"])
    if parsed.scheme == "http" and parsed.hostname not in LOCAL_HOSTS:
        print("warning: an API key would be sent over plain http to a remote host; use https", file=sys.stderr)


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------

def read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"warning: {path}: skipping unreadable line {line_no}", file=sys.stderr)
    return records


def call_key(record: dict[str, Any]) -> tuple:
    return (record.get("layer"), record.get("instance_id"), record.get("model"),
            record.get("template_sha256"), record.get("prompt_sha256"))


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def prepare(config: dict[str, Any], instances_path: str, definitions_path: str | None, allow_unreviewed: bool):
    header, rows = read_table(instances_path)
    require_columns(header, [config["id_column"], config["unit_column"]], instances_path)
    index_unique(rows, config["id_column"], instances_path)
    definitions: dict[str, dict[str, str]] = {}
    if definitions_path:
        if "definition" in header:
            raise CMHError("the instances table already has a 'definition' column; drop it or omit --definitions")
        def_header, def_rows = read_table(definitions_path)
        require_columns(def_header, [config["def_unit_column"], config["def_text_column"],
                                     config["def_status_column"]], definitions_path)
        definitions = index_unique(def_rows, config["def_unit_column"], definitions_path)
        units = {row[config["unit_column"]] for row in rows}
        missing = sorted(units - definitions.keys())
        if missing:
            raise CMHError(f"no definition for {len(missing)} unit(s), e.g. {', '.join(missing[:10])}")
        unreviewed = sorted(unit for unit in units
                            if definitions[unit][config["def_status_column"]] != config["def_approved"])
        if unreviewed and not allow_unreviewed:
            raise CMHError(f"{len(unreviewed)} definition(s) are not marked "
                           f"{config['def_status_column']}={config['def_approved']}, e.g. {', '.join(unreviewed[:10])}. "
                           "A researcher must review definitions before models use them "
                           "(--allow-unreviewed runs anyway and records the status in the ledger)")
    clash = [name for name in config["prompt_files"] if name in header or (definitions and name == "definition")]
    if clash:
        raise CMHError(f"[prompt.files] name(s) {', '.join(clash)} are also columns of the input")
    config["fixed_texts"] = {name: p.read_text(encoding="utf-8") for name, p in config["prompt_files"].items()}
    template = string.Template(config["template_path"].read_text(encoding="utf-8"))
    system = config["system_path"].read_text(encoding="utf-8") if config["system_path"] else None
    return rows, definitions, template, system


def mapping_for(row: dict[str, str], definitions: dict[str, dict[str, str]], config: dict[str, Any]) -> dict[str, str]:
    mapping = dict(row)
    mapping.update(config.get("fixed_texts", {}))
    if definitions:
        mapping["definition"] = definitions[row[config["unit_column"]]][config["def_text_column"]]
    return mapping


def check_protocol(lock: str | None, config: dict[str, Any], extra_files: list[str]) -> str | None:
    if not lock:
        print("note: no --protocol-lock given; treat this run as exploratory", file=sys.stderr)
        return None
    problems = verify_lock(lock)
    if problems:
        raise CMHError("the protocol changed since it was frozen: " + "; ".join(problems))
    covered = locked_files(lock)
    wanted = [config["path"], config["template_path"], config["system_path"], *config["prompt_files"].values(),
              *map(Path, extra_files)]
    uncovered = [str(p) for p in wanted if p is not None and Path(p).resolve() not in covered]
    if uncovered:
        print("warning: not covered by the protocol lock: " + ", ".join(uncovered), file=sys.stderr)
    return sha256_file(lock)


def template_version(config: dict[str, Any]) -> str:
    """Hash of the prompt template, combined with any [prompt.files] texts."""
    if not config["prompt_files"]:
        return sha256_file(config["template_path"])
    parts = [sha256_file(config["template_path"])]
    parts += [sha256_file(path) for _, path in sorted(config["prompt_files"].items())]
    return sha256_text(json.dumps(parts))


def command_run(args) -> int:
    config = load_config(args.config)
    warn_insecure_transport(config["backend"])
    extra = [args.definitions] if args.definitions else []
    lock_sha = check_protocol(args.protocol_lock, config, extra)
    rows, definitions, template, system = prepare(config, args.instances, args.definitions, args.allow_unreviewed)
    template_sha = template_version(config)
    system_sha = sha256_file(config["system_path"]) if config["system_path"] else None
    ledger_path = Path(args.ledger)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    backend = config["backend"]

    previous = read_ledger(ledger_path)
    done = {call_key(rec) for rec in previous if rec.get("label") is not None
            or (rec.get("error") is None and not args.retry_unparsed)}
    latest: dict[tuple, dict[str, Any]] = {}
    for rec in previous:
        latest[call_key(rec)] = rec

    todo = rows[: args.limit] if args.limit else rows
    calls = failures_in_a_row = 0
    keys_for_rows: list[tuple] = []
    with ledger_path.open("a", encoding="utf-8") as ledger:
        for row in todo:
            prompt = render(template, mapping_for(row, definitions, config))
            prompt_sha = sha256_text(json.dumps({"system": system, "user": prompt}, ensure_ascii=False))
            key = (args.layer, row[config["id_column"]], backend["model"], template_sha, prompt_sha)
            keys_for_rows.append(key)
            if key in done:
                continue
            started = time.monotonic()
            output, error = call_with_retries(backend, prompt, system)
            label = parse_label(output, config["allowed"], config["aliases"], config["match"]) if error is None else None
            record = {
                "call_id": uuid.uuid4().hex,
                "time_utc": utc_now(),
                "layer": args.layer,
                "instance_id": row[config["id_column"]],
                "unit_id": row[config["unit_column"]],
                "backend": backend["type"],
                "model": backend["model"],
                "params": {"temperature": backend["temperature"], "max_tokens": backend["max_tokens"],
                           "extra_body": backend.get("extra_body", {})},
                "template_sha256": template_sha,
                "system_sha256": system_sha,
                "prompt_sha256": prompt_sha,
                "protocol_lock_sha256": lock_sha,
                "definition_status": (definitions[row[config["unit_column"]]][config["def_status_column"]]
                                      if definitions else None),
                "raw_output": output,
                "label": label,
                "error": error,
                "latency_seconds": round(time.monotonic() - started, 3),
                "tool_version": __version__,
            }
            if config["store_prompts"]:
                record["prompt"] = prompt
            ledger.write(json.dumps(record, ensure_ascii=False) + "\n")
            ledger.flush()
            latest[key] = record
            calls += 1
            failures_in_a_row = failures_in_a_row + 1 if error else 0
            if failures_in_a_row >= MAX_CONSECUTIVE_FAILURES:
                raise CMHError(f"{failures_in_a_row} calls in a row failed (last error: {error}); "
                               "stopping. Fix the backend and run again; finished calls are kept")
            if calls % 50 == 0:
                print(f"{calls} calls made", file=sys.stderr)
            if config["sleep_seconds"]:
                time.sleep(config["sleep_seconds"])

    out_rows = []
    counts = defaultdict(int)
    for row, key in zip(todo, keys_for_rows):
        rec = latest.get(key)
        if rec is None:
            status = "missing"
        elif rec.get("error"):
            status = "error"
        elif rec.get("label") is None:
            status = "unparsed"
        else:
            status = "ok"
        counts[status] += 1
        out_rows.append({
            "instance_id": row[config["id_column"]],
            "unit_id": row[config["unit_column"]],
            "layer": args.layer,
            "model": backend["model"],
            "label": rec.get("label") or "" if rec else "",
            "status": status,
            "call_id": rec["call_id"] if rec else "",
            "template_sha256": template_sha,
        })
    write_table(args.out, ["instance_id", "unit_id", "layer", "model", "label", "status", "call_id",
                           "template_sha256"], out_rows)
    summary = ", ".join(f"{name} {count}" for name, count in sorted(counts.items()))
    print(f"{calls} new call(s); labels written to {args.out} ({summary})")
    return 0


def command_dry_run(args) -> int:
    config = load_config(args.config)
    rows, definitions, template, system = prepare(config, args.instances, args.definitions, True)
    for row in rows[: args.n]:
        print(f"===== {row[config['id_column']]} =====")
        if system:
            print("[system]\n" + system)
        print(render(template, mapping_for(row, definitions, config)))
    return 0


def command_summary(args) -> int:
    records = read_ledger(Path(args.ledger))
    groups: dict[tuple, dict[str, Any]] = {}
    for rec in records:
        key = (rec.get("layer"), rec.get("model"), (rec.get("template_sha256") or "")[:12])
        g = groups.setdefault(key, {"calls": 0, "labelled": 0, "unparsed": 0, "errors": 0, "instances": set(),
                                    "first_utc": rec.get("time_utc"), "last_utc": rec.get("time_utc"),
                                    "latency_seconds": 0.0})
        g["calls"] += 1
        if rec.get("error"):
            g["errors"] += 1
        elif rec.get("label") is None:
            g["unparsed"] += 1
        else:
            g["labelled"] += 1
        g["instances"].add(rec.get("instance_id"))
        g["first_utc"] = min(g["first_utc"] or "", rec.get("time_utc") or "")
        g["last_utc"] = max(g["last_utc"] or "", rec.get("time_utc") or "")
        g["latency_seconds"] += float(rec.get("latency_seconds") or 0)
    print("| layer | model | prompt | calls | labelled | unparsed | errors | instances | first | last |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    result = []
    for (layer, model, prompt), g in sorted(groups.items(), key=lambda item: tuple(map(str, item[0]))):
        print(f"| {layer} | {model} | {prompt} | {g['calls']} | {g['labelled']} | {g['unparsed']} | "
              f"{g['errors']} | {len(g['instances'])} | {g['first_utc']} | {g['last_utc']} |")
        result.append({"layer": layer, "model": model, "template_sha256_prefix": prompt,
                       **{k: v for k, v in g.items() if k != "instances"}, "instances": len(g["instances"])})
    versions = defaultdict(set)
    for layer, _model, prompt in groups:
        versions[layer].add(prompt)
    for layer, prompts in versions.items():
        if len(prompts) > 1:
            print(f"\nnote: layer '{layer}' has {len(prompts)} prompt versions in this ledger; "
                  "report labels from one frozen version only")
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="label instances; every call goes to the ledger")
    p_run.add_argument("--config", required=True, help="judge or audit TOML file")
    p_run.add_argument("--instances", required=True, help="CSV with one row per corpus instance")
    p_run.add_argument("--definitions", help="CSV with a reviewed definition per unit")
    p_run.add_argument("--ledger", required=True, help="JSONL file that receives every call (appended)")
    p_run.add_argument("--out", required=True, help="labels CSV to write")
    p_run.add_argument("--layer", default="judge", help="layer name recorded with each call (judge, audit, ...)")
    p_run.add_argument("--protocol-lock", help="lock file from cmh_protocol.py; the run stops if files changed")
    p_run.add_argument("--allow-unreviewed", action="store_true", help="run even if definitions are not approved")
    p_run.add_argument("--retry-unparsed", action="store_true", help="call again where an earlier reply was unreadable")
    p_run.add_argument("--limit", type=int, help="only the first N instances (for a pilot)")

    p_dry = sub.add_parser("dry-run", help="print rendered prompts without calling a model")
    p_dry.add_argument("--config", required=True)
    p_dry.add_argument("--instances", required=True)
    p_dry.add_argument("--definitions")
    p_dry.add_argument("--n", type=int, default=3)

    p_sum = sub.add_parser("summary", help="summarise a ledger")
    p_sum.add_argument("--ledger", required=True)
    p_sum.add_argument("--json", help="also write the summary as JSON")

    args = parser.parse_args()
    return {"run": command_run, "dry-run": command_dry_run, "summary": command_summary}[args.command](args)


if __name__ == "__main__":
    run_cli(main)
