cmake_minimum_required(VERSION 3.16)
project(GCR_SEP_Sim)

# Same WITH_GEANT4_UIVIS pattern already in ActiveShield_Sim/CMakeLists.txt
# (inherited from the official Geant4 example) -- OFF avoids requesting
# ui_all/vis_all, which a "noqt" geant4 build (no Qt6, see
# environment.headless.yml) doesn't need for a batch-only compute node.
option(WITH_GEANT4_UIVIS "Build with Geant4 UI and Vis drivers" ON)
if(WITH_GEANT4_UIVIS)
  find_package(Geant4 REQUIRED ui_all vis_all)
else()
  find_package(Geant4 REQUIRED)
endif()
include(${Geant4_USE_FILE})

include_directories(${PROJECT_SOURCE_DIR}/include)

file(GLOB sources ${PROJECT_SOURCE_DIR}/src/*.cc)
file(GLOB headers ${PROJECT_SOURCE_DIR}/include/*.hh)

add_executable(gcrsim main.cc ${sources} ${headers})
target_link_libraries(gcrsim ${Geant4_LIBRARIES})

file(COPY ${PROJECT_SOURCE_DIR}/macros DESTINATION ${PROJECT_BINARY_DIR})
file(COPY ${PROJECT_SOURCE_DIR}/data DESTINATION ${PROJECT_BINARY_DIR})
