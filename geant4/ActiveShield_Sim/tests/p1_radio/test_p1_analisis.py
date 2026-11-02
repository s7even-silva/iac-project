"""El análisis de P1 paso 3 (p1_radio.py) con corridas sintéticas: depósitos
exponenciales con la fracción de primarios con depósito ∝ 1/R², como con la
esfera fuente, y el N que fijaría la sonda."""
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p1_radio import CONTROL_RADIUS_M, compare, decide, merge, vov_of  # noqa: E402
import design_parameters as dp  # noqa: E402


def category(deposits, m):
    s = [sum(v**k for v in deposits) for k in (1, 2, 3, 4)]
    return {"M": m, "S1_J": s[0], "S2_J2": s[1], "S3_J3": s[2], "S4_J4": s[3], "n_nonzero": len(deposits),
            "max_J": max(deposits, default=0.0), "vov": vov_of(*s, m) if len(deposits) >= 2 else math.inf}


def synthetic_run(rng, radius, m, scale=1.0, f16=1e-3):
    n = round(m*f16*(CONTROL_RADIUS_M/radius)**2)
    return category([scale*rng.expovariate(1.0) for _ in range(n)], m)


class P1AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(3)
        # SE(Δ) ~ B/4 con depósitos exponenciales (1 + CV² = 2) y f = 10⁻³ a 16 m.
        tau = dp.B/(4*math.sqrt(2))
        self.m16 = round(2/(1e-3*tau**2))
        self.control = synthetic_run(self.rng, CONTROL_RADIUS_M, self.m16//4)

    def pairs(self, scale14=1.0, m14_factor=1.0):
        runs = {r: synthetic_run(self.rng, r, round(self.m16*(r/16)**2*(m14_factor if r == 14 else 1)),
                                 scale14 if r == 14 else 1.0) for r in (14.0, 16.0, 18.0)}
        return {"caso": {(ri, rj): compare((ri, runs[ri]), (rj, runs[rj]), (CONTROL_RADIUS_M, self.control))
                         for ri, rj in ((14.0, 16.0), (14.0, 18.0), (16.0, 18.0))}}

    def test_same_dose_accepts_smallest_radius(self):
        pairs = self.pairs()
        self.assertEqual(decide(pairs, [14.0, 16.0, 18.0]), 14.0)
        se = pairs["caso"][(14.0, 18.0)]["se"]
        self.assertTrue(dp.B/5 < se < dp.B/3, se)  # la normalización R² deja el SE de diseño

    def test_dose_excess_is_not_equivalent(self):
        self.assertIsNone(decide(self.pairs(scale14=1.06), [14.0, 16.0, 18.0]))

    def test_run_failing_d4_does_not_conclude(self):
        pairs = self.pairs(m14_factor=1e-3)  # ~100 eventos con depósito a 14 m
        self.assertFalse(pairs["caso"][(14.0, 16.0)]["d4"])
        self.assertIsNone(decide(pairs, [14.0, 16.0, 18.0]))

    def test_parts_merge_into_the_whole_run(self):
        deposits = [self.rng.expovariate(1.0) for _ in range(1000)]
        whole = category(deposits, 10**6)
        merged, truncated = merge([({"total_body": category(deposits[:300], 4*10**5)}, 3.0),
                                   ({"total_body": category(deposits[300:], 6*10**5)}, 1.0)])
        for key, value in whole.items():
            self.assertAlmostEqual(merged["total_body"][key]/value, 1.0, places=9, msg=key)
        self.assertEqual(truncated, 4e-6)


if __name__ == "__main__":
    unittest.main()
