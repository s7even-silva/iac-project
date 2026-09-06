#include "DetectorMessenger.hh"
#include "DetectorConstruction.hh"

#include "G4UIdirectory.hh"
#include "G4UIcmdWithABool.hh"
#include "G4UIcmdWithADouble.hh"
#include "G4RunManager.hh"

DetectorMessenger::DetectorMessenger(DetectorConstruction* det)
  : fDetector(det)
{
  fDir = new G4UIdirectory("/detector/");
  fDir->SetGuidance("Comandos de geometria: blindaje pasivo (Al+polietileno) y campo (placeholder).");

  fShieldCmd = new G4UIcmdWithABool("/detector/shield", this);
  fShieldCmd->SetGuidance("Activa/desactiva el blindaje pasivo (Al + polietileno).");
  fShieldCmd->SetParameterName("shieldOn", false);

  fAlThicknessCmd = new G4UIcmdWithADouble("/detector/alThickness", this);
  fAlThicknessCmd->SetGuidance("Espesor del casco de aluminio, en cm.");
  fAlThicknessCmd->SetParameterName("thicknessCm", false);

  fPolyThicknessCmd = new G4UIcmdWithADouble("/detector/polyThickness", this);
  fPolyThicknessCmd->SetGuidance("Espesor del revestimiento de polietileno, en cm.");
  fPolyThicknessCmd->SetParameterName("thicknessCm", false);

  fFieldCmd = new G4UIcmdWithABool("/detector/field", this);
  fFieldCmd->SetGuidance("Activa/desactiva el campo magnetico (placeholder).");
  fFieldCmd->SetParameterName("fieldOn", false);

  fFieldValueCmd = new G4UIcmdWithADouble("/detector/fieldValue", this);
  fFieldValueCmd->SetGuidance("Intensidad del campo magnetico activo, en tesla (barrido 7-10 T).");
  fFieldValueCmd->SetParameterName("bzTesla", false);

  fHullThicknessCmd = new G4UIcmdWithADouble("/detector/hullThicknessCm", this);
  fHullThicknessCmd->SetGuidance("Espesor del casco estructural de aluminio de la nave, en cm.");
  fHullThicknessCmd->SetParameterName("thicknessCm", false);

  fAstronautXCmd = new G4UIcmdWithADouble("/detector/astronautX", this);
  fAstronautXCmd->SetGuidance("Posicion X del astronauta dentro de la nave, en cm (barrido 0-280).");
  fAstronautXCmd->SetParameterName("xCm", false);
}

DetectorMessenger::~DetectorMessenger()
{
  delete fShieldCmd;
  delete fAlThicknessCmd;
  delete fPolyThicknessCmd;
  delete fFieldCmd;
  delete fFieldValueCmd;
  delete fHullThicknessCmd;
  delete fAstronautXCmd;
  delete fDir;
}

void DetectorMessenger::SetNewValue(G4UIcommand* command, G4String newValue)
{
  if (command == fShieldCmd) {
    fDetector->SetShieldOn(fShieldCmd->GetNewBoolValue(newValue));
  } else if (command == fAlThicknessCmd) {
    fDetector->SetAlThicknessCm(fAlThicknessCmd->GetNewDoubleValue(newValue));
  } else if (command == fPolyThicknessCmd) {
    fDetector->SetPolyThicknessCm(fPolyThicknessCmd->GetNewDoubleValue(newValue));
  } else if (command == fFieldCmd) {
    fDetector->SetFieldOn(fFieldCmd->GetNewBoolValue(newValue));
  } else if (command == fFieldValueCmd) {
    fDetector->SetFieldValueTesla(fFieldValueCmd->GetNewDoubleValue(newValue));
  } else if (command == fHullThicknessCmd) {
    fDetector->SetHullThicknessCm(fHullThicknessCmd->GetNewDoubleValue(newValue));
  } else if (command == fAstronautXCmd) {
    fDetector->SetAstronautXCm(fAstronautXCmd->GetNewDoubleValue(newValue));
  }

  G4RunManager::GetRunManager()->ReinitializeGeometry();
}
