#include "G4RunManagerFactory.hh"
#include "G4UImanager.hh"
#include "G4UIExecutive.hh"
#include "G4VisExecutive.hh"
#include "G4PhysListFactory.hh"
#include "G4StepLimiterPhysics.hh"
#include "Randomize.hh"

#include "DetectorConstruction.hh"
#include "ActionInitialization.hh"

int main(int argc, char** argv)
{
  G4UIExecutive* ui = nullptr;
  if (argc == 1) {
    ui = new G4UIExecutive(argc, argv);
  }

  auto* runManager = G4RunManagerFactory::CreateRunManager(G4RunManagerType::Serial);

  runManager->SetUserInitialization(new DetectorConstruction());

  G4PhysListFactory physListFactory;
  G4VModularPhysicsList* physicsList = physListFactory.GetReferencePhysList("Shielding");
  // Habilita que G4UserLimits::SetUserMaxTrackLength() se respete (usado en
  // ShipInterior para no dejar particulas dando vueltas indefinidamente
  // dentro del campo magnetico confinado, ver DetectorConstruction.cc).
  physicsList->RegisterPhysics(new G4StepLimiterPhysics());
  runManager->SetUserInitialization(physicsList);

  runManager->SetUserInitialization(new ActionInitialization());

  runManager->Initialize();

  G4VisManager* visManager = new G4VisExecutive();
  visManager->Initialize();

  G4UImanager* UImanager = G4UImanager::GetUIpointer();

  if (ui) {
    UImanager->ApplyCommand("/control/execute macros/init_vis.mac");
    ui->SessionStart();
    delete ui;
  } else {
    G4String command = "/control/execute ";
    G4String fileName = argv[1];
    UImanager->ApplyCommand(command + fileName);
  }

  delete visManager;
  delete runManager;
  return 0;
}
