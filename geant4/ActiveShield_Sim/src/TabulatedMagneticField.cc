#include "TabulatedMagneticField.hh"
#include "G4SystemOfUnits.hh"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>

MagneticFieldMap::MagneticFieldMap(const std::string& filename) {
  std::ifstream input(filename, std::ios::binary);
  if (!input) throw std::runtime_error("Cannot open field map: " + filename);
  char magic[8] = {};
  if (input.read(magic, sizeof magic) && std::string(magic, sizeof magic) == "IACBMAP1") {
    ReadBinary(input, filename);
  } else {
    input.clear();
    input.seekg(0);
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
    double grid[9];
    for (auto& value : grid) value = read();
    SetGrid(grid, grid + 3, grid + 6);
    // No reserve from an untrusted size: a truncated file fails before allocating
    // its declared full grid. Ordering: x fastest, then y, then z.
    for (std::size_t i = 0; i < fSize[0] * fSize[1] * fSize[2]; ++i) {
      G4ThreeVector b;
      for (int axis = 0; axis < 3; ++axis) b[axis] = read() * tesla;
      fValues.push_back(b);
    }
    std::string extra;
    if (data >> extra) throw std::runtime_error("Unexpected extra field map data");
  }
  for (std::size_t z = 0; z < fSize[2]; ++z)
    for (std::size_t y = 0; y < fSize[1]; ++y)
      for (std::size_t x = 0; x < fSize[0]; ++x) {
        const auto& b = fValues[(z * fSize[1] + y) * fSize[0] + x];
        if (!std::isfinite(b.mag2())) throw std::runtime_error("Invalid field magnitude");
        if (x == 0 || y == 0 || z == 0 || x == fSize[0]-1 ||
            y == fSize[1]-1 || z == fSize[2]-1)
          fBoundaryMaximum = std::max(fBoundaryMaximum, b.mag());
      }
}

void MagneticFieldMap::SetGrid(const double size[3], const double minimum[3], const double spacing[3]) {
  std::size_t count = 1;
  for (int axis = 0; axis < 3; ++axis) {
    if (!(size[axis] >= 2 && size[axis] <= 100000) || std::floor(size[axis]) != size[axis])
      throw std::runtime_error("Each field grid dimension must be an integer >= 2");
    fSize[axis] = static_cast<std::size_t>(size[axis]);
    if (count > std::numeric_limits<std::size_t>::max() / fSize[axis])
      throw std::runtime_error("Field grid size overflow");
    count *= fSize[axis];
    fMinimum[axis] = minimum[axis] * m;
    fSpacing[axis] = spacing[axis] * m;
    if (!(fSpacing[axis] > 0))
      throw std::runtime_error("Field grid spacing must be positive");
    fMaximum[axis] = fMinimum[axis] + (fSize[axis] - 1) * fSpacing[axis];
    if (!std::isfinite(fMinimum[axis]) || !std::isfinite(fMaximum[axis]) ||
        fMaximum[axis] <= fMinimum[axis])
      throw std::runtime_error("Invalid field grid extent");
  }
}

void MagneticFieldMap::ReadBinary(std::istream& input, const std::string& filename) {
  const std::uint16_t probe = 1;
  if (*reinterpret_cast<const unsigned char*>(&probe) != 1)
    throw std::runtime_error("Binary field maps are little-endian; this host is not");
  std::uint64_t size[3];
  double grid[6];
  if (!input.read(reinterpret_cast<char*>(size), sizeof size) ||
      !input.read(reinterpret_cast<char*>(grid), sizeof grid))
    throw std::runtime_error("Invalid or incomplete field map: " + filename);
  const double sizes[3] = {double(size[0]), double(size[1]), double(size[2])};
  SetGrid(sizes, grid, grid + 3);
  // Size check before allocating: a truncated or padded file is rejected.
  const auto start = input.tellg();
  input.seekg(0, std::ios::end);
  const auto count = fSize[0] * fSize[1] * fSize[2];
  if (input.tellg() - start != static_cast<std::streamoff>(3 * count * sizeof(float)))
    throw std::runtime_error("Field map size does not match its grid: " + filename);
  input.seekg(start);
  std::vector<float> raw(3 * count);
  if (!input.read(reinterpret_cast<char*>(raw.data()), raw.size() * sizeof(float)))
    throw std::runtime_error("Invalid or incomplete field map: " + filename);
  fValues.reserve(count);
  for (std::size_t i = 0; i < count; ++i)
    fValues.emplace_back(raw[3*i] * tesla, raw[3*i+1] * tesla, raw[3*i+2] * tesla);
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
