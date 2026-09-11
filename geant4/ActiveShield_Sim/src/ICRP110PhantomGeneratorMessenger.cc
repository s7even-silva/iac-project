#include "ICRP110PhantomGeneratorMessenger.hh"
#include "ICRP110PhantomPrimaryGeneratorAction.hh"
#include "G4UIdirectory.hh"
#include "G4UIcmdWithAString.hh"
#include "G4UIcmdWithADouble.hh"

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

  fFixedEnergyCmd = new G4UIcmdWithADouble("/gun/fixedEnergyMeV", this);
  fFixedEnergyCmd->SetGuidance("Bins de produccion (ver scripts/energy_bins.py): fija la energia de "
      "TODOS los primarios de la corrida (MeV/amu para GCR_H|GCR_He, MeV para SEP_p), en vez de "
      "muestrear el espectro continuo. Omitir para mantener el muestreo continuo (default).");
  fFixedEnergyCmd->SetParameterName("energyMeV", false);
}

ICRP110PhantomGeneratorMessenger::~ICRP110PhantomGeneratorMessenger()
{
  delete fSpeciesCmd;
  delete fPhaseCmd;
  delete fFixedEnergyCmd;
  delete fDir;
}

void ICRP110PhantomGeneratorMessenger::SetNewValue(G4UIcommand* command, G4String newValue)
{
  if (command == fSpeciesCmd) fGenerator->SetSpecies(newValue);
  else if (command == fPhaseCmd) fGenerator->SetPhase(newValue);
  else if (command == fFixedEnergyCmd) fGenerator->SetFixedEnergy(fFixedEnergyCmd->GetNewDoubleValue(newValue));
}
