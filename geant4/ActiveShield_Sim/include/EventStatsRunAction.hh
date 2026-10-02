// Scorer por evento (requisito R1 de plan_barrido.md, con R12 y los
// diagnosticos de P3): suma el deposito de cada evento por organo y por
// categoria, y acumula S1/S2 con esos totales. N es el numero de eventos
// (= primarios, uno por evento), incluidos los que no depositan nada.
//
// Se apoya en la malla de scoring por comandos ya existente (PhantomMesh /
// energyDeposit): lee su mapa de hits del evento en G4Run::RecordEvent, antes
// de que G4ScoringManager lo acumule. No cambia lo que escribe
// ICRP110UserScoreWriter.
#ifndef EventStatsRunAction_h
#define EventStatsRunAction_h 1

#include "G4Run.hh"
#include "G4UserRunAction.hh"
#include "G4UserSteppingAction.hh"
#include "globals.hh"

#include <memory>
#include <vector>

class G4GenericMessenger;

// Configuracion fijada por comandos /eventStats/* (difundidos a los hilos).
struct EventStatsConfig {
  G4bool enabled = false;
  G4String sex = "male";
  G4String section = "full";
  G4String collection = "PhantomMesh/energyDeposit";
  G4String categoryFile;   // lineas: <categoria> <organ_id> <peso>
  G4String output = "EventStats.tsv";
  G4String perEventFile;   // R12: totales por evento de las categorias
  std::vector<G4int> checkpoints;  // M acumulados (event_id < M)
};

// Tablas de solo lectura compartidas entre hilos: organo de cada voxel de
// la malla y pesos de categoria.
struct EventStatsTables {
  G4int nx = 0, ny = 0, nz = 0;
  std::vector<G4int> organOfMeshIndex;  // indice de malla -> organ_id
  G4int nOrgans = 0;
  std::vector<G4String> categoryNames;
  // organ_id -> lista (categoria, peso)
  std::vector<std::vector<std::pair<G4int, G4double>>> categoriesOfOrgan;
};

struct EventStatsAccumulator {
  G4double nEvents = 0;
  std::vector<G4double> s1, s2, s3, s4, maxValue;  // s3/s4: para la VOV
  std::vector<G4double> nNonZero;
  std::vector<G4long> maxEvent;
  void Resize(std::size_t n);
  void Add(std::size_t i, G4double value, G4long eventId);
  void Merge(const EventStatsAccumulator& other);
};

class EventStatsRun : public G4Run {
 public:
  EventStatsRun(const EventStatsConfig& config);
  void RecordEvent(const G4Event* event) override;
  void Merge(const G4Run* run) override;
  void Write() const;
  // R6: trazas cortadas por el limite de longitud (G4UserSpecialCuts).
  void AddTruncated(G4double kineticEnergy, G4bool primary);

 private:
  std::size_t SegmentOf(G4long eventId) const;
  EventStatsConfig fConfig;
  std::shared_ptr<const EventStatsTables> fTables;
  G4int fCollectionId = -1;
  // Un acumulador por tramo de checkpoints: [0,M1), [M1,M2), ..., [Mk,inf).
  std::vector<EventStatsAccumulator> fOrgans, fCategories;
  std::vector<G4double> fEventOrgan;   // buffer por evento
  std::vector<G4int> fTouched;
  std::vector<G4double> fEventCategory;
  std::vector<std::pair<G4long, std::vector<G4double>>> fPerEvent;
  G4double fTruncatedTracks = 0, fTruncatedPrimaries = 0, fTruncatedEnergy = 0;
};

// Cuenta las trazas que mata G4UserSpecialCuts (limite de longitud de
// MagnetEnvelope). Sin EventStats activo no hace nada.
class EventStatsSteppingAction : public G4UserSteppingAction {
 public:
  void UserSteppingAction(const G4Step* step) override;
};

class EventStatsRunAction : public G4UserRunAction {
 public:
  EventStatsRunAction();
  ~EventStatsRunAction() override;
  G4Run* GenerateRun() override;
  void EndOfRunAction(const G4Run* run) override;

 private:
  void SetCheckpoints(G4String value);
  EventStatsConfig fConfig;
  G4String fCheckpointsText;
  G4GenericMessenger* fMessenger;
};

#endif
