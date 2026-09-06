#include "DetectorConstruction.hh"
#include "DetectorMessenger.hh"

#include "G4NistManager.hh"
#include "G4Box.hh"
#include "G4Orb.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4VisAttributes.hh"
#include "G4Colour.hh"
#include "G4UniformMagField.hh"
#include "G4FieldManager.hh"
#include "G4UserLimits.hh"

DetectorConstruction::DetectorConstruction()
{
  fMessenger = new DetectorMessenger(this);
}

DetectorConstruction::~DetectorConstruction()
{
  delete fMessenger;
}

G4VPhysicalVolume* DetectorConstruction::Construct()
{
  G4NistManager* nist = G4NistManager::Instance();

  G4Material* vacuum  = nist->FindOrBuildMaterial("G4_Galactic");
  G4Material* aluminum= nist->FindOrBuildMaterial("G4_Al");
  G4Material* polyeth = nist->FindOrBuildMaterial("G4_POLYETHYLENE");
  G4Material* tissue  = nist->FindOrBuildMaterial("G4_TISSUE_SOFT_ICRU-4");

  const G4double phantomRadius = 15.0 * cm;

  // Radio interior nominal de la nave: 2.8 m (valor de estudio, barrido de
  // posicion del astronauta va de 0 a 2.8 m). El solido interior real se
  // construye un poco mas grande (margen de holgura) para que el phantom no
  // se salga del casco cuando el astronauta esta en la posicion extrema
  // (2.8 m + radio del phantom > 2.8 m literales) -- esto es solo holgura
  // geometrica interna, el barrido y el CSV siguen reportando 0-2.8 m.
  const G4double shipInteriorRadius = 2.8*m + phantomRadius + 5.0*cm;
  const G4double shipHullOuterRadius = shipInteriorRadius + fHullThicknessCm * cm;

  // De adentro hacia afuera (blindaje pasivo legado, desactivado por defecto):
  // phantom -> polietileno -> aluminio
  const G4double polyInner = phantomRadius + 1.0*cm;
  const G4double polyOuter = polyInner + fPolyThickness * cm;
  const G4double alInner   = polyOuter;
  const G4double alOuter   = alInner + fAlThickness * cm;

  fSourceRadius = shipHullOuterRadius + 20.0 * cm;

  const G4double worldHalfSize = fSourceRadius + 50.0 * cm;
  G4Box* solidWorld = new G4Box("World", worldHalfSize, worldHalfSize, worldHalfSize);
  G4LogicalVolume* logicWorld = new G4LogicalVolume(solidWorld, vacuum, "World");
  G4VPhysicalVolume* physWorld = new G4PVPlacement(
      nullptr, G4ThreeVector(), logicWorld, "World", nullptr, false, 0, true);

  // Casco de la nave (aluminio estructural)
  G4Orb* solidHull = new G4Orb("ShipHull", shipHullOuterRadius);
  G4LogicalVolume* logicHull = new G4LogicalVolume(solidHull, aluminum, "ShipHull");
  new G4PVPlacement(nullptr, G4ThreeVector(), logicHull, "ShipHull",
                     logicWorld, false, 0, true);
  logicHull->SetVisAttributes(new G4VisAttributes(G4Colour(0.7,0.7,0.75,0.15)));

  // Interior de la nave (vacio) -- aqui se confina el campo magnetico activo
  G4Orb* solidInterior = new G4Orb("ShipInterior", shipInteriorRadius);
  G4LogicalVolume* logicInterior = new G4LogicalVolume(solidInterior, vacuum, "ShipInterior");
  new G4PVPlacement(nullptr, G4ThreeVector(), logicInterior, "ShipInterior",
                     logicHull, false, 0, true);

  // Sin material dentro de ShipInterior, una particula cargada cuyo radio de
  // giro en el campo no llegue a tocar el phantom ni el casco circularia
  // indefinidamente (Geant4 no la detiene sola). Se limita la longitud de
  // trayectoria dentro de este volumen para descartarla tras unas cuantas
  // vueltas maximo, en vez de trackearla sin fin (requiere G4StepLimiterPhysics
  // registrado en la physics list, ver main.cc).
  G4UserLimits* interiorLimits = new G4UserLimits();
  interiorLimits->SetUserMaxTrackLength(20.0 * (2.0 * shipInteriorRadius));
  logicInterior->SetUserLimits(interiorLimits);

  G4LogicalVolume* motherLVForPhantom = logicInterior;

  if (fShieldOn) {
    // Capa 1 (afuera): casco de aluminio del blindaje pasivo legado
    G4Orb* solidAl = new G4Orb("ShieldAl", alOuter);
    G4LogicalVolume* logicAl = new G4LogicalVolume(solidAl, aluminum, "ShieldAl");
    new G4PVPlacement(nullptr, G4ThreeVector(), logicAl, "ShieldAl",
                       logicInterior, false, 0, true);
    logicAl->SetVisAttributes(new G4VisAttributes(G4Colour(0.7,0.7,0.75,0.25)));

    // Capa 2 (adentro): revestimiento de polietileno, dentro del aluminio
    G4Orb* solidPoly = new G4Orb("ShieldPoly", polyOuter);
    G4LogicalVolume* logicPoly = new G4LogicalVolume(solidPoly, polyeth, "ShieldPoly");
    new G4PVPlacement(nullptr, G4ThreeVector(), logicPoly, "ShieldPoly",
                       logicAl, false, 0, true);
    logicPoly->SetVisAttributes(new G4VisAttributes(G4Colour(0.6,0.6,1.0,0.3)));

    motherLVForPhantom = logicPoly;
  }

  // Phantom (donde se mide dosis), ubicado en X segun la posicion del astronauta
  G4Orb* solidPhantom = new G4Orb("Phantom", phantomRadius);
  fLogicPhantom = new G4LogicalVolume(solidPhantom, tissue, "Phantom");
  fLogicPhantom->SetVisAttributes(new G4VisAttributes(G4Colour(1.0,0.8,0.6,0.6)));

  new G4PVPlacement(nullptr, G4ThreeVector(fAstronautXCm * cm, 0., 0.), fLogicPhantom,
                     "Phantom", motherLVForPhantom, false, 0, true);

  // Campo magnetico activo, confinado al interior de la nave (no a todo el mundo)
  if (fFieldOn) {
    G4UniformMagField* magField = new G4UniformMagField(G4ThreeVector(0., 0., fBzTesla * tesla));
    G4FieldManager* localFieldMgr = new G4FieldManager();
    localFieldMgr->SetDetectorField(magField);
    localFieldMgr->CreateChordFinder(magField);
    logicInterior->SetFieldManager(localFieldMgr, true);
  }

  return physWorld;
}
