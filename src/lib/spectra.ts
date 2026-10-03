import raw from "../data/spectra.json";

export interface Spectrum {
  label: string;
  species: string;
  log10_R_GV: number[];
  pct_per_decade: number[];
  cdf: number[];
}

export const SPECTRA = raw.spectra as Record<"gcr_h" | "gcr_he" | "sep", Spectrum>;

/** Linear interpolation in log10 R; null outside the tabulated range. */
export function interp(s: Spectrum, field: "pct_per_decade" | "cdf", lr: number): number | null {
  const xs = s.log10_R_GV;
  const ys = s[field];
  if (lr < xs[0] || lr > xs[xs.length - 1]) return null;
  let i = 1;
  while (xs[i] < lr) i++;
  const f = (lr - xs[i - 1]) / (xs[i] - xs[i - 1]);
  return ys[i - 1] + f * (ys[i] - ys[i - 1]);
}

/** Fraction of the spectrum (above 10 MeV/n) with rigidity below 10^lr GV. */
export function fractionBelow(s: Spectrum, lr: number): number {
  if (lr < s.log10_R_GV[0]) return 0;
  if (lr > s.log10_R_GV[s.log10_R_GV.length - 1]) return 1;
  return interp(s, "cdf", lr) ?? 0;
}
