"""El análisis de P2 (p2_estimador.evaluate) con datos sintéticos de varianza
finita: el SE por lote es correcto, así que tiene que aprobar."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p2_estimador import evaluate  # noqa: E402
import design_parameters as dp  # noqa: E402


class P2AnalysisTests(unittest.TestCase):
    def test_well_behaved_deposits_pass(self):
        rng = random.Random(1)
        n, p = 40*20000, 0.02  # ~400 eventos con depósito por lote, depósitos exponenciales
        values = {"total_body": {e: rng.expovariate(1.0) for e in range(n) if rng.random() < p}}
        result = evaluate(n, ["total_body"], values, dp.P2_BATCHES)
        self.assertEqual(result["pairs_passing_d4"], dp.P2_BATCHES)
        self.assertGreaterEqual(result["coverage_passing_d4"], dp.P2_MIN_COVERAGE)
        rho = result["rho"]["total_body"]["rho"]
        self.assertTrue(dp.P2_MIN_RHO <= rho < 1.4, rho)


if __name__ == "__main__":
    unittest.main()
