//
// ********************************************************************
// * License and Disclaimer                                           *
// *                                                                  *
// * The  Geant4 software  is  copyright of the Copyright Holders  of *
// * the Geant4 Collaboration.  It is provided  under  the terms  and *
// * conditions of the Geant4 Software License,  included in the file *
// * LICENSE and available at  http://cern.ch/geant4/license .  These *
// * include a list of copyright holders.                             *
// *                                                                  *
// * Neither the authors of this software system, nor their employing *
// * institutes,nor the agencies providing financial support for this *
// * work  make  any representation or  warranty, express or implied, *
// * regarding  this  software system or assume any liability for its *
// * use.  Please see the license in the file  LICENSE  and URL above *
// * for the full disclaimer and the limitation of liability.         *
// *                                                                  *
// * This  code  implementation is the result of  the  scientific and *
// * technical work of the GEANT4 collaboration.                      *
// * By using,  copying,  modifying or  distributing the software (or *
// * any work based  on the software)  you  agree  to acknowledge its *
// * use  in  resulting  scientific  publications,  and indicate your *
// * acceptance of all terms of the Geant4 Software license.          *
// ********************************************************************
//
//
// Code developed by:
// S.Guatelli, M. Large and A. Malaroda, University of Wollongong
//
//Original code from geant4/examples/extended/runAndEvent/RE03
//
#include <vector>
#include <map>
#include <cmath>
#include "ICRP110UserScoreWriter.hh"
#include "ICRP110ScoreWriterMessenger.hh"
#include "G4SystemOfUnits.hh"
#include "G4SDParticleFilter.hh"
#include "G4VPrimitiveScorer.hh"
#include "G4VScoringMesh.hh"

ICRP110UserScoreWriter::ICRP110UserScoreWriter():
G4VScoreWriter() 
{
 fMessenger = new ICRP110ScoreWriterMessenger(this);
 fSex = "female"; //Default phantom sex is female
 fSection = "head"; // Default phantom section is head
}

ICRP110UserScoreWriter::~ICRP110UserScoreWriter() 
{
  delete fMessenger;
}

void ICRP110UserScoreWriter::DumpQuantityToFile(const G4String & psName, const G4String & fileName, const G4String & option) 
{
    using MeshScoreMap = G4VScoringMesh::MeshScoreMap;

    if(verboseLevel > 0) 
      {
      G4cout << "ICRP110UserScorer-defined DumpQuantityToFile() method is invoked." << G4endl; 
      }

    // change the option string into lowercase to the case-insensitive.
    G4String opt = option;
    std::transform(opt.begin(), opt.end(), opt.begin(), (int (*)(int))(tolower));
    
    // confirm the option
    if(opt.size() == 0) opt = "csv";

//--------------------------------------------------------------------//
//----------------Create Scoring Mesh Output Text File----------------//
//--------------------------------------------------------------------//
// First we create use the scoring mesh to create a default output text
// file containing 4 columns: voxel number along x, y, z, and edep deposited
// in that voxel (in J). This file is to be called "PhantomMesh_Edep.txt". 

std::ofstream ofile(fileName);
  
if(!ofile) 
{
   G4cerr << "ERROR : DumpToFile : File open error -> " << fileName << G4endl;
   return;
}
  ofile << "# mesh name: " << fScoringMesh -> GetWorldName() << G4endl;

// retrieve the map
MeshScoreMap fSMap = fScoringMesh -> GetScoreMap();
  
auto msMapItr = fSMap.find(psName);
  
if(msMapItr == fSMap.end()) 
  {
   G4cerr << "ERROR : DumpToFile : Unknown quantity, \""<< psName 
   << "\"." << G4endl;
   return;
  }

std::map<G4int, G4StatDouble*> * score = msMapItr -> second-> GetMap();

ofile << "# primitive scorer name: " << msMapItr -> first << G4endl;

  // declare dose array and initialize to zero.
  std::vector<double> ScoringMeshEdep;
  for(G4int y = 0; y < fNMeshSegments[0]*fNMeshSegments[1]*fNMeshSegments[2]; y++) ScoringMeshEdep.push_back(0.);

// Fase 7 del plan estadistico (docs/bitacora/plan_estadistico.md, Piloto A
// -- validacion del estimador de incertidumbre intra-run): ademas de
// sum_wx() (edep total, ya usado abajo), G4StatDouble por voxel ya trae
// sum_wx2() y n() sin costo de computo adicional -- Geant4 los acumula
// por evento via fill() dentro del propio nucleo (G4StatDouble::fill()),
// el proyecto simplemente no los leia. Se guardan aqui, por voxel, para
// agregarlos por organo mas abajo (S1_organo = suma de S1 de sus voxels,
// igual que ya se hace con Edep; ver limitacion de covarianza entre
// voxels documentada en el bloque de agregacion, mas abajo).
// UNIDADES: sum_wx() esta en MeV internamente, se divide por "joule" (J)
// para convertir -- sum_wx2() = sum(valor^2) esta en MeV^2 internamente,
// hay que dividir por (joule*joule), NO por joule, para J^2. Error de
// escala facil de cometer, dejado explicito.
  std::vector<double> ScoringMeshEdep2; // sum_wx2 por voxel, en J^2
  std::vector<int> ScoringMeshN;        // n (eventos que depositaron algo) por voxel
  for(G4int y = 0; y < fNMeshSegments[0]*fNMeshSegments[1]*fNMeshSegments[2]; y++) {
    ScoringMeshEdep2.push_back(0.);
    ScoringMeshN.push_back(0);
  }

ofile << std::setprecision(16); // for double value with 8 bytes

for(G4int x = 0; x < fNMeshSegments[0]; x++) {
   for(G4int y = 0; y < fNMeshSegments[1]; y++) {
     for(G4int z = 0; z < fNMeshSegments[2]; z++){
        // Retrieve dose in each scoring mesh bin/voxel
        G4int idx = GetIndex(x, y, z);
        std::map<G4int, G4StatDouble*>::iterator value = score -> find(idx);
        if (value != score -> end()) {
          ScoringMeshEdep[idx] += (value->second->sum_wx())/(joule);
          ScoringMeshEdep2[idx] += (value->second->sum_wx2())/(joule*joule);
          ScoringMeshN[idx] += value->second->n();
        }
       }
      }
     }

ofile << std::setprecision(6);

ofile << std::setprecision(16); // for double value with 8 bytes

for(G4int x = 0; x < fNMeshSegments[0]; x++) {
   for(G4int y = 0; y < fNMeshSegments[1]; y++) {
     for(G4int z = 0; z < fNMeshSegments[2]; z++){

         G4int idx = GetIndex(x, y, z);

         if (ScoringMeshEdep[idx] != 0){
         // Columnas 5 y 6 (sum_wx2 en J^2, n) agregadas al final de la
         // linea -- ver el bloque de relectura mas abajo, que ahora
         // consume 6 columnas por linea en vez de 4 (mismo cambio, para
         // no desalinear la lectura -- ver tambien el fix del bug de
         // relectura, bloque siguiente).
         ofile << x << '\t' << y << '\t' << z << '\t' << ScoringMeshEdep[idx]
               << '\t' << ScoringMeshEdep2[idx] << '\t' << ScoringMeshN[idx] << G4endl;
         }
         //Store x,y,z and dose for each voxel in output text file.

       }
      }
     }

// Close the output ASCII file
ofile.close();

//----------------------------------------------------------------------------------------//
//-----Read Data.dat File to determine the name and number of slice files to open---------//
//----------------------------------------------------------------------------------------//
// Using the macro commands from the .in files, the UserScoreWriter identifies which
// phantom sex and section has been constructed. We then store the names of the individual z-slices 
// which have been called upon in the detector construction when creating the phantom.

G4int NSlices = 0;
G4int NXVoxels = 0;
G4int NYVoxels = 0;
std::ifstream DataFile;

  G4cout << "Phantom Sex: " << fSex << G4endl;
  G4cout << "Phantom Section: " << fSection << G4endl;

G4String male = "male";
G4String female = "female";
//G4String 

  //Determine Phantom Sex and Section which was Simulated
  if (fSex == "male")
  {
    if (fSection == "head")
    {
      DataFile.open("ICRPdata/MaleHead.dat");
      G4cout << "Selecting data file ICRPdata/MaleHead.dat..." << G4endl;
    }
    if (fSection == "trunk")
    {
      DataFile.open("ICRPdata/MaleTrunk.dat");
      G4cout << "Selecting data file ICRPdata/MaleTrunk.dat..." << G4endl;
    }
    if (fSection == "full")
    {
      DataFile.open("ICRPdata/MaleData.dat");
      G4cout << "Selecting data file ICRPdata/MaleData.dat..." << G4endl;
    }
  }
  else if(fSex == "female")
  {
    if (fSection == "head")
    {
      DataFile.open("ICRPdata/FemaleHead.dat");
      G4cout << "Selecting data file ICRPdata/FemaleHead.dat..." << G4endl;
    }
    if (fSection == "trunk")
    {
      DataFile.open("ICRPdata/FemaleTrunk.dat");
      G4cout << "Selecting data file ICRPdata/FemaleTrunk.dat..." << G4endl;
    }
    if (fSection == "full")
    {
      DataFile.open("ICRPdata/FemaleData.dat");
      G4cout << "Selecting data file ICRPdata/FemaleData.dat..." << G4endl;
    }
  }
  else
  {
    G4cout << "Phantom Sex or section not correctly specified to ICRP110UserScoreWriter" << G4endl;
  }

		//Check if file opens
		if(DataFile.good() != 1 )
		{
			G4cout << "Problem Reading Data File" << G4endl;
		}
		else 
		{
			G4cout << "Opening Data.dat File..." << G4endl; 
		}
   
DataFile >> NSlices;
G4cout << "Number of Phantom Slices Simulated = " << NSlices << G4endl;

DataFile >> NXVoxels >> NYVoxels;
G4cout << "Number of X Voxels per slice = " << NXVoxels << G4endl;
G4cout << "Number of Y Voxels per slice = " << NYVoxels << G4endl;


G4int VoxelsPerSlice = 0;
VoxelsPerSlice = NXVoxels * NYVoxels;

//Skip lines 4-60 of Data.dat as they hold no useful information for this code
	for (G4int i = 0; i < 58; i++){
		DataFile.ignore(256, '\n'); 
	}

// Read file names to open from Data.dat (i.e. those that were used in simulation)
 
std::vector<G4String> SliceName; //char SliceName[NSlices][20]; //Stores name and number of phantom slices used in simulation

  for(G4int i = 0; i < NSlices; i++){
		SliceName.push_back("empty");
	}

	for (G4int i = 0; i < NSlices; i++){
		DataFile >> SliceName[i];
	}


//--------------------------------------------------------------------//
//----------------------Read Phantom Slice Files----------------------//
//--------------------------------------------------------------------//
// Reads each of the phantom z-slice files identified by the above code
// and stores the organIDs within each voxel sequentially. 
// Later, we will compare the dose in each voxel to the organ ID of each 
// voxel to calculate total dose in each organ. 

G4int ARRAY_SIZE = VoxelsPerSlice * NSlices;

std::vector<G4int> OrganIDs; 

std::ifstream PhantomFile;
 
for (G4int ii = 0; ii < NSlices; ii++){

G4String sliceVar = SliceName[ii];
G4String slice;

  if (fSex == "male")
  {
    slice = "ICRPdata/ICRP110_g4dat/AM/"+sliceVar;
  }
  else if(fSex == "female")
  {
    slice = "ICRPdata/ICRP110_g4dat/AF/"+sliceVar;
  }

  PhantomFile.open(slice.c_str());

		//Check if file opens
		if(PhantomFile.good() != 1 )
		{
			G4cout << "Problem Reading Phantom Slice File:" << SliceName[ii] << G4endl;
		}
		else 
		{
			G4cout << "Opening Phantom Slice File: " << SliceName[ii] << G4endl; 
		}

	G4int FNVoxelX;
	G4int FNVoxelY;
	G4int FNVoxelZ;

		//Input first 3 numbers of file - They are not organ IDs	
		PhantomFile >> FNVoxelX >> FNVoxelY >> FNVoxelZ;
  
  G4int aa = 0;
  
 for (G4int i = 0; i < VoxelsPerSlice; i++)
	{
		PhantomFile >> aa;
    OrganIDs.push_back(aa);
	}

  PhantomFile.close();
}

//---------------------------------------------------------------//
//--------------Read Data from Scoring Mesh Text File------------//
//---------------------------------------------------------------//
// Opens and reads initial/default scoring mesh output file which
// was created at the beginning of the code. We now store the edep in each
// voxel to cross reference against the organ ID of each voxel for 
// calculations of total dose in each organ.

std::ifstream MeshFile(fileName);

	//Check if file opens
	if(MeshFile.good() != 1 )
	{
		G4cout << "Problem Reading Data File: " << fileName << G4endl;
	}
	else {
		G4cout << "Opening File: " << fileName << G4endl; 
	}


//-----Reads Phantom Mesh Text File and Stores Data in 6 different Vectors-------//

// Fix de un bug real preexistente (encontrado 2026-09-18/19, ver
// docs/bitacora/plan_estadistico.md): el codigo anterior iteraba un
// numero FIJO de veces (lines = VoxelsPerSlice*NSlices, el total de
// voxels POSIBLES del fantoma completo), pero PhantomMesh_Edep.txt solo
// tiene una linea por voxel con edep != 0 (la inmensa mayoria de los
// voxels de un fantoma nunca reciben energia en una corrida cualquiera
// -- verificado con datos reales: 200.655 lineas reales contra
// 7.161.276 posibles, ~97% del bucle de sobra). Cuando el stream de C++
// (operator>>) se agota, las variables NO se resetean a 0 -- conservan
// su ultimo valor leido silenciosamente (verificado empiricamente con
// un programa C++ aislado que reproduce el patron exacto). Esto hacia
// que el bucle de agregacion de mas abajo (OrganDep[OrganIndex] +=
// Edep[i]) sumara el edep del ULTIMO voxel real, repetidamente, para
// TODO el resto del bucle -- en la practica el impacto parecia acotado
// al organo "Air" (organo_id=0, porque el ultimo voxel escrito, dado el
// orden de los bucles x->y->z al generar el archivo, suele caer en el
// borde extremo del volumen mallado), pero no hay garantia de que esto
// se cumpla siempre para toda combinacion/geometria -- no verificado en
// general, solo en la corrida de prueba usada para encontrar el bug.
//
// Corregido: se lee mientras el stream siga bien (while(MeshFile >> ...)),
// sin asumir de antemano cuantas lineas tiene el archivo -- patron
// idiomatico de C++ para esto, en vez de un limite fijo que dependia de
// que el archivo tuviera EXACTAMENTE esa cantidad de lineas (nunca fue
// el caso).
//
// Se agregan ademas 2 columnas nuevas (S1/S2/N intra-run, ver arriba):
// sum_wx2 (J^2) y n, en las columnas 5 y 6 de cada linea.

//Ignore first 2 lines of PhantomMesh.txt as they are text headers
MeshFile.ignore(256, '\n');
MeshFile.ignore(256, '\n');

std::vector<G4int> X_MeshID; //Stores X-position of all scoring mesh voxels
std::vector<G4int> Y_MeshID; //Stores Y-position
std::vector<G4int> Z_MeshID; //Stores Z-position
std::vector<G4double> Edep; //Stores edep in voxels
std::vector<G4double> Edep2; //Stores sum_wx2 (J^2) in voxels -- Fase 7, intra-run
std::vector<G4int> NEvts;    //Stores n (event count) in voxels -- Fase 7, intra-run

G4int nX = 0; //Number along X of scoring mesh voxel
G4int nY = 0; //Number along Y
G4int nZ = 0; //Number along Z
G4double EDep = 0.0; //edep deposited in individual voxels
G4double EDep2 = 0.0; //sum_wx2 deposited in individual voxels (J^2)
G4int NEvt = 0; //n (event count) in individual voxels

while (MeshFile >> nX >> nY >> nZ >> EDep >> EDep2 >> NEvt) {
	X_MeshID.push_back(nX);
	Y_MeshID.push_back(nY);
	Z_MeshID.push_back(nZ);
	Edep.push_back(EDep);
	Edep2.push_back(EDep2);
	NEvts.push_back(NEvt);
}

G4int ARRAY_SIZE_MeshLines = static_cast<G4int>(X_MeshID.size()); // lineas REALES leidas, ver mas abajo

MeshFile.close();

//--------------------------------------------------------------------//
//---------Reads AM/AF_organs.dat file and stores info about----------//
//------------------------the phantom organs--------------------------//
//--------------------------------------------------------------------//

std::ifstream PhantomOrganNames;

  if (strcmp(fSex.c_str(), male.c_str()) == 0)
  {
      PhantomOrganNames.open ("ICRPdata/ICRP110_g4dat/P110_data_V1.2/AM/AM_organs.dat");
    	//Check if file opens
      	if(PhantomOrganNames.good() != 1 )
      	{
      		G4cout << "Problem reading AM_organs.dat" << G4endl;
      	}
      	else
        {
      		G4cout << "Reading AM_organs.dat" << G4endl; 
      	}
  }
  else if(strcmp(fSex.c_str(), female.c_str()) == 0)
  {
      PhantomOrganNames.open ("ICRPdata/ICRP110_g4dat/P110_data_V1.2/AF/AF_organs.dat");
    	//Check if file opens
      	if(PhantomOrganNames.good() != 1 )
      	{
      		G4cout << "Problem reading AF_organs.dat" << G4endl;
      	}
      	else
        {
      		G4cout << "Reading AF_organs.dat" << G4endl; 
      	}
  }

	
PhantomOrganNames.ignore(256, '\n');
PhantomOrganNames.ignore(256, '\n');
PhantomOrganNames.ignore(256, '\n');
PhantomOrganNames.ignore(256, '\n');

G4String str;
std::vector<G4String> OrganNames;

  OrganNames.push_back("0     Air"); // Register air surrounding phantom
    //Fill with organ IDs of the phantom from ICRP data files (located in /ICRPdata/ICRP110_g4dat/P110_data_V1.2/)
    while(getline(PhantomOrganNames, str))
    {
      OrganNames.push_back(str);
    }
  OrganNames.push_back("141    Phantom Top/Bottom Skin Layer"); //Registers top and bottom slices of phantom made entirely of
  // skin. The skin in these layers has organ ID 141 to differentiate it from other skin, and is given its
  // own organ ID so that the user can choose whether to include it or not. 
  
//-------------------------------------------------------------------//
//---------Reads OrganMasses.dat file and stores info about----------//
//--------------------the phantom organ massess----------------------//
//-------------------------------------------------------------------//

G4int NOrganIDs = static_cast<G4int>(OrganNames.size());

std::ifstream OrganMasses;

      OrganMasses.open ("ICRPdata/OrganMasses.dat");
    	//Check if file opens
      	if(OrganMasses.good() != 1 )
      	{
      		G4cout << "Problem reading OrganMasses.dat" << G4endl;
      	}
      	else
        {
      		G4cout << "Reading OrganMasses.dat" << G4endl; 
      	}


OrganMasses.ignore(256, '\n'); //Igonore first line as it is a header

std::vector<G4int> iteratorID;
std::vector<G4double> MaleOrganMasses;
std::vector<G4double> FemaleOrganMasses;

G4int itID = 0;
G4double massM = 0.0;
G4double massF = 0.0;  
  
  for (G4int i = 0; i < NOrganIDs; i++)
    {
        OrganMasses >> itID;
        iteratorID.push_back(itID);
        
        OrganMasses >> massM;
        MaleOrganMasses.push_back(massM);
        
        OrganMasses >> massF;
        FemaleOrganMasses.push_back(massF);
    }

//---------------------------------------------------------------------------//
//----------------------Writes Outputs of code to File-----------------------//
//-------------------------------OrganDeps.out------------------------------//
//---------------------------------------------------------------------------//
// As the final step, we compare the edep in each voxel with the voxels organID 
// and sum the edep in voxels with identical organIDs to obtain total edep in 
// each organ. We then divide total edep in each organ by their respective organ
// mass to give total dose received in each organ (in Gy). 
// All this information is then output to the file "ICRP110.out".

std::ofstream OutputFile2;

G4int VoxelNumber = 0; 
G4int OrganIndex = 0;
G4cout << "NOrganIDs: " << NOrganIDs << G4endl;
std::vector <G4double> OrganDep;
std::vector <G4double> OrganDose;

G4double a = 0.0;
G4double b = 0.0;

for (G4int i = 0; i < NOrganIDs; i++)
{
  OrganDep.push_back(a);
  OrganDose.push_back(b);
}

// Fase 7 (Piloto A, intra-run): S1_organo/S2_organo/N_organo, agregados
// por organo igual que OrganDep -- misma logica de suma que Edep, ver
// docstring del bloque de arriba para la limitacion importante:
//
//   S2_organo = suma_voxel(sum_wx2_voxel) NO es la varianza correcta de
//   "edep del organo por evento" si hay correlacion entre voxels del
//   mismo evento (un primario que cruza el organo deposita en varios
//   voxels simultaneamente -> covarianza != 0 entre ellos). Esto es el
//   "Camino B" documentado en la discusion de diseno de esta fase: mas
//   simple de implementar que instrumentar EndOfEventAction (que daria
//   la varianza exacta por evento-organo), a cambio de una posible
//   SUBESTIMACION de SE_within si esa covarianza es positiva (el caso
//   tipico). La Fase 7 existe precisamente para medir empiricamente
//   cuanto importa esto, comparando SE_within (de este calculo) contra
//   s_between (de repeticiones independientes historicas) -- si
//   coinciden razonablemente, Camino B queda validado; si no, hace
//   falta el camino mas costoso.
G4double c = 0.0;
std::vector<G4double> OrganDep2; // S2 por organo, J^2 -- Camino B
std::vector<G4int> OrganN;       // N por organo (suma de eventos-voxel, NO eventos-organo unicos)
for (G4int i = 0; i < NOrganIDs; i++)
{
  OrganDep2.push_back(c);
  OrganN.push_back(0);
}

for (G4int i = 0; i < ARRAY_SIZE_MeshLines; i++){
	VoxelNumber = X_MeshID[i] + NXVoxels * Y_MeshID[i] + VoxelsPerSlice * Z_MeshID[i];
  OrganIndex = OrganIDs[VoxelNumber];
  OrganDep[OrganIndex] += Edep[i];
  OrganDep2[OrganIndex] += Edep2[i];
  OrganN[OrganIndex] += NEvts[i];
}

//Calculate dose in each organ by dividing edep in each organ by organ masses (in kg)
  if (strcmp(fSex.c_str(), male.c_str()) == 0)
  {
    for (G4int i = 0; i < NOrganIDs; i++)
      {
        OrganDose[i] = (MaleOrganMasses[i] == 0 ) ? 0 : OrganDep[i]/(MaleOrganMasses[i] * 1e-3); 
      }
  }
  else if(strcmp(fSex.c_str(), female.c_str()) == 0)
  {
    for (G4int i = 0; i < NOrganIDs; i++)
      {
        OrganDose[i] = (FemaleOrganMasses[i] == 0 ) ? 0 : OrganDep[i]/(FemaleOrganMasses[i] * 1e-3); 
      }  
  }

OutputFile2.open ("ICRP110.out");

	//Check if file opens
	if(OutputFile2.good() != 1 )
	{
		G4cout << "Problem writing output to ICRP110.out" << G4endl;
	}
	else {
		G4cout << "Writing output to ICRP110.out" << G4endl; 
	}


G4double TotalDep = 0.0;
G4double TotalDose = 0.0;

OutputFile2 << G4endl; 
OutputFile2 << '\t' << "-------------------------------- " << G4endl;
OutputFile2 << '\t' << "OrganID" << '\t' << "Edep (J)" << '\t' << "Dose (Gy)" << G4endl;
OutputFile2 << '\t' << "-------------------------------- " << G4endl;


for (G4int i = 1; i < NOrganIDs; i++)
{
  if (OrganDep[i] != 0)
  {
    if (i != 140) //Skip dose deposited in air inside body
    {
      OutputFile2 << '\t' << i << " |" << '\t' << '\t' << OrganDep[i] << '\t' << OrganDose[i] << G4endl;
    }
  }
}

OutputFile2 << "----------------------------------------------------------------------------" << G4endl;
OutputFile2 << "-------------------------------ORGAN INFO-----------------------------------" << G4endl;
OutputFile2 << "-----------------(of organs where edep/dose was recorded)-------------------" << G4endl;
OutputFile2 << "----------------------------------------------------------------------------" << G4endl;
OutputFile2 << "ID" << '\t' << '\t' << "Organ Name" << '\t' << "    " << '\t' << "    " << '\t' << "    " << '\t' << "Material ID" << '\t'  << '\t' << "Density (g/cm^3) " << G4endl;

for(G4int i = 1; i < NOrganIDs; i++)
{
  if (OrganDep[i] != 0)
  {
    if (i != 140) //Skip dose deposited in air inside body
    {
      OutputFile2 << OrganNames[i] << G4endl;
    }
  }
}

//Sum total dose over all organs
for (G4int i = 1; i < NOrganIDs; i++)
{
    if (i != 140) //Skip dose deposited in air inside body
    {
      TotalDep += OrganDep[i];
      TotalDose += OrganDose[i];
    }
}

OutputFile2 << G4endl;
OutputFile2 << "Total Edep over all organs = " << TotalDep << " J" << G4endl;
OutputFile2 << "Total dose absorbed over all organs = " << TotalDose << " Gy" << G4endl;


OutputFile2 << G4endl;
OutputFile2 << "----------------------------------------------------------------------------" << G4endl;
OutputFile2 << "----------------ORGAN ENERGY DEPOSITIONS AND ABSORBED DOSE------------------" << G4endl;
OutputFile2 << "-----------(for all organs [includes air - OrganIDs = 0, 140])--------------" << G4endl;
OutputFile2 << "--------------([and top/bottom skin layer - OrganIDs = 141])----------------" << G4endl;
OutputFile2 << "----------------------------------------------------------------------------" << G4endl;
// Columnas 3-6 (S1_J, S2_J2, N, SE_run_J) agregadas al final de cada
// linea -- Fase 7 (Piloto A, intra-run), ver docs/bitacora/plan_estadistico.md.
// El parser Python (parse_icrp110_out en run_organ_sweep.py) solo lee
// parts[0]/parts[1] (Edep/Dose) de cada linea con "|" -- columnas extra
// al final no lo rompen (verificado antes de escribir esto), pero
// aggregate_organ_doses.py necesita actualizarse aparte para USARLAS
// (no hecho en este cambio, ver checklist de la Fase 7).
//
// S1_J = OrganDep[i] (ya escrito en la columna "Edep (J)", repetido aqui
// explicitamente para que la fila sea autocontenida como (N,S1,S2)).
// SE_run_J = sqrt(s^2/N), con s^2 = (S2 - S1^2/N)/(N-1) -- formula
// exacta del plan (Fase 5/7). N<2 no tiene varianza muestral (ver la
// misma regla ya aplicada en aggregate_organ_doses.py para R_b=1) -- se
// escribe SE_run_J=0 explicitamente en ese caso, NUNCA como "precision
// infinita": el organo simplemente no tiene suficiente informacion
// intra-run para estimar su propia varianza (misma limitacion ya
// documentada para bins_R1_sin_varianza).
OutputFile2 << "OrganID" << '\t' << "Edep (J) " << '\t' << "Dose (Gy) "
            << '\t' << "S1_J" << '\t' << "S2_J2" << '\t' << "N" << '\t' << "SE_run_J" << G4endl;
OutputFile2 << "-------------------------------" << G4endl;

for (G4int i = 0; i < NOrganIDs; i++)
{
    G4double s1 = OrganDep[i];
    G4double s2 = OrganDep2[i];
    G4int n = OrganN[i];
    G4double seRun = 0.0;
    if (n >= 2) {
      G4double variance = (s2 - (s1 * s1) / n) / (n - 1);
      // La resta S2 - S1^2/N puede dar un numero negativo diminuto por
      // cancelacion de punto flotante cuando la varianza real es casi
      // cero (todos los eventos depositaron casi lo mismo) -- se recorta
      // a 0 en vez de propagar un NaN via sqrt() de un negativo.
      if (variance < 0.0) variance = 0.0;
      seRun = std::sqrt(variance / n);
    }
    OutputFile2 << i << "  | " << '\t' << '\t' << OrganDep[i] << '\t' << OrganDose[i]
                << '\t' << s1 << '\t' << s2 << '\t' << n << '\t' << seRun << G4endl;
}

OutputFile2 << "Total energy depositied over all organs = " << TotalDep << " J" << G4endl;
OutputFile2 << "Total absorbed dose over all organs = " << TotalDose << " Gy " << G4endl;
G4cout << "Total energy deposited over all Organs within the Phantom is " << TotalDep << " J" << G4endl;
G4cout << "Total absorbed dose over all phantom organs is " << TotalDose << " Gy " << G4endl;

OutputFile2.close();
}


// Sets the sex of the phantom as defined through the messenger class
void ICRP110UserScoreWriter::SetPhantomSex(G4String newSex)
{
  fSex = newSex;
  
  if (fSex == "male")
    {
      G4cout << ">> Male Phantom identified by UserScoreWriter." << G4endl;
    }
  if (fSex == "female")
    {
      G4cout << ">> Female Phantom identified by UserScoreWriter." << G4endl;
    }
  if ((fSex != "female") && (fSex != "male"))
    G4cout << fSex << " can not be defined!" << G4endl;
}

// Sets the section of the phantom as defined through the messenger class
void ICRP110UserScoreWriter::SetPhantomSection(G4String newSection)
{
  fSection = newSection;
  
  if (fSection == "head")
    {
      G4cout << ">> Partial Head Phantom identified by UserScoreWriter." << G4endl;
    }
  if (fSection == "trunk")
    {
      G4cout << ">> Partial Trunk Phantom identified by UserScoreWriter." << G4endl;
    }
  if (fSection == "full")
    {
      G4cout << ">> Custom/Full Phantom identified by UserScoreWriter." << G4endl;
    }
  if ((fSection != "head") && (fSection != "trunk") && (fSection != "full"))
    G4cout << fSection << " can not be defined!" << G4endl;
}
