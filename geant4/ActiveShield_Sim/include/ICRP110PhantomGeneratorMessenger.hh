#pragma once
#include "G4UImessenger.hh"
#include "globals.hh"

class ICRP110PhantomPrimaryGeneratorAction;
class G4UIdirectory;
class G4UIcmdWithAString;

// /gun/species GCR_H|GCR_He|SEP_p (una sola especie por corrida, ver AGENTS.md)
// /gun/phase max|min (fase del ciclo solar, solo cambia el CSV de GCR/SEP usado)
class ICRP110PhantomGeneratorMessenger : public G4UImessenger {
public:
  explicit ICRP110PhantomGeneratorMessenger(ICRP110PhantomPrimaryGeneratorAction* gen);
  ~ICRP110PhantomGeneratorMessenger() override;
  void SetNewValue(G4UIcommand* command, G4String newValue) override;

private:
  ICRP110PhantomPrimaryGeneratorAction* fGenerator;
  G4UIdirectory* fDir;
  G4UIcmdWithAString* fSpeciesCmd;
  G4UIcmdWithAString* fPhaseCmd;
};
