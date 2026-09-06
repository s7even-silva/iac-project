#pragma once
#include "G4VUserDetectorConstruction.hh"
#include "G4LogicalVolume.hh"
#include "globals.hh"

class DetectorMessenger;

// Geometria: World (vacio) -> ShipHull (aluminio) -> ShipInterior (vacio,
// aqui se confina el campo magnetico activo) -> [blindaje pasivo legado,
// opcional] -> Phantom (posicionable en X dentro de la nave).
//
// El blindaje pasivo de DOS capas (Aluminio -> Polietileno -> Phantom) se
// conserva por compatibilidad pero esta desactivado por defecto: el estudio
// actual se enfoca en el campo magnetico activo, no en blindaje pasivo.
class DetectorConstruction : public G4VUserDetectorConstruction {
public:
  DetectorConstruction();
  ~DetectorConstruction() override;

  G4VPhysicalVolume* Construct() override;

  void SetShieldOn(G4bool val)             { fShieldOn = val; }
  void SetAlThicknessCm(G4double val)      { fAlThickness = val; }
  void SetPolyThicknessCm(G4double val)    { fPolyThickness = val; }
  void SetFieldOn(G4bool val)              { fFieldOn = val; }
  void SetFieldValueTesla(G4double val)    { fBzTesla = val; }
  void SetHullThicknessCm(G4double val)    { fHullThicknessCm = val; }
  void SetAstronautXCm(G4double val)       { fAstronautXCm = val; }

  G4bool   GetShieldOn() const         { return fShieldOn; }
  G4double GetAlThicknessCm() const    { return fAlThickness; }
  G4double GetPolyThicknessCm() const  { return fPolyThickness; }
  G4bool   GetFieldOn() const          { return fFieldOn; }
  G4double GetFieldValueTesla() const  { return fBzTesla; }
  G4double GetHullThicknessCm() const  { return fHullThicknessCm; }
  G4double GetAstronautXCm() const     { return fAstronautXCm; }

  G4LogicalVolume* GetPhantomLV() const { return fLogicPhantom; }
  G4double GetSourceSphereRadius() const { return fSourceRadius; }

private:
  G4bool   fShieldOn      = false;
  G4double fAlThickness   = 0.3;   // cm, capa de aluminio del blindaje pasivo legado
  G4double fPolyThickness = 5.0;   // cm, revestimiento de polietileno (legado)
  G4bool   fFieldOn       = false;
  G4double fBzTesla       = 0.0;   // intensidad del campo activo, Tesla (barrido 7-10T)

  G4double fHullThicknessCm = 0.3; // cm, casco estructural de aluminio de la nave
  G4double fAstronautXCm    = 0.0; // cm, posicion del astronauta dentro de la nave (eje X)

  G4double fSourceRadius = 0.0;

  G4LogicalVolume* fLogicPhantom = nullptr;
  DetectorMessenger* fMessenger = nullptr;
};
