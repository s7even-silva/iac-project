#include "SpectrumSampler.hh"
#include "Randomize.hh"

#include <fstream>
#include <sstream>
#include <iostream>
#include <algorithm>

SpectrumSampler::SpectrumSampler(const G4String& csvFilename)
{
  std::ifstream file(csvFilename);
  if (!file.is_open()) {
    G4cerr << "SpectrumSampler: no se pudo abrir " << csvFilename << G4endl;
    return;
  }

  std::vector<G4double> energies;
  std::vector<G4double> fluxes;

  std::string line;
  while (std::getline(file, line)) {
    if (line.empty() || line[0] == '#') continue;
    std::replace(line.begin(), line.end(), ',', ' ');
    std::istringstream iss(line);
    G4double e, f;
    if (iss >> e >> f) {
      energies.push_back(e);
      fluxes.push_back(f);
    }
  }
  file.close();

  if (energies.size() < 2) {
    G4cerr << "SpectrumSampler: " << csvFilename
           << " tiene muy pocos puntos validos." << G4endl;
    return;
  }

  fEnergy = energies;
  fCDF.resize(energies.size(), 0.0);
  for (size_t i = 1; i < energies.size(); ++i) {
    G4double dE = energies[i] - energies[i-1];
    G4double avgFlux = 0.5 * (fluxes[i] + fluxes[i-1]);
    fCDF[i] = fCDF[i-1] + avgFlux * dE;
  }
  fIntegratedFlux = fCDF.back();
  for (auto& c : fCDF) c /= fIntegratedFlux;
}

G4double SpectrumSampler::SampleEnergy() const
{
  if (fCDF.empty()) return 0.0;

  G4double u = G4UniformRand();
  auto it = std::lower_bound(fCDF.begin(), fCDF.end(), u);
  size_t idx = std::distance(fCDF.begin(), it);
  if (idx == 0) return fEnergy.front();
  if (idx >= fEnergy.size()) return fEnergy.back();

  G4double c0 = fCDF[idx-1], c1 = fCDF[idx];
  G4double e0 = fEnergy[idx-1], e1 = fEnergy[idx];
  G4double frac = (c1 > c0) ? (u - c0) / (c1 - c0) : 0.0;
  return e0 + frac * (e1 - e0);
}
