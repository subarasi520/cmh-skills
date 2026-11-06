"""Tests for aggregate, triage, sheet, agreement, evaluate, check and numbers."""

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from helpers import read_csv, run_script, write_csv


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result


class AggregateTests(Base):
    def setUp(self):
        super().setUp()
        write_csv(self.dir / "instances.csv", ["instance_id", "unit_id", "time", "period"], [
            ["a1", "u1", "1950", "p1"], ["a2", "u1", "1962", "p1"], ["a3", "u1", "1975", "p2"],
            ["b1", "u2", "1951-04", "p1"], ["b2", "u2", "1960", "p2"],
            ["c1", "u3", "1970", "p2"],
        ])
        write_csv(self.dir / "labels.csv", ["instance_id", "unit_id", "label", "status"], [
            ["a1", "u1", "OTHER", "ok"], ["a2", "u1", "TARGET", "ok"], ["a3", "u1", "TARGET", "ok"],
            ["b1", "u2", "TARGET", "ok"], ["b2", "u2", "", "unparsed"],
            ["c1", "u3", "OTHER", "ok"],
        ])

    def agg(self, command, *extra):
        out = self.dir / f"{command}.csv"
        self.ok(run_script("cmh_aggregate.py", command, "--labels", self.dir / "labels.csv", "--instances",
                           self.dir / "instances.csv", "--out", out, "--positive", "TARGET", *extra))
        return {row.get("unit_id", ""): row for row in read_csv(out)}, out

    def test_earliest(self):
        rows, out = self.agg("earliest", "--window-start", "1951")
        self.assertEqual(rows["u1"]["value"], "1962")
        self.assertEqual(rows["u1"]["evidence_instance_id"], "a2")
        self.assertEqual(rows["u1"]["gap_to_next_positive"], "13")
        self.assertEqual(rows["u1"]["censored"], "")
        self.assertEqual(rows["u2"]["censored"], "left")  # 1951-04 sits in the first window year
        self.assertEqual(rows["u3"]["status"], "abstained")
        self.assertEqual(rows["u3"]["reason"], "no_positive_instance")
        self.assertTrue(Path(str(out) + ".manifest.json").exists())

    def test_min_positive(self):
        rows, _ = self.agg("earliest", "--min-positive", "2")
        self.assertEqual(rows["u2"]["reason"], "too_few_positive")
        self.assertEqual(rows["u1"]["status"], "claimed")

    def test_proportion_and_presence(self):
        out = self.dir / "shares.csv"
        self.ok(run_script("cmh_aggregate.py", "proportion", "--labels", self.dir / "labels.csv", "--instances",
                           self.dir / "instances.csv", "--out", out, "--positive", "TARGET",
                           "--group-columns", "period", "--min-n", "3"))
        shares = {row["period"]: row for row in read_csv(out)}
        self.assertEqual(shares["p1"]["n_positive"], "2")
        self.assertEqual(shares["p1"]["denominator"], "3")
        self.assertEqual(shares["p1"]["status"], "ok")
        self.assertEqual(shares["p2"]["status"], "insufficient_n")
        rows, _ = self.agg("presence", "--group-columns", "unit_id")
        self.assertEqual(rows["u3"]["status"], "not_observed")

    def test_bad_time_rejected(self):
        write_csv(self.dir / "instances.csv", ["instance_id", "unit_id", "time"], [["a1", "u1", "late 1950s"]])
        write_csv(self.dir / "labels.csv", ["instance_id", "unit_id", "label", "status"], [["a1", "u1", "TARGET", "ok"]])
        result = run_script("cmh_aggregate.py", "earliest", "--labels", self.dir / "labels.csv", "--instances",
                            self.dir / "instances.csv", "--out", self.dir / "x.csv", "--positive", "TARGET")
        self.assertEqual(result.returncode, 2)


class TriageTests(Base):
    def test_rules_and_spot_check(self):
        write_csv(self.dir / "claims.csv", ["unit_id", "status", "censored", "gap_to_next_positive"],
                  [[f"u{i:02d}", "claimed" if i < 18 else "abstained", "left" if i == 1 else "",
                    "25" if i == 2 else "1"] for i in range(20)])
        write_csv(self.dir / "units.csv", ["unit_id", "form"], [[f"u{i:02d}", "ab" if i == 3 else "abcd"]
                                                               for i in range(20)])
        (self.dir / "rules.toml").write_text(textwrap.dedent('''
            [[rule]]
            name = "short_form"
            conditions = [{ column = "form", op = "len_le", value = 2 }]
            [[rule]]
            name = "window_edge"
            conditions = [{ column = "censored", op = "eq", value = "left" }]
            [[rule]]
            name = "isolated_anchor"
            conditions = [{ column = "gap_to_next_positive", op = "gt", value = 10 }]
        '''), encoding="utf-8")

        def triage(out):
            self.ok(run_script("cmh_triage.py", "--claims", self.dir / "claims.csv", "--rules",
                               self.dir / "rules.toml", "--units", self.dir / "units.csv", "--out", out,
                               "--seed", "42", "--spot-check-n", "5"))
            return {row["unit_id"]: row for row in read_csv(out)}

        first = triage(self.dir / "t1.csv")
        self.assertEqual({k for k, r in first.items() if r["flagged"] == "true"}, {"u01", "u02", "u03"})
        self.assertEqual(first["u03"]["flag_reasons"], "short_form")
        spot = {k for k, r in first.items() if r["spot_check"] == "true"}
        self.assertEqual(len(spot), 5)
        self.assertFalse(spot & {"u01", "u02", "u03", "u18", "u19"})
        second = triage(self.dir / "t2.csv")
        self.assertEqual(spot, {k for k, r in second.items() if r["spot_check"] == "true"})


class SheetTests(Base):
    def setUp(self):
        super().setUp()
        write_csv(self.dir / "items.csv", ["item_id", "unit_id", "text", "definition", "condition", "lang"], [
            ["x1", "u1", "click the mouse", "pointing device", "C1", "en"],
            ["x2", "u1", "click the mouse", "pointing device", "C2", "en"],
            ["x3", "u2", "=HYPERLINK(\"http://example.invalid\")", "formula text", "C1", "en"],
            ["x4", "u3", "the cat chased a mouse", "pointing device", "C2", "en"],
        ])

    def make(self, *extra, key_dir=None):
        return run_script("cmh_sheet.py", "make", "--items", self.dir / "items.csv", "--show", "text,definition",
                          "--raters", "A,B", "--out-dir", self.dir / "sheets",
                          "--key-dir", key_dir or (self.dir / "private"), "--seed", "9", "--labels", "1,2,3", *extra)

    def test_make_check_merge(self):
        self.ok(self.make("--require", "lang=en"))
        sheet_a = read_csv(self.dir / "sheets" / "sheet_A.csv")
        self.assertEqual(len(sheet_a), 3)  # x1 and x2 are the same text: shown once
        self.assertEqual(set(sheet_a[0]), {"sheet_item_id", "text", "definition", "label", "note"})
        formula = [row for row in sheet_a if "HYPERLINK" in row["text"]][0]
        self.assertTrue(formula["text"].startswith("'="))
        key = read_csv(self.dir / "private" / "key.csv")
        self.assertIn("x1;x2", [row["item_ids"] for row in key])

        for rater, answers in (("A", ["1", "2", "1"]), ("B", ["1", "2", "2"])):
            rows = read_csv(self.dir / "sheets" / f"sheet_{rater}.csv")
            for row, answer in zip(sorted(rows, key=lambda r: r["sheet_item_id"]), answers):
                row["label"] = answer
            write_csv(self.dir / "returned" / f"sheet_{rater}.csv", list(rows[0]), [list(r.values()) for r in rows])
            self.ok(run_script("cmh_sheet.py", "check", "--blank", self.dir / "sheets" / f"sheet_{rater}.csv",
                               "--returned", self.dir / "returned" / f"sheet_{rater}.csv", "--labels", "1,2,3"))
        merged = self.dir / "merged.csv"
        self.ok(run_script("cmh_sheet.py", "merge", "--key", self.dir / "private" / "key.csv", "--returned",
                           f"A={self.dir / 'returned' / 'sheet_A.csv'}", f"B={self.dir / 'returned' / 'sheet_B.csv'}",
                           "--labels", "1,2,3", "--out", merged, "--items", self.dir / "items.csv",
                           "--carry", "unit_id,condition", "--expanded-out", self.dir / "by_item.csv"))
        rows = read_csv(merged)
        self.assertEqual(sorted(r["agreement"] for r in rows), ["no_majority", "unanimous", "unanimous"])
        self.assertIn("C1;C2", [r["condition"] for r in rows])
        self.assertEqual(len(read_csv(self.dir / "by_item.csv")), 4)

    def test_check_detects_edits_and_bad_labels(self):
        self.ok(self.make())
        rows = read_csv(self.dir / "sheets" / "sheet_A.csv")
        rows[0]["text"] = "edited"
        rows[1]["label"] = "7"
        write_csv(self.dir / "ret.csv", list(rows[0]), [list(r.values()) for r in rows])
        result = run_script("cmh_sheet.py", "check", "--blank", self.dir / "sheets" / "sheet_A.csv",
                            "--returned", self.dir / "ret.csv", "--labels", "1,2,3")
        self.assertEqual(result.returncode, 1)
        self.assertIn("edited text", result.stdout)
        self.assertIn("outside", result.stdout)

    def test_refusals(self):
        self.assertEqual(self.make(key_dir=self.dir / "sheets" / "key").returncode, 2)
        risky = run_script("cmh_sheet.py", "make", "--items", self.dir / "items.csv", "--show", "text,condition",
                           "--raters", "A", "--out-dir", self.dir / "s2", "--key-dir", self.dir / "k2", "--seed", "1")
        self.assertEqual(risky.returncode, 2)
        self.assertIn("condition", risky.stderr)
        self.assertEqual(self.make("--require", "lang=ja").returncode, 2)
        self.ok(self.make())
        self.assertEqual(self.make().returncode, 2)  # no silent regeneration


class AgreementEvaluateTests(Base):
    def test_agreement_cli(self):
        rows = [[f"i{n}", f"u{n % 5}", "Y", "Y", "Y"] for n in range(20)]
        rows += [[f"j{n}", f"u{n % 5}", "N", "N", "Y"] for n in range(10)]
        rows += [[f"k{n}", f"u{n % 5}", "N", "Y", "N"] for n in range(5)]
        rows += [[f"m{n}", f"u{n % 5}", "Y", "N", "N"] for n in range(5)]
        write_csv(self.dir / "wide.csv", ["item", "unit", "A", "B", "model"], rows)
        out = self.dir / "agreement.json"
        self.ok(run_script("cmh_agreement.py", "--table", self.dir / "wide.csv", "--raters", "A,B,model",
                           "--positive", "Y", "--categories", "Y,N", "--cluster", "unit", "--bootstrap", "200",
                           "--seed", "3", "--out", out))
        data = json.loads(out.read_text())["agreement"]
        ab = data["pairs"]["A|B"]
        self.assertEqual(ab["n"], 40)
        self.assertAlmostEqual(ab["observed_agreement"], 30 / 40)
        self.assertIn("ci_low", ab["bootstrap"]["cohen_kappa"])
        self.assertIn("fleiss_kappa", data)

    def test_evaluate_triage_audit_compare(self):
        rows = [["f", "true", "2", "overturn", "overturn"]] * 6 + [["f2", "true", "1", "accept", "overturn"]] * 4
        rows += [["u", "false", "2", "accept", "overturn"]] * 3 + [["u2", "false", "1", "accept", "accept"]] * 37
        write_csv(self.dir / "claims.csv", ["id", "flagged", "truth", "audit_x", "audit_y"], rows)
        tri = self.ok(run_script("cmh_evaluate.py", "triage", "--table", self.dir / "claims.csv", "--truth-column",
                                 "truth", "--valid-values", "1", "--invalid-values", "2", "--noise", "0.02",
                                 "--seed", "1", "--reps", "50", "--out", self.dir / "tri.json"))
        self.assertIn("6/10 = 60.0%", tri.stdout)
        self.assertIn("3/40 = 7.5%", tri.stdout)
        aud = self.ok(run_script("cmh_evaluate.py", "audit", "--table", self.dir / "claims.csv", "--truth-column",
                                 "truth", "--valid-values", "1", "--invalid-values", "2",
                                 "--decision-columns", "audit_x,audit_y", "--out", self.dir / "aud.json"))
        result = json.loads((self.dir / "aud.json").read_text())["result"]
        x = result["per_configuration"]["audit_x"]
        y = result["per_configuration"]["audit_y"]
        self.assertEqual((x["catch_rate"]["k"], x["catch_rate"]["n"]), (6, 9))
        self.assertEqual(y["false_overturn_rate"]["k"], 4)
        self.assertEqual(result["paired_comparisons"]["audit_x|audit_y"]["catches_on_invalid"]["c"], 3)
        self.assertIn("McNemar", aud.stdout)
        cmp_ = self.ok(run_script("cmh_evaluate.py", "compare", "--a", "layered:8/200", "--b", "single:13/250"))
        self.assertIn("does not show that they are equal", cmp_.stdout)

    def test_estimate_and_recall(self):
        write_csv(self.dir / "pop.csv", ["id", "model"], [[f"p{i}", "Y" if i < 30 else "N"] for i in range(100)])
        write_csv(self.dir / "gold.csv", ["id", "model", "human"],
                  [["g0", "Y", "Y"], ["g1", "Y", "N"], ["g2", "N", "N"], ["g3", "N", "N"], ["g4", "Y", "N"],
                   ["g5", "N", "N"], ["g6", "N", "N"], ["g7", "N", "N"], ["g8", "N", "N"], ["g9", "N", "N"]])
        self.ok(run_script("cmh_evaluate.py", "estimate", "--population", self.dir / "pop.csv", "--gold",
                           self.dir / "gold.csv", "--model-column", "model", "--human-column", "human",
                           "--positive", "Y", "--out", self.dir / "est.json"))
        est = json.loads((self.dir / "est.json").read_text())["result"]["groups"]["all"]
        self.assertAlmostEqual(est["difference_estimate"]["estimate"], 0.1)
        write_csv(self.dir / "neg.csv", ["id", "truth"], [[f"n{i}", "Y" if i < 2 else "N"] for i in range(40)])
        rec = self.ok(run_script("cmh_evaluate.py", "recall", "--sample", self.dir / "neg.csv", "--truth-column",
                                 "truth", "--positive", "Y", "--pool-size", "400"))
        self.assertIn("2/40 = 5.0%", rec.stdout)
        self.assertIn("20.0", rec.stdout)


class CheckTests(Base):
    def test_rules(self):
        write_csv(self.dir / "instances.csv", ["instance_id"], [["i1"], ["i2"]])
        write_csv(self.dir / "truth.csv", ["unit_id", "tier", "value", "value_kind", "evidence_id"], [
            ["u1", "model_judged", "1990", "attested", "i1"],
            ["u2", "search_count", "1985", "attested", ""],
            ["u2", "made_up", "19x5", "upper_bound", "i9"],
        ])
        (self.dir / "checks.toml").write_text(textwrap.dedent('''
            [[check]]
            type = "unique"
            columns = ["unit_id"]
            [[check]]
            type = "allowed"
            column = "tier"
            values = ["human", "model_judged", "search_count"]
            [[check]]
            type = "pattern"
            column = "value"
            regex = '\\d{4}'
            [[check]]
            name = "search counts only give upper bounds"
            type = "implies"
            when = [{ column = "tier", op = "eq", value = "search_count" }]
            then = [{ column = "value_kind", op = "eq", value = "upper_bound" }]
            [[check]]
            type = "foreign_key"
            column = "evidence_id"
            table = "instances.csv"
            table_column = "instance_id"
            allow_empty = true
            [[check]]
            type = "row_count"
            same_as = "instances.csv"
        '''), encoding="utf-8")
        result = run_script("cmh_check.py", "run", "--table", self.dir / "truth.csv", "--rules",
                            self.dir / "checks.toml", "--key-column", "unit_id")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count("FAIL"), 6, result.stdout)
        self.assertIn("search counts only give upper bounds: 1 row(s)", result.stdout)

    def test_diff(self):
        write_csv(self.dir / "old.csv", ["unit_id", "value"], [["u1", "1990"], ["u2", "1985"]])
        write_csv(self.dir / "new.csv", ["unit_id", "value"], [["u1", "1990"], ["u2", "1986"], ["u3", "2000"]])
        result = run_script("cmh_check.py", "diff", "--old", self.dir / "old.csv", "--new", self.dir / "new.csv",
                            "--key", "unit_id", "--fail-on-change")
        self.assertEqual(result.returncode, 1)
        self.assertIn("~ u2 [value]: '1985' -> '1986'", result.stdout)
        self.assertIn("+ u3", result.stdout)


class NumbersTests(Base):
    def test_registry_and_scan(self):
        (self.dir / "results.json").write_text(json.dumps({"pairs": {"A|B": {"kappa": 0.6254}}, "n": 1203}))
        write_csv(self.dir / "claims.csv", ["status", "share"], [["claimed", "0.125"], ["claimed", ""],
                                                                 ["abstained", ""]])
        (self.dir / "numbers.toml").write_text(textwrap.dedent('''
            [settings]
            ignore = ['^(19|20)\\d{2}$']
            [[number]]
            id = "kappa"
            source = "results.json"
            path = ["pairs", "A|B", "kappa"]
            format = ".2f"
            [[number]]
            id = "n"
            source = "results.json"
            path = ["n"]
            format = ",d"
            [[number]]
            id = "claimed"
            source = "claims.csv"
            count_where = [{ column = "status", op = "eq", value = "claimed" }]
            format = "d"
        '''), encoding="utf-8")
        (self.dir / "paper.md").write_text("In 2020 we coded 1,203 items; κ = 0.63.\n共有2个结论，另有17个未登记。\n",
                                           encoding="utf-8")
        result = run_script("cmh_numbers.py", "check", "--manuscript", self.dir / "paper.md", "--registry",
                            self.dir / "numbers.toml")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ok      kappa: 0.63", result.stdout)
        self.assertIn("line 2: 17", result.stdout)
        self.assertNotIn("2020", result.stdout.split("not registered")[-1])
        strict = run_script("cmh_numbers.py", "check", "--manuscript", self.dir / "paper.md", "--registry",
                            self.dir / "numbers.toml", "--strict")
        self.assertEqual(strict.returncode, 1)
        (self.dir / "paper.md").write_text("κ = 0.62\n", encoding="utf-8")
        missing = run_script("cmh_numbers.py", "check", "--manuscript", self.dir / "paper.md", "--registry",
                             self.dir / "numbers.toml")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("MISSING kappa", missing.stdout)


if __name__ == "__main__":
    unittest.main()
