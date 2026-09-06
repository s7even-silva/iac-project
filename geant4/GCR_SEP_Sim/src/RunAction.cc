#include "RunAction.hh"
#include "DetectorConstruction.hh"
#include "PrimaryGeneratorAction.hh"

#include "G4Run.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"

#include <fstream>
#include <sys/stat.h>

RunAction::RunAction() = default;

void RunAction::BeginOfRunAction(const G4Run*)
{
  fEdep = 0.0;
}

void RunAction::EndOfRunAction(const G4Run* run)
{
  G4int nEvents = run->GetNumberOfEvent();
  if (nEvents == 0) return;

  auto* detector = static_cast<const DetectorConstruction*>(
      G4RunManager::GetRunManager()->GetUserDetectorConstruction());
  auto* generator = static_cast<const PrimaryGeneratorAction*>(
      G4RunManager::GetRunManager()->GetUserPrimaryGeneratorAction());

  G4double mass = detector->GetPhantomLV()->GetMass();
  G4double edepJoule = fEdep * MeV / joule;
  G4double massKg = mass / kg;
  G4double doseGy = (massKg > 0) ? edepJoule / massKg : 0.0;

  G4double fieldT = detector->GetFieldOn() ? detector->GetFieldValueTesla() : 0.0;
  G4double astronautXm = detector->GetAstronautXCm() / 100.0;

  G4bool fileExists = false;
  {
    struct stat buffer;
    fileExists = (stat("resultados_dosis_sweep.csv", &buffer) == 0);
  }

  std::ofstream out("resultados_dosis_sweep.csv", std::ios::app);
  if (!fileExists) {
    out << "modelo,fase,field_T,astronaut_x_m,n_eventos,edep_MeV,masa_kg,dosis_Gy\n";
  }
  out << generator->GetModel() << ","
      << generator->GetPhase() << ","
      << fieldT << ","
      << astronautXm << ","
      << nEvents << ","
      << fEdep << ","
      << massKg << ","
      << doseGy << "\n";
  out.close();

  G4cout << "\n===== FIN DEL RUN =====\n"
         << "Modelo: " << generator->GetModel()
         << " | Fase: " << generator->GetPhase() << "\n"
         << "Campo: " << fieldT << " T | Posicion astronauta: " << astronautXm << " m\n"
         << "Eventos: " << nEvents << "\n"
         << "Energia depositada en phantom: " << fEdep << " MeV\n"
         << "Masa del phantom: " << massKg << " kg\n"
         << "Dosis absorbida: " << doseGy << " Gy\n"
         << "Fila agregada a resultados_dosis_sweep.csv\n"
         << "========================\n" << G4endl;
}
