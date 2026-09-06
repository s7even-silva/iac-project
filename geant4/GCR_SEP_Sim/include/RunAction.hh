#pragma once
#include "G4UserRunAction.hh"
#include "globals.hh"

class G4Run;

class RunAction : public G4UserRunAction {
public:
  RunAction();
  ~RunAction() override = default;

  void BeginOfRunAction(const G4Run*) override;
  void EndOfRunAction(const G4Run*) override;

  void AddEdep(G4double edep) { fEdep += edep; }

private:
  G4double fEdep = 0.0; // MeV, acumulado en el phantom durante el run
};
