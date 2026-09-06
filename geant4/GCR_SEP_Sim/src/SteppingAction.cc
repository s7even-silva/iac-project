#include "SteppingAction.hh"
#include "EventAction.hh"

#include "G4Step.hh"
#include "G4Track.hh"
#include "G4LogicalVolume.hh"

SteppingAction::SteppingAction(EventAction* eventAction)
  : fEventAction(eventAction)
{}

void SteppingAction::UserSteppingAction(const G4Step* step)
{
  G4LogicalVolume* volume = step->GetPreStepPoint()->GetTouchableHandle()
                                ->GetVolume()->GetLogicalVolume();

  if (volume->GetName() != "Phantom") return;

  G4double edep = step->GetTotalEnergyDeposit();
  if (edep > 0.) {
    fEventAction->AddEdep(edep);
  }
}
