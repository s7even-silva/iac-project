#pragma once
#include "G4UserEventAction.hh"
#include "globals.hh"

class RunAction;
class G4Event;

class EventAction : public G4UserEventAction {
public:
  explicit EventAction(RunAction* runAction);
  ~EventAction() override = default;

  void BeginOfEventAction(const G4Event*) override;
  void EndOfEventAction(const G4Event*) override;

  void AddEdep(G4double edep) { fEdep += edep; }

private:
  RunAction* fRunAction;
  G4double fEdep = 0.0;
};
