#include "TabulatedMagneticField.hh"
#include "G4SystemOfUnits.hh"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>

MagneticFieldMap::MagneticFieldMap(const std::string& filename) {
  std::ifstream input(filename);
  if (!input) throw std::runtime_error("Cannot open field map: " + filename);
  // Strip comments before parsing; reject malformed, incomplete or extra data.
  std::stringstream data;
  for (std::string line; std::getline(input, line);)
    data << line.substr(0, line.find('#')) << '\n';
  const auto read = [&]() {
    double value;
    if (!(data >> value) || !std::isfinite(value))
      throw std::runtime_error("Invalid or incomplete field map: " + filename);
    return value;
  };
  std::size_t count = 1;
  for (auto& size : fSize) {
    const double value = read();
    if (value < 2 || value > 100000 || std::floor(value) != value)
      throw std::runtime_error("Each field grid dimension must be an integer >= 2");
    size = static_cast<std::size_t>(value);
    if (count > std::numeric_limits<std::size_t>::max() / size)
      throw std::runtime_error("Field grid size overflow");
    count *= size;
  }
  for (int axis = 0; axis < 3; ++axis) fMinimum[axis] = read() * m;
  for (int axis = 0; axis < 3; ++axis) {
    fSpacing[axis] = read() * m;
    if (fSpacing[axis] <= 0)
      throw std::runtime_error("Field grid spacing must be positive");
    fMaximum[axis] = fMinimum[axis] + (fSize[axis] - 1) * fSpacing[axis];
    if (!std::isfinite(fMinimum[axis]) || !std::isfinite(fMaximum[axis]) ||
        fMaximum[axis] <= fMinimum[axis])
      throw std::runtime_error("Invalid field grid extent");
  }
  // No reserve from an untrusted size: a truncated file fails before allocating
  // its declared full grid. Ordering: x fastest, then y, then z.
  for (std::size_t z = 0; z < fSize[2]; ++z)
    for (std::size_t y = 0; y < fSize[1]; ++y)
      for (std::size_t x = 0; x < fSize[0]; ++x) {
        G4ThreeVector b;
        for (int axis = 0; axis < 3; ++axis) b[axis] = read() * tesla;
        if (!std::isfinite(b.mag2())) throw std::runtime_error("Invalid field magnitude");
        fValues.push_back(b);
        if (x == 0 || y == 0 || z == 0 || x == fSize[0]-1 ||
            y == fSize[1]-1 || z == fSize[2]-1)
          fBoundaryMaximum = std::max(fBoundaryMaximum, b.mag());
      }
  std::string extra;
  if (data >> extra) throw std::runtime_error("Unexpected extra field map data");
}

G4ThreeVector MagneticFieldMap::Evaluate(const G4ThreeVector& point) const {
  std::array<std::size_t, 3> index;
  std::array<double, 3> weight;
  for (int axis = 0; axis < 3; ++axis) {
    if (!std::isfinite(point[axis]) || point[axis] < fMinimum[axis] ||
        point[axis] > fMaximum[axis]) return {};  // Explicit zero outside the map.
    const double cell = (point[axis] - fMinimum[axis]) / fSpacing[axis];
    index[axis] = std::min(static_cast<std::size_t>(cell), fSize[axis] - 2);
    weight[axis] = std::clamp(cell - index[axis], 0., 1.);
  }
  G4ThreeVector result;
  for (std::size_t z = 0; z < 2; ++z)
    for (std::size_t y = 0; y < 2; ++y)
      for (std::size_t x = 0; x < 2; ++x) {
        const auto offset = ((index[2]+z)*fSize[1]+index[1]+y)*fSize[0]+index[0]+x;
        result += fValues[offset] * (x ? weight[0] : 1-weight[0]) *
                  (y ? weight[1] : 1-weight[1]) * (z ? weight[2] : 1-weight[2]);
      }
  return result;
}

void TabulatedMagneticField::GetFieldValue(const G4double point[4], G4double* field) const {
  const auto b = fMap->Evaluate({point[0], point[1], point[2]}) * fScale;
  for (int axis = 0; axis < 3; ++axis) field[axis] = b[axis];
}
