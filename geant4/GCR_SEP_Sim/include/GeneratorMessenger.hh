#pragma once
#include "G4UImessenger.hh"
#include "globals.hh"

class PrimaryGeneratorAction;
class G4UIdirectory;
class G4UIcmdWithAString;

// /gun/model GCR|SEP
// /gun/dirMode isotropic|front|back|left|right
// /gun/phase max|min
class GeneratorMessenger : public G4UImessenger {
public:
  explicit GeneratorMessenger(PrimaryGeneratorAction* gen);
  ~GeneratorMessenger() override;
  void SetNewValue(G4UIcommand* command, G4String newValue) override;

private:
  PrimaryGeneratorAction* fGenerator;
  G4UIdirectory* fDir;
  G4UIcmdWithAString* fModelCmd;
  G4UIcmdWithAString* fDirCmd;
  G4UIcmdWithAString* fPhaseCmd;
};
