#include "RunAction.hh"
#include "DetectorConstruction.hh"
#include "PrimaryGeneratorAction.hh"

#include "G4Run.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4PhysicalConstants.hh"

#include <fstream>
#include <sys/stat.h>

RunAction::RunAction() = default;

void RunAction::BeginOfRunAction(const G4Run*)
{
  fEdepBySpeciesMeV.clear();
  fNBySpecies.clear();
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
  G4double massKg = mass / kg;

  // dosis_Gy: dosis cruda de la corrida (todas las especies mezcladas en los
  // N eventos simulados) -- util para QA/depuracion, pero NO es una dosis
  // fisica real: no pesa cada especie por su flujo verdadero.
  G4double totalEdepMeV = 0.0;
  for (auto& kv : fEdepBySpeciesMeV) totalEdepMeV += kv.second;
  G4double doseGy = (massKg > 0) ? (totalEdepMeV * MeV / joule) / massKg : 0.0;

  // dosis_absoluta_Gy: normalizacion fisica real, sumando por especie
  // R[s] (Gy por primario simulado de esa especie) x W[s] (numero real de
  // primarios de esa especie que cruzan la esfera fuente). Ver deduccion y
  // formulas en AGENTS.md ("Dosis absoluta") -- para GCR el resultado es
  // Gy/dia (el flujo de OLTARIS ya viene por dia); para SEP es la dosis
  // aguda del evento completo (Oct 1989), sin factor de tiempo.
  G4double sourceRadiusCm = detector->GetSourceSphereRadius() / cm;
  G4double areaCm2 = CLHEP::pi * sourceRadiusCm * sourceRadiusCm;

  G4double doseAbsGy = 0.0;
  for (auto& kv : fEdepBySpeciesMeV) {
    const G4String& species = kv.first;
    G4int nSpecies = fNBySpecies[species];
    if (nSpecies == 0 || massKg <= 0) continue;

    G4double edepJoule = kv.second * MeV / joule;
    G4double responsePerPrimaryGy = edepJoule / massKg / nSpecies; // R[s]
    G4double integratedFlux = generator->GetIntegratedFlux(species); // particles/(day*cm2) o particles/cm2
    G4double physicalWeight = areaCm2 * integratedFlux; // W[s]: primarios/dia (GCR) o totales del evento (SEP)
    doseAbsGy += responsePerPrimaryGy * physicalWeight;
  }

  G4double fieldT = detector->GetFieldOn() ? detector->GetFieldValueTesla() : 0.0;
  G4double astronautXm = detector->GetAstronautXCm() / 100.0;

  G4bool fileExists = false;
  {
    struct stat buffer;
    fileExists = (stat("resultados_dosis_sweep.csv", &buffer) == 0);
  }

  std::ofstream out("resultados_dosis_sweep.csv", std::ios::app);
  if (!fileExists) {
    out << "modelo,fase,field_T,astronaut_x_m,n_eventos,edep_MeV,masa_kg,dosis_Gy,dosis_absoluta_Gy\n";
  }
  out << generator->GetModel() << ","
      << generator->GetPhase() << ","
      << fieldT << ","
      << astronautXm << ","
      << nEvents << ","
      << totalEdepMeV << ","
      << massKg << ","
      << doseGy << ","
      << doseAbsGy << "\n";
  out.close();

  G4cout << "\n===== FIN DEL RUN =====\n"
         << "Modelo: " << generator->GetModel()
         << " | Fase: " << generator->GetPhase() << "\n"
         << "Campo: " << fieldT << " T | Posicion astronauta: " << astronautXm << " m\n"
         << "Eventos: " << nEvents << "\n"
         << "Energia depositada en phantom: " << totalEdepMeV << " MeV\n"
         << "Masa del phantom: " << massKg << " kg\n"
         << "Dosis absorbida (cruda, sin ponderar): " << doseGy << " Gy\n"
         << "Dosis absoluta (ponderada por flujo real, " << (generator->GetModel() == "SEP" ? "evento completo" : "por dia") << "): "
         << doseAbsGy << " Gy\n"
         << "Fila agregada a resultados_dosis_sweep.csv\n"
         << "========================\n" << G4endl;
}
