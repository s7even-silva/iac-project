# Comparación de la metodología con la literatura (2026-10-31)

La metodología de la v2 se construyó casi sin mirar otros proyectos. Esta
nota la compara con los trabajos más cercanos para ver si está a la altura
del estándar y dónde gana o pierde. Es una revisión acotada (una sesión de
búsqueda), no una revisión sistemática. Las fuentes que no se pudieron abrir
se marcan como tales.

## Trabajos revisados

| Trabajo | Qué hace | Cómo lo hace |
|---|---|---|
| Vuolo et al. 2016, *Life Sci. Space Res.* 8:22 (SR2S) | Toroide superconductor de MgB₂ | Geant4 (GRAS); campo + materiales del imán + nave + **estructura de soporte realista**; GCR de protones y núcleos con Z ≥ 2. Según su resumen, protones y helio dan ~85% de la dosis total. Solo se leyó el resumen (el texto completo dio 403). |
| Ambroglini, Battiston y Burger 2016, *Front. Oncol.* 6:97 (grupo de ARSSEM) | Compara configuraciones de ESA, NIAC y SR2S | **Dosis equivalente** (cSv/año) en BFO y piel de cilindros de agua. Reducciones del campo de ~20–25% (hasta ~50% con 23 T·m); incertidumbres de ~3–5%. |
| Battiston et al. 2012, ARSSEM (arXiv:1209.1907) | Geom13/14 | Dosis por grupo de Z (1, 2, 3–10, 11–20, 21–28): incluye iones hasta Fe. |
| Ferrone 2020, tesis (UTHealth) | Blindaje magnético activo | Geant4; **dosis efectiva** y riesgo; fantomas de ambos sexos y varias edades; más de 100 escenarios. Solo se leyó el resumen. |
| Washburn et al. (NASA, 2013–2015) y Hesse-Withbroe y Arquilla 2025 (arXiv:2509.09051) | Solenoides | Dosis equivalente con HZETRN o modelos semianalíticos; la figura de mérito es la **masa ahorrada frente a un blindaje pasivo** que da la misma reducción. |
| Naito y Kodaira 2022, *Sci. Rep.* (PMC9365775) | Dosimetría de GCR en espacio profundo | Geant4 10.04; Q de ICRP. En espacio libre el hidrógeno da 98.6 de 162 mGy/año de dosis absorbida, pero los iones pesados pesan mucho más en la dosis equivalente. |
| NASA-STD-3001, vol. 1, rev. B (2022) | Norma | Límite de carrera de 600 mSv de dosis efectiva; SEP de diseño = suma de los eventos de octubre de 1989, < 250 mSv; límites por órgano a 30 días en mGy-Eq. |
| ICRP 123 (2013) | Dosimetría de astronautas | Q(L) de ICRP 60 en lugar de w_R para el espacio. |
| Zeitlin et al. 2013, *Science* 340:1080 (MSL/RAD) | Medición en crucero a Marte | ~1.8 mSv/día de dosis equivalente de GCR dentro de la nave: referencia medida que suelen usar los modelos. |

## Comparación por aspecto

| Aspecto | Práctica en la literatura | Este proyecto | Lectura |
|---|---|---|---|
| **Especies de GCR** | Todo el espectro, Z = 1–28 (SR2S, ARSSEM, NASA) | **Solo H y He** | **Desventaja principal.** H y He dominan la dosis absorbida (~85% en SR2S), pero los iones pesados dominan la dosis equivalente detrás de blindajes delgados, y nuestro casco es de 4 g/cm². Con el endpoint de D2 (dosis equivalente efectiva con Q(L)), faltaría gran parte del resultado. |
| SEP | Eventos históricos; NASA diseña con octubre de 1989 | Octubre de 1989 y febrero de 1956 (OLTARIS) | Alineado: el caso SEP máximo es el SEP de diseño de NASA. |
| Modelo de GCR | BON (NASA), ISO 15390 | BON2020 | Alineado con el modelo vigente de NASA. |
| Fantoma | Cilindros o esferas de agua (SR2S, Ambroglini); antropomórficos (Ferrone) | Vóxeles ICRP110, AM y AF, por órgano | **Ventaja:** dosis por órgano y dosis efectiva reales. |
| Magnitudes | Dosis equivalente con Q(L); dosis efectiva; BFO y piel | Dosis absorbida y Q(L) (R2, pendiente de implementar); E con w_T de ICRP 103 | Alineado, una vez implementado R2. |
| Campo | Mapas del diseño del imán, modelos analíticos o idealizados | Biot-Savart volumétrico con error medido, verificado con Elmer | **Ventaja:** error del campo cuantificado. |
| Materiales del imán | SR2S incluye estructura de soporte; NASA suma la masa del sistema | Bobinas homogeneizadas (15.6 t); sin estructura, criostato ni soporte | **Desventaja:** faltan secundarios de la estructura. Declararla o agregar una masa equivalente. |
| Control | Campo encendido frente a apagado con los mismos materiales (SR2S) | El mismo control (`fieldScale 0`) | Alineado. |
| Comparación con blindaje pasivo | Figura de mérito central: masa ahorrada frente a un blindaje pasivo de igual efecto (Washburn, Hesse-Withbroe) | Capas pasivas implementadas pero apagadas; no está en el plan | **Falta.** Es barata de agregar: una configuración pasiva de igual masa. |
| Fuente | Isótropa desde una superficie envolvente (GRAS) | Ley coseno sobre una esfera de 14–18 m, radio validado por reentradas | Alineado, con una validación más explícita que la usual. |
| Integración espectral | Muestreo directo del espectro, o coeficientes monoenergéticos (ICRP 116) | Respuesta monoenergética por energía y plegado con el espectro, grilla validada (P4) | Alineado; además permite reusar las corridas con otros espectros. |
| Posición del astronauta | Promedios en el hábitat (Ambroglini usa seis cilindros) | 5 posiciones | Ventaja: da la dependencia con la posición. |
| Estadística | Errores estadísticos reportados (1–10%); casi nunca criterios fijados de antemano | Pilotos con criterios previos, SE por evento con VOV, pruebas de equivalencia, CRN | **Ventaja** en rigor; desventaja en costo y tiempo. |
| Validación física | Comparación entre códigos (Geant4, HZETRN, PHITS, FLUKA) y con mediciones (MSL/RAD) | P0 contra ICRP 116 (normalización); no hay comparación con mediciones ni sensibilidad a la physics list | **Falta:** un benchmark del transporte de GCR y una prueba de sensibilidad a la physics list. |
| Resultados para misión | Dosis anual o por misión y riesgo (REID) | Tasa de dosis y η | Menor: el paso a dosis de misión es posprocesado. |

## Conclusión

La metodología está bien planteada y, en el tratamiento estadístico, el
fantoma y el campo, es más rigurosa que lo usual en este tema. Hay cuatro
huecos frente al estándar, por orden de impacto:

1. **Iones pesados (Z ≥ 3).** Afecta directamente al endpoint primario
   (dosis equivalente efectiva con Q(L)). Opciones:
   - agregar iones representativos por grupo de carga (por ejemplo O, Si
     y Fe), con sus espectros BON2020 de OLTARIS; o
   - restringir el resultado a «H + He» y declararlo, aceptando que no se
     compara con los límites de NASA.

   Hay que decidirlo antes de congelar la configuración, porque cambia el
   costo y la lista de casos.
2. **Estructura del imán.** Declarar que no está, o modelarla como masa
   equivalente si NIAC da su valor.
3. **Configuración pasiva de igual masa,** como comparación secundaria.
   Es la figura de mérito que usa la literatura para juzgar un escudo
   activo.
4. **Validación física externa:** un caso comparado con OLTARIS/HZETRN o
   con una medición (MSL/RAD), y la sensibilidad a la physics list en
   2–3 puntos (hecha en P0 contra ICRP 116, 2026-11-02: llevó a cambiar a
   `QGSP_INCLXX_HP`; ver `plan_piloto.md`, P0).

Ninguno de los cuatro invalida lo hecho hasta ahora: la geometría, el campo
y los pilotos P0–P7 siguen valiendo. El primero sí cambia el alcance del
barrido.

## Fuentes

- [Vuolo et al. 2016](https://www.sciencedirect.com/science/article/abs/pii/S221455241600002X)
- [Ambroglini, Battiston y Burger 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC4896949/)
- [ARSSEM, arXiv:1209.1907](https://arxiv.org/pdf/1209.1907)
- [Ferrone 2020](https://digitalcommons.library.tmc.edu/utgsbs_dissertations/1019)
- [Hesse-Withbroe y Arquilla 2025](https://arxiv.org/abs/2509.09051)
- [Naito y Kodaira 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9365775/)
- [NASA-STD-3001 vol. 1 rev. B](https://www.nasa.gov/wp-content/uploads/2020/10/2022-01-05_nasa-std-3001_vol.1_rev._b_final_draft_with_signature_010522.pdf)
- [ICRP 123 (ICRPaedia)](https://icrpaedia.org/ICRP_Publication_123)
- [Zeitlin et al. 2013 (resumen de AAAS)](https://www.aaas.org/news/science-mars-mission-reveals-radiation-risk-future-astronauts)
