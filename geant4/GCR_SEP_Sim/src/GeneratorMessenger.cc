#include "GeneratorMessenger.hh"
#include "PrimaryGeneratorAction.hh"
#include "G4UIdirectory.hh"
#include "G4UIcmdWithAString.hh"

GeneratorMessenger::GeneratorMessenger(PrimaryGeneratorAction* gen)
  : fGenerator(gen)
{
  fDir = new G4UIdirectory("/gun/");
  fDir->SetGuidance("Comandos del generador de eventos GCR/SEP.");

  fModelCmd = new G4UIcmdWithAString("/gun/model", this);
  fModelCmd->SetGuidance("Selecciona el modelo de radiacion: GCR o SEP.");
  fModelCmd->SetParameterName("model", false);

  fDirCmd = new G4UIcmdWithAString("/gun/dirMode", this);
  fDirCmd->SetGuidance("isotropic|front|back|left|right (para anisotropia).");
  fDirCmd->SetParameterName("dirMode", false);

  fPhaseCmd = new G4UIcmdWithAString("/gun/phase", this);
  fPhaseCmd->SetGuidance("Fase del ciclo solar: max|min.");
  fPhaseCmd->SetParameterName("phase", false);
}

GeneratorMessenger::~GeneratorMessenger()
{
  delete fModelCmd;
  delete fDirCmd;
  delete fPhaseCmd;
  delete fDir;
}

void GeneratorMessenger::SetNewValue(G4UIcommand* command, G4String newValue)
{
  if (command == fModelCmd) fGenerator->SetModel(newValue);
  else if (command == fDirCmd) fGenerator->SetDirectionMode(newValue);
  else if (command == fPhaseCmd) fGenerator->SetPhase(newValue);
}
