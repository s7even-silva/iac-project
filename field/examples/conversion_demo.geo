// Conversion fixture only: NOT a DH/REBCO magnet or a production coil.
// All dimensions in metres; located outside the existing habitat.
SetFactory("OpenCASCADE");
Torus(1) = {4, 0, 0, 0.4, 0.07};
Box(2) = {3.4, -0.6, -0.3, 0.2, 1.2, 0.1};
Physical Volume("demo_winding") = {1};
Physical Volume("demo_support") = {2};
Mesh.MeshSizeMin = 0.04;
Mesh.MeshSizeMax = 0.08;
Mesh.MeshSizeFromCurvature = 12;
