#pragma once
#include "globals.hh"
#include <vector>

// Lee un CSV de dos columnas: energia, flujo/fluencia diferencial, y
// muestrea energias siguiendo esa distribucion (metodo de la CDF, por
// integracion trapezoidal). Que tan real es esa distribucion depende de
// que fuente este activa en data/ (ver scripts/select_spectrum_source.py);
// algunas combinaciones siguen siendo placeholders, ver docs/checklist_espectros_reales.md.
class SpectrumSampler {
public:
  explicit SpectrumSampler(const G4String& csvFilename);

  G4double SampleEnergy() const;
  G4bool IsValid() const { return !fEnergy.empty(); }

  // Integral trapezoidal del flujo/fluencia diferencial tal cual esta en el
  // CSV (antes de normalizar a CDF), en las unidades nativas del archivo:
  // particles/(day*cm2) para los CSV de GCR (flujo), particles/cm2 para los
  // de SEP (fluencia de evento). Es el "flujo/fluencia integrado" que usa
  // RunAction para la normalizacion a dosis absoluta -- ver AGENTS.md.
  G4double GetIntegratedFlux() const { return fIntegratedFlux; }

private:
  std::vector<G4double> fEnergy;
  std::vector<G4double> fCDF;
  G4double fIntegratedFlux = 0.0;
};
