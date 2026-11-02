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
// Text maps, or binary maps (.bmap, field/compute_field_volumetric.py) that
// start with "IACBMAP1": uint64 nx ny nz, float64 minimum and spacing, then
// float32 values in the text order; little-endian.
class MagneticFieldMap {
 public:
  explicit MagneticFieldMap(const std::string& filename);
  G4ThreeVector Evaluate(const G4ThreeVector& point) const;
  G4ThreeVector Minimum() const { return fMinimum; }
  G4ThreeVector Maximum() const { return fMaximum; }
  double BoundaryMaximum() const { return fBoundaryMaximum; }

 private:
  void SetGrid(const double size[3], const double minimum[3], const double spacing[3]);
  void ReadBinary(std::istream& input, const std::string& filename);
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
