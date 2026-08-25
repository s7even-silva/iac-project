# IAC 2026

## Entorno de simulación

    conda env create -f environment.yml
    conda activate geant4_env

Compilación (fuera de fuente, con el toolchain de conda):

    rm -rf build && mkdir build && cd build
    cmake -DCMAKE_CXX_COMPILER=$CXX ..
    make -j$(nproc)

### Versiones

| Componente | Versión |
|---|---|
| GEANT4 | 11.4.2 (conda-forge) |
| CMake | 4.4.1 |
| Compilador | gcc/gxx_linux-64 15.2.0 |

### Datasets de GEANT4

| Dataset | Versión | Relevancia |
|---|---|---|
| G4EMLOW | 8.8 | Procesos EM de baja energía, poder de frenado |
| G4NDL | 4.7.1 | Transporte de neutrones (HP) — crítico con polietileno |
| G4PARTICLEXS | 4.2 | Secciones eficaces hadrónicas |
| G4ABLA | 3.3 | Desexcitación nuclear — fragmentos secundarios |
| G4INCL | 1.3 | Cascada intranuclear |
| PhotonEvaporation | 6.1.2 | |
| RadioactiveDecay | 6.1.2 | |
| G4ENSDFSTATE | 3.0 | |
| G4SAIDDATA | 2.0 | |
| G4PII | 1.3 | |
| RealSurface | 2.2 | |
| G4CHANNELING | 2.0 | |

### Parámetros de simulación

- Physics list: (por definir — `Shielding` / `QGSP_BIC_HP`)
- Stepper de campo: (por definir)
- Cortes de producción: (por definir)
- Semillas: registradas por corrida en `output/`

