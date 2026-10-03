/** GV per (T·m): r[m] = R[GV] / (C · B[T]). */
export const C = 0.299792458;

export type SpeciesKey = "p" | "He" | "Fe";

/** Nucleus mass per nucleon (MeV), mass number and charge. */
export const SPECIES: Record<SpeciesKey, { label: string; name: string; mu: number; A: number; Z: number }> = {
  p: { label: "Proton", name: "proton", mu: 938.272, A: 1, Z: 1 },
  He: { label: "Helium-4", name: "helium-4", mu: 3727.379 / 4, A: 4, Z: 2 },
  Fe: { label: "Iron-56", name: "iron-56", mu: 52089.8 / 56, A: 56, Z: 26 },
};

/** Rigidity (GV) from kinetic energy per nucleon (MeV). */
export function rigidity(sp: SpeciesKey, tn: number): number {
  const s = SPECIES[sp];
  return (s.A * Math.sqrt(tn * (tn + 2 * s.mu))) / s.Z / 1000;
}

/** Kinetic energy per nucleon (MeV) that gives rigidity R (GV). */
export function energyAt(sp: SpeciesKey, R: number): number {
  const s = SPECIES[sp];
  const pn = (R * 1000 * s.Z) / s.A;
  return Math.sqrt(pn * pn + s.mu * s.mu) - s.mu;
}

export const fmtE = (mev: number) =>
  mev >= 1000 ? `${+(mev / 1000).toPrecision(3)} GeV` : `${+mev.toPrecision(3)} MeV`;
export const fmtR = (gv: number) => (gv >= 10 ? `${gv.toFixed(1)} GV` : `${gv.toPrecision(3)} GV`);
export const fmtLen = (m: number) =>
  m >= 1000 ? `${(m / 1000).toPrecision(3)} km` : m >= 10 ? `${m.toFixed(0)} m` : `${m.toPrecision(2)} m`;
export const fmtPct = (f: number) =>
  f < 0.001 ? "< 0.1%" : f > 0.999 ? "> 99.9%" : `${(100 * f).toFixed(f < 0.1 ? 1 : 0)}%`;
