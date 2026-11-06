"""The toy example doubles as an end-to-end test of every script."""

import subprocess
import sys
import unittest

from helpers import REPO, read_csv


class ToyExampleTests(unittest.TestCase):
    def test_runs_end_to_end(self):
        result = subprocess.run([sys.executable, str(REPO / "examples" / "toy" / "run_example.py")],
                                capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-3000:])
        self.assertIn("all checks passed", result.stdout)
        out = REPO / "examples" / "toy" / "out"
        final = {row["unit_id"]: row for row in read_csv(out / "final_table.csv")}
        self.assertEqual(final["u_mouse"]["value_kind"], "upper_bound")   # anchor at the window edge
        self.assertEqual(final["u_cloud"]["value"], "2008")               # isolated false anchor removed
        self.assertEqual(final["u_yun"]["value"], "2009")                 # segmentation trap removed
        self.assertFalse((out / "sheets" / "key.csv").exists())          # key never sits with the sheets


if __name__ == "__main__":
    unittest.main()
