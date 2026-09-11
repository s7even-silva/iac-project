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
// Original GPS-based skeleton by S.Guatelli, M. Large and A. Malaroda,
// University of Wollongong. Rewritten (2026-09-10) to sample real OLTARIS
// GCR/SEP spectra instead of a fixed GPS macro beam, mirroring the pattern
// already validated in GCR_SEP_Sim/PrimaryGeneratorAction -- see AGENTS.md.
//
#ifndef ICRP110PhantomPrimaryGeneratorAction_h
#define ICRP110PhantomPrimaryGeneratorAction_h 1

#include "G4VUserPrimaryGeneratorAction.hh"
#include "G4ParticleGun.hh"
#include "globals.hh"

class G4Event;
class SpectrumSampler;
class ICRP110PhantomGeneratorMessenger;

// /gun/species GCR_H|GCR_He|SEP_p (una sola especie por corrida -- el
// scoring de dosis por organo de esta app pasa por G4ScoringManager, que no
// distingue especies dentro de una corrida; combinar especies con sus pesos
// fisicos W[s] se hace en Python leyendo el ICRP110.out de cada corrida,
// ver scripts/run_organ_sweep.py y scripts/aggregate_organ_doses.py).
// /gun/phase max|min (fase del ciclo solar; SEP min = Feb 1956, SEP max = Oct 1989)
class ICRP110PhantomPrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction
{
  public:
    explicit ICRP110PhantomPrimaryGeneratorAction();
    ~ICRP110PhantomPrimaryGeneratorAction() override;

    void GeneratePrimaries(G4Event* anEvent) override;

    void SetSpecies(const G4String& species) { fSpecies = species; }
    void SetPhase(const G4String& phase)     { fPhase = phase; }
    G4String GetSpecies() const { return fSpecies; }
    G4String GetPhase() const   { return fPhase; }

    // Bins de energia monoenergeticos para produccion (2026-09-11, ver
    // AGENTS.md y scripts/energy_bins.py): si se fija (>=0), CADA primario
    // nace con esta energia exacta -- MeV/amu para GCR_H/GCR_He (antes de
    // multiplicar por A, igual que SpectrumSampler::SampleEnergy()), MeV
    // para SEP_p -- en vez de muestrear el espectro continuo de
    // SpectrumSampler. Default -1 (deshabilitado): mantiene el muestreo
    // continuo tal cual para primary.mac/demos, donde no importa seguir la
    // decision de bins de produccion.
    void SetFixedEnergy(G4double e) { fFixedEnergy = e; }
    G4double GetFixedEnergy() const { return fFixedEnergy; }

    // Flujo/fluencia integrado (SpectrumSampler::GetIntegratedFlux) de la
    // especie/fase actualmente seleccionada -- mismas unidades nativas que
    // en GCR_SEP_Sim (particles/(day*cm2) para GCR, particles/cm2 para SEP).
    // Usado por aggregate_organ_doses.py junto al radio de esfera fuente
    // para recalcular W[s], no consumido en C++.
    G4double GetIntegratedFlux() const;

  private:
    void SampleIsotropicPosition(G4ThreeVector& pos, G4ThreeVector& dir, G4double radius) const;

    G4ParticleGun* fGun;
    G4String fSpecies = "GCR_H";
    G4String fPhase   = "min";
    G4double fFixedEnergy = -1.;

    SpectrumSampler* fGCR_H_max  = nullptr;
    SpectrumSampler* fGCR_H_min  = nullptr;
    SpectrumSampler* fGCR_He_max = nullptr;
    SpectrumSampler* fGCR_He_min = nullptr;
    SpectrumSampler* fSEP_p_max  = nullptr;
    SpectrumSampler* fSEP_p_min  = nullptr;

    ICRP110PhantomGeneratorMessenger* fMessenger = nullptr;
};
#endif
