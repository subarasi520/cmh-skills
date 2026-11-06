"""Fill blank sheets the way three human readers might (toy example only).

Real annotators read the sheets themselves. Here readers A and C copy a
hidden answer list and reader B disagrees on two items, so the agreement
numbers are not trivially perfect.
"""
import csv
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
sheets, returned = Path(sys.argv[1]), Path(sys.argv[2])
with (here / "data" / "instances.csv").open(encoding="utf-8") as handle:
    text_to_id = {row["text"]: row["instance_id"] for row in csv.DictReader(handle)}
with (here / "data" / "toy_gold.csv").open(encoding="utf-8") as handle:
    gold = {row["instance_id"]: row["gold"] for row in csv.DictReader(handle)}
reader_b = {"c2": "1", "y2": "3"}

returned.mkdir(parents=True, exist_ok=True)
for rater in ("A", "B", "C"):
    with (sheets / f"sheet_{rater}.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        instance = text_to_id[row["text"]]
        row["label"] = reader_b.get(instance, gold[instance]) if rater == "B" else gold[instance]
    with (returned / f"sheet_{rater}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
print(f"filled sheets for readers A, B, C in {returned}")
