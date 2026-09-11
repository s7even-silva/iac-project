#include "ICRP110PhantomGeneratorMessenger.hh"
#include "ICRP110PhantomPrimaryGeneratorAction.hh"
#include "G4UIdirectory.hh"
#include "G4UIcmdWithAString.hh"

ICRP110PhantomGeneratorMessenger::ICRP110PhantomGeneratorMessenger(ICRP110PhantomPrimaryGeneratorAction* gen)
  : fGenerator(gen)
{
  fDir = new G4UIdirectory("/gun/");
  fDir->SetGuidance("Comandos del generador de eventos GCR/SEP (una especie por corrida).");

  fSpeciesCmd = new G4UIcmdWithAString("/gun/species", this);
  fSpeciesCmd->SetGuidance("Especie primaria de la corrida: GCR_H|GCR_He|SEP_p.");
  fSpeciesCmd->SetParameterName("species", false);

  fPhaseCmd = new G4UIcmdWithAString("/gun/phase", this);
  fPhaseCmd->SetGuidance("Fase del ciclo solar: max|min.");
  fPhaseCmd->SetParameterName("phase", false);
}

ICRP110PhantomGeneratorMessenger::~ICRP110PhantomGeneratorMessenger()
{
  delete fSpeciesCmd;
  delete fPhaseCmd;
  delete fDir;
}

void ICRP110PhantomGeneratorMessenger::SetNewValue(G4UIcommand* command, G4String newValue)
{
  if (command == fSpeciesCmd) fGenerator->SetSpecies(newValue);
  else if (command == fPhaseCmd) fGenerator->SetPhase(newValue);
}
