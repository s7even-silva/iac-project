#include "PrimaryGeneratorAction.hh"
#include "GeneratorMessenger.hh"
#include "SpectrumSampler.hh"
#include "DetectorConstruction.hh"

#include "G4Event.hh"
#include "G4ParticleTable.hh"
#include "G4ParticleDefinition.hh"
#include "G4IonTable.hh"
#include "G4SystemOfUnits.hh"
#include "Randomize.hh"
#include "G4RunManager.hh"

PrimaryGeneratorAction::PrimaryGeneratorAction()
{
  fGun = new G4ParticleGun(1);

  fGCRSpecies = {
    {"H",  1, 1, 0.87},
    {"He", 4, 2, 0.13}
  };

  fGCR_H_max  = new SpectrumSampler("data/gcr_proton_solarmax.csv");
  fGCR_H_min  = new SpectrumSampler("data/gcr_proton_solarmin.csv");
  fGCR_He_max = new SpectrumSampler("data/gcr_alpha_solarmax.csv");
  fGCR_He_min = new SpectrumSampler("data/gcr_alpha_solarmin.csv");
  fSEP_p_max  = new SpectrumSampler("data/sep_proton_solarmax.csv");
  fSEP_p_min  = new SpectrumSampler("data/sep_proton_solarmin.csv");

  fMessenger = new GeneratorMessenger(this);
}

PrimaryGeneratorAction::~PrimaryGeneratorAction()
{
  delete fGun;
  delete fGCR_H_max;
  delete fGCR_H_min;
  delete fGCR_He_max;
  delete fGCR_He_min;
  delete fSEP_p_max;
  delete fSEP_p_min;
  delete fMessenger;
}

void PrimaryGeneratorAction::SampleIsotropicPosition(
    G4ThreeVector& pos, G4ThreeVector& dir, G4double radius) const
{
  G4double cosTheta = 2*G4UniformRand() - 1.0;
  G4double sinTheta = std::sqrt(1 - cosTheta*cosTheta);
  G4double phi = CLHEP::twopi * G4UniformRand();

  G4ThreeVector onSphere(sinTheta*std::cos(phi), sinTheta*std::sin(phi), cosTheta);
  pos = onSphere * radius;
  dir = -onSphere;
}

void PrimaryGeneratorAction::SampleFixedDirection(
    G4ThreeVector& pos, G4ThreeVector& dir, G4double radius) const
{
  G4ThreeVector axis;
  if (fDirMode == "front")      axis = G4ThreeVector(0,0,1);
  else if (fDirMode == "back")  axis = G4ThreeVector(0,0,-1);
  else if (fDirMode == "left")  axis = G4ThreeVector(1,0,0);
  else if (fDirMode == "right") axis = G4ThreeVector(-1,0,0);
  else                          axis = G4ThreeVector(0,0,1);

  pos = axis * radius;
  dir = -axis;
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* anEvent)
{
  auto* detector = static_cast<const DetectorConstruction*>(
      G4RunManager::GetRunManager()->GetUserDetectorConstruction());
  G4double radius = detector->GetSourceSphereRadius();
  if (radius <= 0.) radius = 50.*cm;

  G4ThreeVector pos, dir;
  if (fDirMode == "isotropic") SampleIsotropicPosition(pos, dir, radius);
  else                          SampleFixedDirection(pos, dir, radius);

  G4ParticleTable* table = G4ParticleTable::GetParticleTable();
  G4IonTable* ionTable = table->GetIonTable();

  G4ParticleDefinition* particle = nullptr;
  G4double kineticEnergy = 0.0;

  const G4bool isMin = (fPhase == "min");
  SpectrumSampler* sepP  = isMin ? fSEP_p_min  : fSEP_p_max;
  SpectrumSampler* gcrH  = isMin ? fGCR_H_min  : fGCR_H_max;
  SpectrumSampler* gcrHe = isMin ? fGCR_He_min : fGCR_He_max;

  if (fModel == "SEP") {
    particle = table->FindParticle("proton");
    kineticEnergy = sepP->SampleEnergy() * MeV;
    fLastSpecies = "SEP_p";
  } else {
    G4double u = G4UniformRand();
    G4double acc = 0.0;
    G4String name; G4int A=1, Z=1; G4double w=1.0;
    for (auto& sp : fGCRSpecies) {
      std::tie(name, A, Z, w) = sp;
      acc += w;
      if (u <= acc) break;
    }

    if (name == "H") {
      particle = table->FindParticle("proton");
      kineticEnergy = gcrH->SampleEnergy() * MeV;
      fLastSpecies = "GCR_H";
    } else {
      particle = ionTable->GetIon(Z, A, 0.0);
      G4double keMeVPerNucleon = gcrHe->SampleEnergy();
      kineticEnergy = keMeVPerNucleon * A * MeV;
      fLastSpecies = "GCR_He";
    }
  }

  fGun->SetParticleDefinition(particle);
  fGun->SetParticlePosition(pos);
  fGun->SetParticleMomentumDirection(dir);
  fGun->SetParticleEnergy(kineticEnergy);

  fGun->GeneratePrimaryVertex(anEvent);
}

G4double PrimaryGeneratorAction::GetIntegratedFlux(const G4String& species) const
{
  const G4bool isMin = (fPhase == "min");
  if (species == "GCR_H")  return (isMin ? fGCR_H_min  : fGCR_H_max)->GetIntegratedFlux();
  if (species == "GCR_He") return (isMin ? fGCR_He_min : fGCR_He_max)->GetIntegratedFlux();
  if (species == "SEP_p")  return (isMin ? fSEP_p_min  : fSEP_p_max)->GetIntegratedFlux();
  return 0.0;
}
