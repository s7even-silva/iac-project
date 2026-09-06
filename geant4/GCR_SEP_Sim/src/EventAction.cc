#include "EventAction.hh"
#include "RunAction.hh"
#include "G4Event.hh"

EventAction::EventAction(RunAction* runAction)
  : fRunAction(runAction)
{}

void EventAction::BeginOfEventAction(const G4Event*)
{
  fEdep = 0.0;
}

void EventAction::EndOfEventAction(const G4Event*)
{
  fRunAction->AddEdep(fEdep);
}
