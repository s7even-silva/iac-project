#pragma once
#include "G4VUserPrimaryGeneratorAction.hh"
#include "G4ParticleGun.hh"
#include "globals.hh"
#include <vector>
#include <tuple>

class G4Event;
class SpectrumSampler;
class GeneratorMessenger;

// /gun/model GCR|SEP
// /gun/direction isotropic|front|back|left|right
// /gun/phase max|min (fase del ciclo solar)
class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {
public:
  PrimaryGeneratorAction();
  ~PrimaryGeneratorAction() override;

  void GeneratePrimaries(G4Event* anEvent) override;

  void SetModel(const G4String& model)         { fModel = model; }
  void SetDirectionMode(const G4String& mode)  { fDirMode = mode; }
  void SetPhase(const G4String& phase)         { fPhase = phase; }
  G4String GetModel() const     { return fModel; }
  G4String GetDirMode() const   { return fDirMode; }
  G4String GetPhase() const     { return fPhase; }

private:
  void SampleIsotropicPosition(G4ThreeVector& pos, G4ThreeVector& dir, G4double radius) const;
  void SampleFixedDirection(G4ThreeVector& pos, G4ThreeVector& dir, G4double radius) const;

  G4ParticleGun* fGun;
  G4String fModel   = "GCR";
  G4String fDirMode = "isotropic";
  G4String fPhase   = "max";

  std::vector<std::tuple<G4String,G4int,G4int,G4double>> fGCRSpecies;

  // Un sampler por combinacion modelo x fase solar. Los CSV de datos/ son
  // PLACEHOLDERS (max y min son identicos hasta reemplazarlos con espectros
  // reales por fase solar, ver CLAUDE.md).
  SpectrumSampler* fGCR_H_max  = nullptr;
  SpectrumSampler* fGCR_H_min  = nullptr;
  SpectrumSampler* fGCR_He_max = nullptr;
  SpectrumSampler* fGCR_He_min = nullptr;
  SpectrumSampler* fSEP_p_max  = nullptr;
  SpectrumSampler* fSEP_p_min  = nullptr;

  GeneratorMessenger* fMessenger = nullptr;
};
