Fase 8, comprobacion de binning, n_events=200 (smoke test), grillas 8/16/32 bins, 168 corridas.
Corrida ANTERIOR al fix de semillas (02be868): combo_idx = posicion en --combos ("GCR_He/min,SEP_p/max,GCR_H/min"
-> 0/1/2), NO el orden canonico. No es un resultado valido de Fase 8; solo sirve como referencia numerica.
Binario con columnas intra-run (S1/S2/N/SE_run) pero sin se_run_total_j (se calcula n*se_run_j al parsear).
SEP_p/max a 8 bins: dosis exactamente 0 (0,019 MeV no atraviesa el casco). Solo se incluyen outs/, manifest.csv y
epsilon_binning_por_combo.csv (sin logs ni macros). Las rutas absolutas del manifest son de la maquina original.
