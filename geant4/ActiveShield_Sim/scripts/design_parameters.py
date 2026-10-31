"""Statistical design parameters of the v2 study (docs/bitacora/plan_piloto.md).

Single source of truth: pilot and sweep analysis scripts import these names
instead of hardcoding numbers. Changing delta_eta later is one edit here plus
the re-checks listed in plan_piloto.md, "Cambiar δ_η más adelante".
"""

# D2 (2026-10-31): smallest difference in shield effectiveness eta = 1 - D1/D0
# that the primary endpoint must resolve, as a fraction of the unshielded dose.
DELTA_ETA = 0.10
# P6: half-width of the 95% CI of eta.
H_ETA_MAX = DELTA_ETA/2

# D3 (2026-10-31): error budget of each method approximation (source radius,
# energy grid, source bias, map resolution) in the equivalence tests of P1, P4
# and P5, as a fraction of the unshielded dose.
EQUIVALENCE_DIVISOR = 4
B = DELTA_ETA/EQUIVALENCE_DIVISOR
# Pre-declared secondary check, reported but never used to decide: the budget
# that delta_eta = 0.05 would need, so a later tightening knows in advance
# whether more events suffice or the frozen configuration must change.
B_SECONDARY = 0.05/EQUIVALENCE_DIVISOR

# D4 (2026-10-31): a run's (or batch's) per-event SE is trusted, per category,
# only if all three hold.
MIN_NONZERO_EVENTS = 200
MAX_VOV = 0.1
MAX_EVENT_FRACTION = 0.10  # largest single event / S1

# P2 pass criteria (2026-10-31), over batches that pass D4.
P2_BATCHES = 40
P2_MIN_COVERAGE = 0.90
P2_MIN_RHO = 0.75
