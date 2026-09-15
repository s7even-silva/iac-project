//
// ********************************************************************
// * License and Disclaimer                                           *
// *                                                                  *
// * The  Geant4 software  is  copyright of the Copyright Holders  of *
// * the Geant4 Collaboration.  It is provided  under  the terms  and *
// * conditions of the Geant4 Software License,  included in the file *
// * LICENSE and available at  http://cern.ch/geant4/license .  These *
// * include a list of copyright holders.                             *
// *                                                                  *
// * Neither the authors of this software system, nor their employing *
// * institutes,nor the agencies providing financial support for this *
// * work  make  any representation or  warranty, express or implied, *
// * regarding  this  software system or assume any liability for its *
// * use.  Please see the license in the file  LICENSE  and URL above *
// * for the full disclaimer and the limitation of liability.         *
// *                                                                  *
// * This  code  implementation is the result of  the  scientific and *
// * technical work of the GEANT4 collaboration.                      *
// * By using,  copying,  modifying or  distributing the software (or *
// * any work based  on the software)  you  agree  to acknowledge its *
// * use  in  resulting  scientific  publications,  and indicate your *
// * acceptance of all terms of the Geant4 Software license.          *
// ********************************************************************
//
// Code developed by:
// S.Guatelli, M. Large and A. Malaroda, University of Wollongong
//
#include "ICRP110PhantomActionInitialization.hh"
#include "ICRP110PhantomPrimaryGeneratorAction.hh"

#include "G4UserEventAction.hh"
#include "G4Event.hh"
#include "G4Threading.hh"
#include "G4RunManager.hh"
#include "G4Run.hh"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <string>

namespace {
// One file per Geant4 thread: no shared lock and no scoring changes.
class DiagnosticEventAction final : public G4UserEventAction {
  std::ofstream output;
  void Record(const G4Event* event, const char* phase) {
    if (!output) return;
    auto now = std::chrono::steady_clock::now().time_since_epoch();
    auto run = G4RunManager::GetRunManager()->GetCurrentRun();
    output << "{\"run\":" << (run ? run->GetRunID() : -1)
           << ",\"event\":" << event->GetEventID()
           << ",\"thread\":" << G4Threading::G4GetThreadId()
           << ",\"phase\":\"" << phase << "\",\"monotonic_ns\":"
           << std::chrono::duration_cast<std::chrono::nanoseconds>(now).count()
           << "}" << std::endl;
  }
 public:
  DiagnosticEventAction() {
    const char* dir = std::getenv("G4_EVENT_DIAGNOSTICS_DIR");
    if (dir && *dir) output.open(std::string(dir) + "/thread-" +
                                std::to_string(G4Threading::G4GetThreadId()) + ".jsonl");
  }
  void BeginOfEventAction(const G4Event* event) override { Record(event, "begin"); }
  void EndOfEventAction(const G4Event* event) override { Record(event, "end"); }
};
}

ICRP110PhantomActionInitialization::ICRP110PhantomActionInitialization():
G4VUserActionInitialization()
{}

ICRP110PhantomActionInitialization::~ICRP110PhantomActionInitialization()
{}

void ICRP110PhantomActionInitialization::BuildForMaster() const
{}

void ICRP110PhantomActionInitialization::Build() const
{   
SetUserAction(new ICRP110PhantomPrimaryGeneratorAction);
SetUserAction(new DiagnosticEventAction);
}  
