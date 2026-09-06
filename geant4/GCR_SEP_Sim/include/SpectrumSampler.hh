#pragma once
#include "globals.hh"
#include <vector>

// Lee un CSV de dos columnas: E_MeV_por_nucleon , flujo_diferencial
// y muestrea energias siguiendo esa distribucion (metodo de la CDF).
//
// IMPORTANTE: los CSV en /data son PLACEHOLDERS ilustrativos para probar
// el pipeline de punta a punta. Para resultados cientificos reales,
// reemplazalos por espectros de OMERE, SPENVIS, CREME96 o Badhwar-O'Neill.
class SpectrumSampler {
public:
  explicit SpectrumSampler(const G4String& csvFilename);

  G4double SampleEnergy() const;
  G4bool IsValid() const { return !fEnergy.empty(); }

private:
  std::vector<G4double> fEnergy;
  std::vector<G4double> fCDF;
};
