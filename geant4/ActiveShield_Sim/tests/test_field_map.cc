#include "TabulatedMagneticField.hh"
#include "G4SystemOfUnits.hh"
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace {
void Require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
void Near(const G4ThreeVector& actual, const G4ThreeVector& expected) {
  Require((actual-expected).mag() < 1.e-10*tesla, "Wrong interpolated field");
}
}

int main() {
  const std::string path = "test-field.map";
  try {
    {
      std::ofstream out(path);
      // Non-cubic grid and unequal spacing detect transposed axes/strides.
      out << "# nx ny nz; minimum [m]; spacing [m]\n3 2 4\n-2 -3 -4\n2 6 3\n";
      for (int z = 0; z < 4; ++z)
        for (int y = 0; y < 2; ++y)
          for (int x = 0; x < 3; ++x) {
            const double px=-2+2*x, py=-3+6*y, pz=-4+3*z;
            // Affine, divergence-free field; trilinear interpolation is exact.
            out << 1+py << ' ' << 2+pz << ' ' << 3+px << '\n';
          }
    }
    auto map = std::make_shared<MagneticFieldMap>(path);
    Near(map->Evaluate({0.3*m, -0.7*m, 1.1*m}), {0.3*tesla, 3.1*tesla, 3.3*tesla});
    Near(map->Evaluate(map->Minimum()), {-2*tesla, -2*tesla, 1*tesla});
    Near(map->Evaluate(map->Maximum()), {4*tesla, 7*tesla, 5*tesla});
    Near(map->Evaluate({2.001*m, 0., 0.}), {});
    Near(map->Evaluate({0., -3.001*m, 0.}), {});
    Near(map->Evaluate({0., 0., 5.001*m}), {});
    Near(map->Evaluate({0., 0., -4.001*m}), {});
    Near(map->Evaluate({-2.001*m, 0., 0.}), {});
    Near(map->Evaluate({0., 3.001*m, 0.}), {});
    Require(std::abs(map->BoundaryMaximum()/tesla-std::sqrt(90.)) < 1.e-10,
            "Wrong boundary diagnostic");
    TabulatedMagneticField field(map, 0.5);
    const G4double point[4] = {0.3*m, -0.7*m, 1.1*m, 0.};
    G4double b[3];
    field.GetFieldValue(point, b);
    Near({b[0],b[1],b[2]}, {0.15*tesla,1.55*tesla,1.65*tesla});
    TabulatedMagneticField off(map, 0.);
    off.GetFieldValue(point, b);
    Near({b[0],b[1],b[2]}, {});

    for (const auto& invalid : {
        "1 2 2\n", "2.5 2 2\n", "2 2 2\n0 0 0\n1 0 1\n",
        "2 2 2\n0 0 0\n1 1 1\n0 0 0\n", "2 2 2\n0 0 nan\n",
        "2 2 2\n0 0 0\n1 1 1\n0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 extra"}) {
      { std::ofstream out(path); out << invalid; }
      bool rejected = false;
      try { MagneticFieldMap bad(path); } catch (const std::runtime_error&) { rejected=true; }
      Require(rejected, "Malformed map accepted");
    }
    std::filesystem::remove(path);
    bool rejected = false;
    try { MagneticFieldMap missing(path); } catch (const std::runtime_error&) { rejected=true; }
    Require(rejected, "Missing map accepted");
    std::cout << "Field interpolation, units, boundaries, scale and invalid maps: PASS\n";
    return 0;
  } catch (const std::exception& error) {
    std::filesystem::remove(path);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
