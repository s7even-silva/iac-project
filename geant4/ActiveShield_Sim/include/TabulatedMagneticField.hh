#ifndef TABULATED_MAGNETIC_FIELD_HH
#define TABULATED_MAGNETIC_FIELD_HH

#include "G4MagneticField.hh"
#include "G4ThreeVector.hh"
#include <array>
#include <memory>
#include <string>
#include <vector>

// Immutable regular Cartesian grid shared by the master and worker threads.
// File coordinates are metres, field components tesla, in the Geant4 world frame.
class MagneticFieldMap {
 public:
  explicit MagneticFieldMap(const std::string& filename);
  G4ThreeVector Evaluate(const G4ThreeVector& point) const;
  G4ThreeVector Minimum() const { return fMinimum; }
  G4ThreeVector Maximum() const { return fMaximum; }
  double BoundaryMaximum() const { return fBoundaryMaximum; }

 private:
  std::array<std::size_t, 3> fSize;
  G4ThreeVector fMinimum, fMaximum, fSpacing;
  std::vector<G4ThreeVector> fValues;
  double fBoundaryMaximum = 0.;
};

class TabulatedMagneticField : public G4MagneticField {
 public:
  TabulatedMagneticField(std::shared_ptr<const MagneticFieldMap> map, double scale)
      : fMap(std::move(map)), fScale(scale) {}
  void GetFieldValue(const G4double point[4], G4double* field) const override;

 private:
  std::shared_ptr<const MagneticFieldMap> fMap;
  double fScale;
};
#endif
