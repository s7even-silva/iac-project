//
// ********************************************************************
// * License and Disclaimer                                           *
// *                                                                  *
// * The  Geant4 software  is  copyright of the Copyright Holders  of *
// * the Geant4 Collaboration.  It is provided  under  the terms  and *
// * conditions of the Geant4 Software License,  included in the file *
// * LICENSE and available at  http://cern.ch/geant4/license .  These *
// * include a list of copyright holders.                             *
// *                                                                  *
// * Neither the authors of this software system, nor their employing *
// * institutes,nor the agencies providing financial support for this *
// * work  make  any representation or  warranty, express or implied, *
// * regarding  this  software system or assume any liability for its *
// * use.  Please see the license in the file  LICENSE  and URL above *
// * for the full disclaimer and the limitation of liability.         *
// *                                                                  *
// * This  code  implementation is the result of  the  scientific and *
// * technical work of the GEANT4 collaboration.                      *
// * By using,  copying,  modifying or  distributing the software (or *
// * any work based  on the software)  you  agree  to acknowledge its *
// * use  in  resulting  scientific  publications,  and indicate your *
// * acceptance of all terms of the Geant4 Software license.          *
// ********************************************************************
//
// Rewritten (2026-09-10) -- see header for context.
//
#include "ICRP110PhantomPrimaryGeneratorAction.hh"
#include "ICRP110PhantomGeneratorMessenger.hh"
#include "SpectrumSampler.hh"
#include "ICRP110PhantomConstruction.hh"

#include "G4Event.hh"
#include "G4ParticleTable.hh"
#include "G4ParticleDefinition.hh"
#include "G4IonTable.hh"
#include "G4SystemOfUnits.hh"
#include "Randomize.hh"
#include "G4RunManager.hh"

ICRP110PhantomPrimaryGeneratorAction::ICRP110PhantomPrimaryGeneratorAction()
{
  fGun = new G4ParticleGun(1);

  fGCR_H_max  = new SpectrumSampler("data/gcr_proton_solarmax.csv");
  fGCR_H_min  = new SpectrumSampler("data/gcr_proton_solarmin.csv");
  fGCR_He_max = new SpectrumSampler("data/gcr_alpha_solarmax.csv");
  fGCR_He_min = new SpectrumSampler("data/gcr_alpha_solarmin.csv");
  fSEP_p_max  = new SpectrumSampler("data/sep_proton_solarmax.csv");
  fSEP_p_min  = new SpectrumSampler("data/sep_proton_solarmin.csv");

  fMessenger = new ICRP110PhantomGeneratorMessenger(this);
}

ICRP110PhantomPrimaryGeneratorAction::~ICRP110PhantomPrimaryGeneratorAction()
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

void ICRP110PhantomPrimaryGeneratorAction::SampleIsotropicPosition(
    G4ThreeVector& pos, G4ThreeVector& dir, G4double radius) const
{
  G4double cosTheta = 2*G4UniformRand() - 1.0;
  G4double sinTheta = std::sqrt(1 - cosTheta*cosTheta);
  G4double phi = CLHEP::twopi * G4UniformRand();

  G4ThreeVector onSphere(sinTheta*std::cos(phi), sinTheta*std::sin(phi), cosTheta);
  pos = onSphere * radius;
  dir = -onSphere;
}

void ICRP110PhantomPrimaryGeneratorAction::GeneratePrimaries(G4Event* anEvent)
{
  auto* detector = static_cast<const ICRP110PhantomConstruction*>(
      G4RunManager::GetRunManager()->GetUserDetectorConstruction());
  G4double radius = detector->GetSourceSphereRadius();
  if (radius <= 0.) radius = 6.*m;

  G4ThreeVector pos, dir;
  SampleIsotropicPosition(pos, dir, radius);

  G4ParticleTable* table = G4ParticleTable::GetParticleTable();
  G4IonTable* ionTable = table->GetIonTable();

  G4ParticleDefinition* particle = nullptr;
  G4double kineticEnergy = 0.0;
  const G4bool isMin = (fPhase == "min");

  if (fSpecies == "GCR_He") {
    particle = ionTable->GetIon(2, 4, 0.0); // alpha: Z=2, A=4
    SpectrumSampler* sampler = isMin ? fGCR_He_min : fGCR_He_max;
    G4double keMeVPerNucleon = sampler->SampleEnergy();
    kineticEnergy = keMeVPerNucleon * 4 * MeV;
  } else if (fSpecies == "SEP_p") {
    particle = table->FindParticle("proton");
    SpectrumSampler* sampler = isMin ? fSEP_p_min : fSEP_p_max;
    kineticEnergy = sampler->SampleEnergy() * MeV;
  } else { // "GCR_H", default
    particle = table->FindParticle("proton");
    SpectrumSampler* sampler = isMin ? fGCR_H_min : fGCR_H_max;
    kineticEnergy = sampler->SampleEnergy() * MeV;
  }

  fGun->SetParticleDefinition(particle);
  fGun->SetParticlePosition(pos);
  fGun->SetParticleMomentumDirection(dir);
  fGun->SetParticleEnergy(kineticEnergy);

  fGun->GeneratePrimaryVertex(anEvent);
}

G4double ICRP110PhantomPrimaryGeneratorAction::GetIntegratedFlux() const
{
  const G4bool isMin = (fPhase == "min");
  if (fSpecies == "GCR_H")  return (isMin ? fGCR_H_min  : fGCR_H_max)->GetIntegratedFlux();
  if (fSpecies == "GCR_He") return (isMin ? fGCR_He_min : fGCR_He_max)->GetIntegratedFlux();
  if (fSpecies == "SEP_p")  return (isMin ? fSEP_p_min  : fSEP_p_max)->GetIntegratedFlux();
  return 0.0;
}
