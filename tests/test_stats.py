import unittest

import helpers  # noqa: F401  (adds the scripts folder to sys.path)
import cmh_stats as st
from cmh_common import make_rng


def two_by_two(a, b, c, d, yes="Y", no="N"):
    pairs = [(yes, yes)] * a + [(yes, no)] * b + [(no, yes)] * c + [(no, no)] * d
    return [x for x, _ in pairs], [y for _, y in pairs]


class ProportionTests(unittest.TestCase):
    def test_wilson(self):
        low, high = st.wilson_interval(10, 100)
        self.assertAlmostEqual(low, 0.05523, places=4)
        self.assertAlmostEqual(high, 0.17437, places=4)

    def test_wilson_edges(self):
        self.assertEqual(st.wilson_interval(0, 20)[0], 0.0)
        self.assertEqual(st.wilson_interval(20, 20)[1], 1.0)
        self.assertTrue(st.is_nan(st.wilson_interval(0, 0)[0]))

    def test_risk_ratio_katz(self):
        rr = st.risk_ratio(10, 50, 10, 200)
        self.assertAlmostEqual(rr["rr"], 4.0)
        self.assertAlmostEqual(rr["ci_low"], 1.7619, places=3)
        self.assertAlmostEqual(rr["ci_high"], 9.0809, places=3)
        self.assertFalse(rr["corrected"])
        self.assertTrue(st.risk_ratio(0, 50, 10, 200)["corrected"])

    def test_fisher_tea_tasting(self):
        self.assertAlmostEqual(st.fisher_exact(3, 1, 1, 3), 17 / 35, places=6)
        self.assertAlmostEqual(st.fisher_exact(0, 0, 0, 0), 1.0)

    def test_mcnemar(self):
        result = st.mcnemar(8, 2)
        self.assertAlmostEqual(result["p_exact"], 112 / 1024)
        self.assertAlmostEqual(result["chi2_cc"], 2.5)
        self.assertAlmostEqual(result["p_chi2_cc"], 0.11385, places=4)
        self.assertEqual(st.mcnemar(0, 0)["p_exact"], 1.0)


class AgreementTests(unittest.TestCase):
    def test_cohen_kappa(self):
        a, b = two_by_two(20, 5, 10, 15)
        self.assertAlmostEqual(st.cohen_kappa(a, b), 0.4)

    def test_gwet_ac1(self):
        a, b = two_by_two(20, 5, 10, 15)
        self.assertAlmostEqual(st.gwet_ac1(a, b, ["Y", "N"]), 0.205 / 0.505)

    def test_specific_agreement(self):
        a, b = two_by_two(20, 5, 10, 15)
        result = st.specific_agreement(a, b, "Y")
        self.assertAlmostEqual(result["p_pos"], 40 / 55)
        self.assertAlmostEqual(result["p_neg"], 30 / 45)

    def test_kappa_undefined_when_one_category(self):
        self.assertTrue(st.is_nan(st.cohen_kappa(["Y"] * 5, ["Y"] * 5)))

    def test_fleiss_textbook_example(self):
        # 10 items, 14 raters, 5 categories (the standard worked example).
        table = [[0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
                 [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7]]
        ratings = [[k for k, count in enumerate(row) for _ in range(count)] for row in table]
        self.assertAlmostEqual(st.fleiss_kappa(ratings), 0.20993, places=4)


class EstimationTests(unittest.TestCase):
    def test_rogan_gladen(self):
        self.assertAlmostEqual(st.rogan_gladen(0.3, 0.9, 0.8), 0.1 / 0.7)
        self.assertTrue(st.is_nan(st.rogan_gladen(0.3, 0.5, 0.5)))

    def test_difference_estimate(self):
        model_all = [1] * 30 + [0] * 70
        model_gold = [1, 1, 0, 0, 1, 0, 0, 0, 0, 0]
        human_gold = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        result = st.difference_estimate(model_all, model_gold, human_gold)
        self.assertAlmostEqual(result["estimate"], 0.1)
        self.assertAlmostEqual(result["ci_high"] - result["estimate"], 0.27648, places=4)

    def test_cluster_bootstrap_is_reproducible(self):
        clusters = {f"u{i}": [i % 2, (i + 1) % 3] for i in range(20)}
        stat = lambda xs: sum(xs) / len(xs)  # noqa: E731
        first = st.cluster_bootstrap(clusters, stat, 200, make_rng(7))
        second = st.cluster_bootstrap(clusters, stat, 200, make_rng(7))
        self.assertEqual(first, second)
        self.assertLess(first["ci_low"], first["ci_high"])

    def test_percentile(self):
        self.assertEqual(st.percentile([1, 2, 3, 4], 0.5), 2.5)


if __name__ == "__main__":
    unittest.main()
