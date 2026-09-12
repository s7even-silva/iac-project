#pragma once
#include "G4UserRunAction.hh"
#include "globals.hh"
#include <map>

class G4Run;

class RunAction : public G4UserRunAction {
public:
  RunAction();
  ~RunAction() override = default;

  void BeginOfRunAction(const G4Run*) override;
  void EndOfRunAction(const G4Run*) override;

  // species: "GCR_H", "GCR_He" o "SEP_p" (ver PrimaryGeneratorAction::GetLastSpecies).
  // Se acumula por especie -- no solo el total -- porque la normalizacion a
  // dosis absoluta pondera cada especie con su propio flujo/fluencia real
  // (ver EndOfRunAction y AGENTS.md).
  void AddEdep(G4double edep, const G4String& species) {
    fEdepBySpeciesMeV[species] += edep;
    fNBySpecies[species] += 1;
  }

private:
  std::map<G4String, G4double> fEdepBySpeciesMeV; // MeV, acumulado en el phantom por especie
  std::map<G4String, G4int> fNBySpecies;          // eventos simulados por especie
};
