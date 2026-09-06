#pragma once
#include "G4UImessenger.hh"
#include "globals.hh"

class DetectorConstruction;
class G4UIdirectory;
class G4UIcmdWithABool;
class G4UIcmdWithADouble;

// /detector/shield on|off            (blindaje pasivo legado, desactivado por defecto)
// /detector/alThickness <cm>         (legado)
// /detector/polyThickness <cm>       (legado)
// /detector/field on|off             (campo magnetico activo)
// /detector/fieldValue <tesla>       (barrido 7-10 T)
// /detector/hullThicknessCm <cm>     (casco de la nave)
// /detector/astronautX <cm>          (posicion del astronauta, barrido 0-280 cm)
class DetectorMessenger : public G4UImessenger {
public:
  explicit DetectorMessenger(DetectorConstruction* det);
  ~DetectorMessenger() override;
  void SetNewValue(G4UIcommand* command, G4String newValue) override;

private:
  DetectorConstruction* fDetector;
  G4UIdirectory* fDir;
  G4UIcmdWithABool* fShieldCmd;
  G4UIcmdWithADouble* fAlThicknessCmd;
  G4UIcmdWithADouble* fPolyThicknessCmd;
  G4UIcmdWithABool* fFieldCmd;
  G4UIcmdWithADouble* fFieldValueCmd;
  G4UIcmdWithADouble* fHullThicknessCmd;
  G4UIcmdWithADouble* fAstronautXCmd;
};
