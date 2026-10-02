#include "EventStatsRunAction.hh"

#include "G4Event.hh"
#include "G4GenericMessenger.hh"
#include "G4HCofThisEvent.hh"
#include "G4RunManager.hh"
#include "G4Step.hh"
#include "G4TransportationProcessType.hh"
#include "G4VProcess.hh"
#include "G4SDManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4THitsMap.hh"
#include "G4Threading.hh"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <limits>
#include <map>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <tuple>

namespace {

[[noreturn]] void Fail(const G4String& message)
{
  G4Exception("EventStats", "EventStats001", FatalException, message);
  throw std::runtime_error(message);  // no se alcanza; satisface [[noreturn]]
}

// Mismo recorrido de archivos que ICRP110UserScoreWriter::DumpQuantityToFile:
// Data.dat da las rebanadas y cada rebanada el organ_id de sus voxels.
std::shared_ptr<EventStatsTables> LoadTables(const EventStatsConfig& config)
{
  auto tables = std::make_shared<EventStatsTables>();
  const G4String sexDir = config.sex == "male" ? "AM" : "AF";
  const G4String prefix = config.sex == "male" ? "Male" : "Female";
  G4String dataName;
  if (config.section == "head") dataName = prefix + "Head.dat";
  else if (config.section == "trunk") dataName = prefix + "Trunk.dat";
  else dataName = prefix + "Data.dat";
  std::ifstream data("ICRPdata/" + dataName);
  if (!data) Fail("No se pudo abrir ICRPdata/" + dataName);
  G4int nSlices = 0, nx = 0, ny = 0;
  data >> nSlices >> nx >> ny;
  for (G4int i = 0; i < 58; ++i) data.ignore(256, '\n');
  std::vector<G4String> slices(nSlices);
  for (auto& name : slices) data >> name;
  if (!data) Fail("Data.dat incompleto: " + dataName);

  std::vector<G4int> organOfVoxel;
  organOfVoxel.reserve(static_cast<std::size_t>(nx) * ny * nSlices);
  for (const auto& name : slices) {
    std::ifstream slice("ICRPdata/ICRP110_g4dat/" + sexDir + "/" + name);
    G4int a = 0, b = 0, c = 0;
    if (!(slice >> a >> b >> c)) Fail("No se pudo leer la rebanada " + name);
    for (G4int i = 0; i < nx * ny; ++i) {
      G4int id = 0;
      if (!(slice >> id)) Fail("Rebanada incompleta " + name);
      organOfVoxel.push_back(id);
    }
  }
  tables->nx = nx;
  tables->ny = ny;
  tables->nz = nSlices;
  // Indice de malla (G4VScoreWriter::GetIndex) = x*ny*nz + y*nz + z;
  // voxel del fantoma = x + nx*y + nx*ny*z.
  tables->organOfMeshIndex.resize(organOfVoxel.size());
  G4int maxOrgan = 141;
  for (G4int x = 0; x < nx; ++x)
    for (G4int y = 0; y < ny; ++y)
      for (G4int z = 0; z < nSlices; ++z) {
        G4int organ = organOfVoxel[x + nx * y + nx * ny * z];
        tables->organOfMeshIndex[(static_cast<std::size_t>(x) * ny + y) * nSlices + z] = organ;
        maxOrgan = std::max(maxOrgan, organ);
      }

  std::vector<std::tuple<G4String, G4int, G4double>> entries;
  if (!config.categoryFile.empty()) {
    std::ifstream categories(config.categoryFile);
    if (!categories) Fail("No se pudo abrir " + config.categoryFile);
    std::string line;
    while (std::getline(categories, line)) {
      if (line.empty() || line[0] == '#') continue;
      std::istringstream fields(line);
      G4String name;
      G4int organ = 0;
      G4double weight = 0;
      if (!(fields >> name >> organ >> weight) || organ < 0)
        Fail("Linea invalida en " + config.categoryFile + ": " + line);
      entries.emplace_back(name, organ, weight);
      maxOrgan = std::max(maxOrgan, organ);
    }
  }
  tables->nOrgans = maxOrgan + 1;
  tables->categoriesOfOrgan.resize(tables->nOrgans);
  for (const auto& [name, organ, weight] : entries) {
    auto it = std::find(tables->categoryNames.begin(), tables->categoryNames.end(), name);
    G4int index = static_cast<G4int>(it - tables->categoryNames.begin());
    if (it == tables->categoryNames.end()) tables->categoryNames.push_back(name);
    tables->categoriesOfOrgan[organ].emplace_back(index, weight);
  }
  return tables;
}

std::shared_ptr<const EventStatsTables> SharedTables(const EventStatsConfig& config)
{
  static std::mutex mutex;
  static std::map<std::tuple<G4String, G4String, G4String>, std::shared_ptr<const EventStatsTables>> cache;
  std::lock_guard<std::mutex> lock(mutex);
  auto key = std::make_tuple(config.sex, config.section, config.categoryFile);
  auto& slot = cache[key];
  if (!slot) slot = LoadTables(config);
  return slot;
}

}  // namespace

void EventStatsAccumulator::Resize(std::size_t n)
{
  s1.assign(n, 0.);
  s2.assign(n, 0.);
  s3.assign(n, 0.);
  s4.assign(n, 0.);
  maxValue.assign(n, 0.);
  nNonZero.assign(n, 0.);
  maxEvent.assign(n, -1);
}

void EventStatsAccumulator::Add(std::size_t i, G4double value, G4long eventId)
{
  s1[i] += value;
  const G4double v2 = value * value;
  s2[i] += v2;
  s3[i] += v2 * value;
  s4[i] += v2 * v2;
  nNonZero[i] += 1;
  if (value > maxValue[i]) {
    maxValue[i] = value;
    maxEvent[i] = eventId;
  }
}

void EventStatsAccumulator::Merge(const EventStatsAccumulator& other)
{
  nEvents += other.nEvents;
  for (std::size_t i = 0; i < s1.size(); ++i) {
    s1[i] += other.s1[i];
    s2[i] += other.s2[i];
    s3[i] += other.s3[i];
    s4[i] += other.s4[i];
    nNonZero[i] += other.nNonZero[i];
    if (other.maxValue[i] > maxValue[i]) {
      maxValue[i] = other.maxValue[i];
      maxEvent[i] = other.maxEvent[i];
    }
  }
}

EventStatsRun::EventStatsRun(const EventStatsConfig& config) : fConfig(config)
{
  std::sort(fConfig.checkpoints.begin(), fConfig.checkpoints.end());
  fTables = SharedTables(fConfig);
  const std::size_t segments = fConfig.checkpoints.size() + 1;
  fOrgans.resize(segments);
  fCategories.resize(segments);
  for (auto& acc : fOrgans) acc.Resize(fTables->nOrgans);
  for (auto& acc : fCategories) acc.Resize(fTables->categoryNames.size());
  fEventOrgan.assign(fTables->nOrgans, 0.);
  fEventCategory.assign(fTables->categoryNames.size(), 0.);
}

std::size_t EventStatsRun::SegmentOf(G4long eventId) const
{
  const auto& c = fConfig.checkpoints;
  return static_cast<std::size_t>(std::upper_bound(c.begin(), c.end(), eventId) - c.begin());
}

void EventStatsRun::RecordEvent(const G4Event* event)
{
  G4Run::RecordEvent(event);
  const G4long eventId = event->GetEventID();
  const std::size_t segment = SegmentOf(eventId);
  fOrgans[segment].nEvents += 1;
  fCategories[segment].nEvents += 1;

  auto* hce = event->GetHCofThisEvent();
  if (!hce) return;
  if (fCollectionId < 0) {
    fCollectionId = G4SDManager::GetSDMpointer()->GetCollectionID(fConfig.collection);
    if (fCollectionId < 0) Fail("No existe la coleccion " + fConfig.collection);
    // La malla tiene que ser la del fantoma (mismo supuesto que el writer).
  }
  auto* hits = dynamic_cast<G4THitsMap<G4double>*>(hce->GetHC(fCollectionId));
  if (!hits) return;

  const auto& organOf = fTables->organOfMeshIndex;
  for (const auto& [index, value] : *hits->GetMap()) {
    if (index < 0 || static_cast<std::size_t>(index) >= organOf.size())
      Fail("Indice de malla fuera del fantoma: la malla no coincide con los voxels");
    const G4int organ = organOf[index];
    if (fEventOrgan[organ] == 0.) fTouched.push_back(organ);
    fEventOrgan[organ] += *value / joule;
  }
  G4bool anyCategory = false;
  for (G4int organ : fTouched) {
    const G4double e = fEventOrgan[organ];
    if (e != 0.) fOrgans[segment].Add(organ, e, eventId);
    for (const auto& [category, weight] : fTables->categoriesOfOrgan[organ]) {
      fEventCategory[category] += weight * e;
      anyCategory = true;
    }
    fEventOrgan[organ] = 0.;
  }
  fTouched.clear();
  if (!anyCategory) return;
  for (std::size_t c = 0; c < fEventCategory.size(); ++c)
    if (fEventCategory[c] != 0.) fCategories[segment].Add(c, fEventCategory[c], eventId);
  if (!fConfig.perEventFile.empty()) fPerEvent.emplace_back(eventId, fEventCategory);
  std::fill(fEventCategory.begin(), fEventCategory.end(), 0.);
}

void EventStatsRun::Merge(const G4Run* run)
{
  const auto* other = static_cast<const EventStatsRun*>(run);
  for (std::size_t s = 0; s < fOrgans.size(); ++s) {
    fOrgans[s].Merge(other->fOrgans[s]);
    fCategories[s].Merge(other->fCategories[s]);
  }
  fPerEvent.insert(fPerEvent.end(), other->fPerEvent.begin(), other->fPerEvent.end());
  fTruncatedTracks += other->fTruncatedTracks;
  fTruncatedPrimaries += other->fTruncatedPrimaries;
  fTruncatedEnergy += other->fTruncatedEnergy;
  G4Run::Merge(run);
}

void EventStatsRun::AddTruncated(G4double kineticEnergy, G4bool primary)
{
  fTruncatedTracks += 1;
  if (primary) fTruncatedPrimaries += 1;
  fTruncatedEnergy += kineticEnergy;
}

void EventStatsSteppingAction::UserSteppingAction(const G4Step* step)
{
  const G4VProcess* process = step->GetPostStepPoint()->GetProcessDefinedStep();
  if (!process || process->GetProcessType() != fGeneral ||
      process->GetProcessSubType() != USER_SPECIAL_CUTS)
    return;
  auto* run = dynamic_cast<EventStatsRun*>(G4RunManager::GetRunManager()->GetNonConstCurrentRun());
  if (!run) return;
  const G4Track* track = step->GetTrack();
  run->AddTruncated(step->GetPreStepPoint()->GetKineticEnergy(), track->GetParentID() == 0);
}

void EventStatsRun::Write() const
{
  std::ofstream out(fConfig.output);
  if (!out) Fail("No se pudo escribir " + fConfig.output);
  out << std::setprecision(17);
  out << "# EventStats v1: una fila por (checkpoint, organo|categoria); valores en J por evento.\n"
      << "# M = eventos con event_id < checkpoint (incluye los que no depositan).\n"
      << "# mean_J = S1/M; se_mean_J = sqrt(s^2/M), s^2 = (S2 - S1^2/M)/(M-1).\n"
      << "# vov = varianza relativa de la varianza (MCNP, Pederson-Forster-Booth):\n"
      << "#   (S4 - 4 S1 S3/M + 6 S1^2 S2/M^2 - 3 S1^4/M^3) / (S2 - S1^2/M)^2 - 1/M\n"
      << "# events_total " << GetNumberOfEvent() << "\n"
      << "# collection " << fConfig.collection << "\n"
      << "# truncated_tracks " << fTruncatedTracks << " truncated_primaries " << fTruncatedPrimaries
      << " truncated_kinetic_energy_MeV " << fTruncatedEnergy / MeV << "\n"
      << "# category_file " << (fConfig.categoryFile.empty() ? "-" : fConfig.categoryFile) << "\n"
      << "checkpoint\tM\tkind\tid\tS1_J\tS2_J2\tn_nonzero\tmax_J\tmax_event_id\tmean_J\tse_mean_J\tS3_J3\tS4_J4\tvov\n";
  std::vector<G4long> labels(fConfig.checkpoints.begin(), fConfig.checkpoints.end());
  labels.push_back(-1);  // -1 = corrida completa
  EventStatsAccumulator organs, categories;
  organs.Resize(fOrgans[0].s1.size());
  categories.Resize(fCategories[0].s1.size());
  auto row = [&](G4long label, G4double m, const char* kind, const G4String& id,
                 const EventStatsAccumulator& acc, std::size_t i) {
    G4double mean = m > 0 ? acc.s1[i] / m : 0.;
    G4double se = 0.;
    if (m > 1) {
      G4double var = (acc.s2[i] - acc.s1[i] * acc.s1[i] / m) / (m - 1);
      se = std::sqrt(std::max(var, 0.) / m);
    }
    // VOV: sensible a los eventos grandes y raros; MCNP pide < 0.1 para
    // confiar en el IC del SE. Sin al menos 2 eventos con deposito no hay
    // varianza, y se escribe inf para que no pase ningun umbral.
    G4double vov = std::numeric_limits<G4double>::infinity();
    const G4double s1 = acc.s1[i], s2 = acc.s2[i];
    const G4double den = (s2 - s1 * s1 / m) * (s2 - s1 * s1 / m);
    if (acc.nNonZero[i] >= 2 && den > 0.) {
      const G4double num = acc.s4[i] - 4. * s1 * acc.s3[i] / m + 6. * s1 * s1 * s2 / (m * m)
                           - 3. * s1 * s1 * s1 * s1 / (m * m * m);
      vov = num / den - 1. / m;
    }
    out << label << '\t' << m << '\t' << kind << '\t' << id << '\t' << acc.s1[i] << '\t'
        << acc.s2[i] << '\t' << acc.nNonZero[i] << '\t' << acc.maxValue[i] << '\t'
        << acc.maxEvent[i] << '\t' << mean << '\t' << se << '\t' << acc.s3[i] << '\t'
        << acc.s4[i] << '\t' << vov << '\n';
  };
  for (std::size_t s = 0; s < labels.size(); ++s) {
    organs.Merge(fOrgans[s]);
    categories.Merge(fCategories[s]);
    const G4double m = organs.nEvents;
    for (std::size_t i = 0; i < organs.s1.size(); ++i)
      if (organs.nNonZero[i] > 0) row(labels[s], m, "organ", std::to_string(i), organs, i);
    for (std::size_t i = 0; i < categories.s1.size(); ++i)
      row(labels[s], m, "category", fTables->categoryNames[i], categories, i);
  }

  if (fConfig.perEventFile.empty()) return;
  std::ofstream per(fConfig.perEventFile);
  if (!per) Fail("No se pudo escribir " + fConfig.perEventFile);
  per << std::setprecision(17) << "# events_total " << GetNumberOfEvent()
      << " (los eventos sin deposito en ninguna categoria no aparecen)\nevent_id";
  for (const auto& name : fTables->categoryNames) per << '\t' << name;
  per << '\n';
  auto rows = fPerEvent;
  std::sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
  for (const auto& [eventId, values] : rows) {
    per << eventId;
    for (G4double v : values) per << '\t' << v;
    per << '\n';
  }
}

EventStatsRunAction::EventStatsRunAction()
{
  fMessenger = new G4GenericMessenger(this, "/eventStats/", "Scorer por evento (R1)");
  fMessenger->DeclareProperty("enable", fConfig.enabled, "Activa el scorer por evento");
  fMessenger->DeclareProperty("phantomSex", fConfig.sex, "male | female").SetCandidates("male female");
  fMessenger->DeclareProperty("phantomSection", fConfig.section, "head | trunk | full")
    .SetCandidates("head trunk full");
  fMessenger->DeclareProperty("collection", fConfig.collection, "Coleccion <malla>/<cantidad>");
  fMessenger->DeclareProperty("categoryFile", fConfig.categoryFile,
                              "Archivo <categoria> <organ_id> <peso>");
  fMessenger->DeclareProperty("output", fConfig.output, "Archivo TSV de salida");
  fMessenger->DeclareProperty("perEventFile", fConfig.perEventFile,
                              "Archivo con los totales por evento de las categorias (R12)");
  fMessenger->DeclareMethod("checkpoints", &EventStatsRunAction::SetCheckpoints,
                            "Lista de M acumulados separados por comas (p. ej. 2500,5000,10000)");
}

EventStatsRunAction::~EventStatsRunAction() { delete fMessenger; }

void EventStatsRunAction::SetCheckpoints(G4String value)
{
  // Separados por comas: el mensajero solo entrega el primer token de un
  // argumento con espacios.
  fConfig.checkpoints.clear();
  std::replace(value.begin(), value.end(), ',', ' ');
  std::istringstream fields(value);
  G4int m = 0;
  while (fields >> m) {
    if (m <= 0) Fail("Checkpoint no positivo: " + value);
    fConfig.checkpoints.push_back(m);
  }
}

G4Run* EventStatsRunAction::GenerateRun()
{
  if (!fConfig.enabled) return new G4Run;
  return new EventStatsRun(fConfig);
}

void EventStatsRunAction::EndOfRunAction(const G4Run* run)
{
  if (!fConfig.enabled || !IsMaster()) return;
  static_cast<const EventStatsRun*>(run)->Write();
  G4cout << "EventStats: " << run->GetNumberOfEvent() << " eventos -> " << fConfig.output << G4endl;
}
