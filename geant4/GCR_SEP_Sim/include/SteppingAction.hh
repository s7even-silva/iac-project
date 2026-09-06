#pragma once
#include "G4UserSteppingAction.hh"
#include "globals.hh"

class EventAction;
class G4Step;

class SteppingAction : public G4UserSteppingAction {
public:
  explicit SteppingAction(EventAction* eventAction);
  ~SteppingAction() override = default;

  void UserSteppingAction(const G4Step* step) override;

private:
  EventAction* fEventAction;
};
