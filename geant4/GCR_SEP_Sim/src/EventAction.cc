#include "EventAction.hh"
#include "RunAction.hh"
#include "PrimaryGeneratorAction.hh"
#include "G4Event.hh"
#include "G4RunManager.hh"

EventAction::EventAction(RunAction* runAction)
  : fRunAction(runAction)
{}

void EventAction::BeginOfEventAction(const G4Event*)
{
  fEdep = 0.0;
}

void EventAction::EndOfEventAction(const G4Event*)
{
  auto* generator = static_cast<const PrimaryGeneratorAction*>(
      G4RunManager::GetRunManager()->GetUserPrimaryGeneratorAction());
  fRunAction->AddEdep(fEdep, generator->GetLastSpecies());
}
