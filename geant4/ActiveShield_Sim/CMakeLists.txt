#----------------------------------------------------------------------------
# Setup the project
cmake_minimum_required(VERSION 3.16...3.27)

project(ICRPphantoms)

#----------------------------------------------------------------------------
# Find Geant4 package, activating all available UI and Vis drivers by default
# You can set WITH_GEANT4_UIVIS to OFF via the command line or ccmake/cmake-gui
# to build a batch mode only executable
#
option(WITH_GEANT4_UIVIS "Build example with Geant4 UI and Vis drivers" ON)
if(WITH_GEANT4_UIVIS)
  find_package(Geant4 REQUIRED gdml ui_all vis_all)
else()
  find_package(Geant4 REQUIRED gdml)
endif()

#----------------------------------------------------------------------------
# Setup Geant4 include directories and compile definitions
#
include(${Geant4_USE_FILE})

#----------------------------------------------------------------------------
# Locate sources and headers for this project
#
include_directories(${PROJECT_SOURCE_DIR}/include 
                    ${Geant4_INCLUDE_DIR}
                    ${GDML_INCLUDE_DIR})
file(GLOB sources ${PROJECT_SOURCE_DIR}/src/*.cc)
file(GLOB headers ${PROJECT_SOURCE_DIR}/include/*.hh)

#----------------------------------------------------------------------------
# Add the executable, and link it to the Geant4 libraries
#
add_executable(ICRP110phantoms ICRP110phantoms.cc ${sources} ${headers})
add_executable(ICRP110standalone ICRP110standalone.cc ${sources} ${headers})

target_link_libraries(ICRP110phantoms ${Geant4_LIBRARIES} )
target_link_libraries(ICRP110standalone ${Geant4_LIBRARIES} )

include(CTest)
if(BUILD_TESTING)
  add_executable(test_field_map tests/test_field_map.cc src/TabulatedMagneticField.cc)
  target_link_libraries(test_field_map ${Geant4_LIBRARIES})
  add_test(NAME field_map COMMAND test_field_map)
  add_test(NAME passive_layers COMMAND ICRP110phantoms ${PROJECT_SOURCE_DIR}/tests/passive_layers.mac)
  set_tests_properties(passive_layers PROPERTIES
    WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
    PASS_REGULAR_EXPRESSION "Passive layer 1: G4_POLYETHYLENE; thickness \\[cm\\]=2"
    FAIL_REGULAR_EXPRESSION "Overlap is detected;G4Exception;COMMAND NOT FOUND")
endif()

# Depend on data for runtime
add_dependencies(ICRP110phantoms ICRPdata)
add_dependencies(ICRP110standalone ICRPdata)

#----------------------------------------------------------------------------
# Copy all scripts to the build directory, i.e. the directory in which we
# build human_phantom. This is so that we can run the executable directly because it
# relies on these scripts being in the current working directory.
#
set(ICRPphantoms_SCRIPTS
     female.in female_head.in female_trunk.in male.in male_head.in male_trunk.in vis.mac primary.mac ColourMap.dat openGLVis.mac g4views/g4_00.g4view g4views/g4_01.g4view standalone.mac
#    ICRPdata/Data.dat 
#    "ICRPdata/ICRP110_g4dat/AF/*.g4dat"
#    "ICRPdata/ICRP110_g4dat/AM/*.g4dat"
  )
 
foreach(_script ${ICRPphantoms_SCRIPTS})
  configure_file(
    ${PROJECT_SOURCE_DIR}/${_script}
    ${PROJECT_BINARY_DIR}/${_script}
    COPYONLY
    )
endforeach()

# OLTARIS GCR/SEP spectra for ICRP110PhantomPrimaryGeneratorAction
# (SpectrumSampler reads "data/<file>.csv" relative to the working
# directory, same convention as GCR_SEP_Sim). The versioned source of
# truth is data/sources/oltaris/*.csv (matches the .gitignore exception
# "geant4/**/data/sources/**/*.csv" -- a bare data/*.csv is NOT versioned,
# same reasoning as GCR_SEP_Sim's data/ vs data/sources/ split, see
# AGENTS.md); this copies those files flat into build/data/ (no "sources/
# oltaris" subdirectory) so the runtime relative path resolves.
file(GLOB ICRPphantoms_OLTARIS_CSV ${PROJECT_SOURCE_DIR}/data/sources/oltaris/*.csv)
file(COPY ${ICRPphantoms_OLTARIS_CSV} DESTINATION ${PROJECT_BINARY_DIR}/data)

#set(ICRPphantoms_DATADIR
#   ICRPdata
#)
        
#file(COPY ${PROJECT_SOURCE_DIR}/${ICRPphantoms_DATADIR} DESTINATION
#     ${PROJECT_BINARY_DIR})

include(ExternalProject)
ExternalProject_Add(ICRPdata
  SOURCE_DIR ${PROJECT_BINARY_DIR}/ICRPdata
  URL https://cern.ch/geant4-data/datasets/examples/advanced/ICRP110Phantoms/ICRPdata.tar.gz
  URL_MD5 2aba5409d4e7b7a2f0328e7d3402f187
  CONFIGURE_COMMAND ""
  BUILD_COMMAND ""
  INSTALL_COMMAND ""
  )

#----------------------------------------------------------------------------
# Add program to the project targets
# (this avoids the need of typing the program name after make)
#
add_custom_target(ICRPphantoms DEPENDS phantom)
add_custom_target(ICRPstandalone DEPENDS phantom)

#----------------------------------------------------------------------------
# Install the executable to 'bin' directory under CMAKE_INSTALL_PREFIX
#
install(TARGETS ICRP110phantoms DESTINATION bin)
install(TARGETS ICRP110standalone DESTINATION bin)
