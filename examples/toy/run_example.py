#!/usr/bin/env python3
"""Run the whole CMH workflow on the synthetic toy corpus.

在合成的小语料上把 CMH 流程从头到尾跑一遍。所有句子、年份和“人工判定”都是编的，
只用来演示流程，不是任何真实的考证结果。

The judge and audit "models" are keyword stand-ins and the three readers are
simulated, so the example runs offline in a few seconds. Outputs go to out/.
Read the printed steps alongside references/workflow.md.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SKILL = REPO / "skills" / "cmh-corpus-verification"
SCRIPTS = SKILL / "scripts"
PROTOCOL, DATA, OUT = HERE / "protocol", HERE / "data", HERE / "out"


def shown(value) -> str:
    text = str(value)
    for base, name in ((OUT, "out"), (HERE, "."), (REPO, "<repo>")):
        text = text.replace(str(base), name)
    return text


def step(title: str, script: str, *args) -> None:
    print(f"\n== {title}", flush=True)
    command = [sys.executable, str(SCRIPTS / script), *map(str, args)]
    print("$ " + " ".join(shown(part) for part in [f"python {script}", *map(str, args)]))
    result = subprocess.run(command, text=True, capture_output=True)
    if result.stdout:
        print(shown(result.stdout), end="", flush=True)
    if result.stderr:
        print(shown(result.stderr), end="", flush=True)
    if result.returncode != 0:
        sys.exit(f"step failed: {title}")


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    lock = OUT / "protocol.lock.json"

    step("1. Freeze the protocol before any model runs", "cmh_protocol.py", "freeze",
         "--files", *sorted(PROTOCOL.iterdir()), "--base-dir", PROTOCOL, "--out", lock, "--note", "toy example")

    step("2. Judge layer: label every retrieved instance (definitions must be approved)", "cmh_judge.py", "run",
         "--config", PROTOCOL / "judge.toml", "--instances", DATA / "instances.csv",
         "--definitions", PROTOCOL / "definitions.csv", "--ledger", OUT / "ledger.jsonl",
         "--out", OUT / "labels_judge.csv", "--protocol-lock", lock)

    step("3. Aggregate: earliest attested target-sense instance per unit; abstain without one", "cmh_aggregate.py",
         "earliest", "--labels", OUT / "labels_judge.csv", "--instances", DATA / "instances.csv",
         "--out", OUT / "claims_first_pass.csv", "--positive", "TARGET", "--window-start", "1990")

    step("4. Triage by stated rules, plus a seeded random spot check of unflagged claims", "cmh_triage.py",
         "--claims", OUT / "claims_first_pass.csv", "--units", DATA / "units.csv", "--rules", PROTOCOL / "triage.toml",
         "--out", OUT / "triage.csv", "--seed", "2026", "--spot-check-n", "2")

    instances = {row["instance_id"]: row for row in read(DATA / "instances.csv")}
    triage = read(OUT / "triage.csv")
    review = [instances[row["evidence_instance_id"]] for row in triage if row["review"] == "true"]
    write(OUT / "audit_instances.csv", list(next(iter(instances.values()))), review)
    step("5. Audit layer: a differently configured checker re-reads the review set", "cmh_judge.py", "run",
         "--config", PROTOCOL / "audit.toml", "--instances", OUT / "audit_instances.csv",
         "--definitions", PROTOCOL / "definitions.csv", "--ledger", OUT / "ledger.jsonl",
         "--out", OUT / "labels_audit.csv", "--layer", "audit", "--protocol-lock", lock)

    definitions = {row["unit_id"]: row["definition"] for row in read(PROTOCOL / "definitions.csv")}
    anchors = [instances[row["evidence_instance_id"]] for row in triage if row["status"] == "claimed"]
    items = [{"item_id": a["instance_id"], "unit_id": a["unit_id"], "lang": a["lang"], "form": a["form"],
              "text": a["text"], "definition": definitions[a["unit_id"]]} for a in anchors]
    write(OUT / "sheet_items.csv", ["item_id", "unit_id", "lang", "form", "text", "definition"], items)
    step("6. Blind sheets for three readers; the key goes to a separate folder", "cmh_sheet.py", "make",
         "--items", OUT / "sheet_items.csv", "--show", "form,text,definition", "--raters", "A,B,C",
         "--out-dir", OUT / "sheets", "--key-dir", OUT / "private_key", "--seed", "2026", "--labels", "1,2,3",
         "--summarize", "lang", "--instructions", SKILL / "templates" / "annotator_guide.en.md")

    print("\n== 7. Readers fill in their sheets (simulated here)", flush=True)
    subprocess.run([sys.executable, str(HERE / "simulate_annotators.py"), str(OUT / "sheets"), str(OUT / "returned")],
                   check=True)

    for rater in "ABC":
        step(f"8. Check reader {rater}'s returned sheet", "cmh_sheet.py", "check",
             "--blank", OUT / "sheets" / f"sheet_{rater}.csv", "--returned", OUT / "returned" / f"sheet_{rater}.csv",
             "--labels", "1,2,3", "--require-complete")

    step("9. Unblind and take the majority label", "cmh_sheet.py", "merge", "--key", OUT / "private_key" / "key.csv",
         "--returned", *[f"{r}={OUT / 'returned' / f'sheet_{r}.csv'}" for r in "ABC"], "--labels", "1,2,3",
         "--out", OUT / "truth_sheet.csv", "--expanded-out", OUT / "truth_by_item.csv",
         "--items", OUT / "sheet_items.csv", "--carry", "unit_id,lang")

    step("10. Agreement among the readers (measure humans first)", "cmh_agreement.py",
         "--table", OUT / "truth_sheet.csv", "--raters", "label_A,label_B,label_C", "--categories", "1,2,3",
         "--positive", "1", "--out", OUT / "agreement.json", "--markdown", OUT / "agreement.md")

    truth = {row["item_id"]: row["majority"] for row in read(OUT / "truth_by_item.csv")}
    audit = {row["instance_id"]: row["label"] for row in read(OUT / "labels_audit.csv")}
    decision = {"ACCEPT": "accept", "REJECT": "overturn"}
    evaluation = [{"unit_id": row["unit_id"], "evidence_instance_id": row["evidence_instance_id"],
                   "flagged": row["flagged"], "review": row["review"],
                   "truth": truth.get(row["evidence_instance_id"], "") if truth.get(row["evidence_instance_id"]) in
                   {"1", "2"} else "",
                   "audit": decision.get(audit.get(row["evidence_instance_id"], ""), "")}
                  for row in triage if row["status"] == "claimed"]
    write(OUT / "evaluation.csv", ["unit_id", "evidence_instance_id", "flagged", "review", "truth", "audit"],
          evaluation)
    step("11a. Does triage concentrate errors?", "cmh_evaluate.py", "triage", "--table", OUT / "evaluation.csv",
         "--truth-column", "truth", "--valid-values", "1", "--invalid-values", "2", "--out", OUT / "eval_triage.json")
    step("11b. What did the audit catch, and what did it break?", "cmh_evaluate.py", "audit",
         "--table", OUT / "evaluation.csv", "--truth-column", "truth", "--valid-values", "1", "--invalid-values", "2",
         "--decision-columns", "audit", "--out", OUT / "eval_audit.json")

    labels = read(OUT / "labels_judge.csv")
    for row in labels:
        if audit.get(row["instance_id"]) == "REJECT":
            row["label"] = "OTHER"
    write(OUT / "labels_after_audit.csv", list(labels[0]), labels)
    step("12. Re-aggregate: rejected evidence no longer counts", "cmh_aggregate.py", "earliest",
         "--labels", OUT / "labels_after_audit.csv", "--instances", DATA / "instances.csv",
         "--out", OUT / "claims_after_audit.csv", "--positive", "TARGET", "--window-start", "1990")
    step("12b. What the audit changed", "cmh_check.py", "diff", "--old", OUT / "claims_first_pass.csv",
         "--new", OUT / "claims_after_audit.csv", "--key", "unit_id", "--columns", "value,evidence_instance_id")

    accepted = {i for i, label in audit.items() if label == "ACCEPT"}
    final = []
    for row in read(OUT / "claims_after_audit.csv"):
        final.append({
            "unit_id": row["unit_id"], "status": row["status"], "value": row["value"],
            "value_kind": ("upper_bound" if row["censored"] == "left" else "first_attested_in_corpus")
            if row["status"] == "claimed" else "",
            "censored": row["censored"], "evidence_instance_id": row["evidence_instance_id"],
            "tier": "model_judged_audited" if row["evidence_instance_id"] in accepted else "model_judged",
        })
    write(OUT / "final_table.csv", ["unit_id", "status", "value", "value_kind", "censored", "evidence_instance_id",
                                    "tier"], final)
    step("13. Check the final table against the evidence policy", "cmh_check.py", "run",
         "--table", OUT / "final_table.csv", "--rules", PROTOCOL / "checks.toml", "--key-column", "unit_id")

    step("14. Ledger summary: calls per layer, model and prompt version", "cmh_judge.py", "summary",
         "--ledger", OUT / "ledger.jsonl", "--json", OUT / "ledger_summary.json")

    step("15. Every number in the report traces to an output file", "cmh_numbers.py", "check",
         "--manuscript", HERE / "report.md", "--registry", HERE / "numbers.toml")
    print("\nDone. Outputs are in examples/toy/out/.")


if __name__ == "__main__":
    main()
