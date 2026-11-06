import tempfile
import unittest
from pathlib import Path

import helpers
from cmh_common import (CMHError, allocate_proportional, check_condition, escape_formula, read_table, sample_rows,
                        unescape_formula, validate_condition)


class ConditionTests(unittest.TestCase):
    row = {"form": "ab", "n": "3", "empty": "", "tier": "model_judged"}

    def test_ops(self):
        cases = [
            ({"column": "form", "op": "len_le", "value": 2}, True),
            ({"column": "form", "op": "len_gt", "value": 2}, False),
            ({"column": "n", "op": "lt", "value": 5}, True),
            ({"column": "n", "op": "ge", "value": 4}, False),
            ({"column": "empty", "op": "lt", "value": 5}, False),  # numeric op on empty cell never fires
            ({"column": "empty", "op": "empty"}, True),
            ({"column": "tier", "op": "in", "value": ["human", "model_judged"]}, True),
            ({"column": "tier", "op": "not_in", "value": ["human"]}, True),
            ({"column": "tier", "op": "regex", "value": "^model"}, True),
            ({"column": "tier", "op": "eq", "value": "human"}, False),
        ]
        for cond, expected in cases:
            with self.subTest(cond=cond):
                validate_condition(cond, "test")
                self.assertEqual(check_condition(self.row, cond), expected)

    def test_validation_errors(self):
        for cond in [{"column": "x"}, {"column": "x", "op": "nope", "value": 1},
                     {"column": "x", "op": "in", "value": "a"}, {"column": "x", "op": "lt", "value": "abc"},
                     {"column": "x", "op": "regex", "value": "("}]:
            with self.subTest(cond=cond), self.assertRaises(CMHError):
                validate_condition(cond, "test")

    def test_missing_column(self):
        with self.assertRaises(CMHError):
            check_condition(self.row, {"column": "nope", "op": "empty"})


class FormulaTests(unittest.TestCase):
    def test_escape_roundtrip(self):
        for value in ["=SUM(A1)", "+1", "-x", "@cmd", "plain", ""]:
            self.assertEqual(unescape_formula(escape_formula(value)), value)
        self.assertEqual(escape_formula("=1+1"), "'=1+1")
        self.assertEqual(escape_formula("text"), "text")


class SamplingTests(unittest.TestCase):
    rows = [{"id": f"r{i:02d}", "s": "a" if i < 30 else "b"} for i in range(40)]

    def test_reproducible_and_order_independent(self):
        first = sample_rows(self.rows, id_column="id", seed=11, n=10)
        second = sample_rows(list(reversed(self.rows)), id_column="id", seed=11, n=10)
        self.assertEqual([r["id"] for r in first], [r["id"] for r in second])
        self.assertNotEqual([r["id"] for r in first], [r["id"] for r in sample_rows(self.rows, id_column="id",
                                                                                     seed=12, n=10)])

    def test_stratified_allocation(self):
        picked = sample_rows(self.rows, id_column="id", seed=1, n=8, strata_column="s")
        self.assertEqual(sum(r["s"] == "a" for r in picked), 6)
        self.assertEqual(allocate_proportional({"a": 1, "b": 1, "c": 1}, 2), {"a": 1, "b": 1, "c": 0})

    def test_too_many(self):
        with self.assertRaises(CMHError):
            sample_rows(self.rows, id_column="id", seed=1, n=41)


class ReadTableTests(unittest.TestCase):
    def test_bad_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            dup = Path(tmp, "dup.csv")
            dup.write_text("a,a\n1,2\n", encoding="utf-8")
            extra = Path(tmp, "extra.csv")
            extra.write_text("a,b\n1,2,3\n", encoding="utf-8")
            bom = Path(tmp, "bom.csv")
            bom.write_text("﻿a,b\n1,\n", encoding="utf-8")
            for path in (dup, extra):
                with self.subTest(path=path.name), self.assertRaises(CMHError):
                    read_table(path)
            header, rows = read_table(bom)
            self.assertEqual(header, ["a", "b"])
            self.assertEqual(rows, [{"a": "1", "b": ""}])


if __name__ == "__main__":
    unittest.main()
