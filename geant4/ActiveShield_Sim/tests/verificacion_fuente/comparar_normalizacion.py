#!/usr/bin/env python3
"""Compara cruces y longitud de traza de normalizacion_caja.mac contra N/(pi R^2).
Correr desde el directorio de build donde se ejecuto el macro (lee FluxCur.txt y FluxLen.txt).
ICRP110UserScoreWriter divide toda magnitud volcada por `joule`; se deshace aqui."""
import math
J = 6.241509074e12  # 1 J en MeV (unidad interna de Geant4)
def leer(nombre):
    linea = [l for l in open(nombre) if not l.startswith("#")][0]
    return float(linea.split()[3]) * J
N = 1_000_000
R = math.sqrt(450**2 + 500**2) + 0.001 + 20.0          # cm, GetSourceSphereRadius() con casco 0.001 cm
a = 50.0                                               # cm, lado de la caja
C, L = leer("FluxCur.txt"), leer("FluxLen.txt")
esp_C = N * 1.5 * a * a / (math.pi * R * R)            # area proyectada media de un cubo = 1.5 a^2
esp_L = N / (math.pi * R * R) * a**3 * 10              # fluencia * volumen, en mm
print(f"cruces {C:.0f} / esperado {esp_C:.1f} = {C/esp_C:.3f} +- {math.sqrt(C)/esp_C:.3f}")
print(f"traza  {L:.0f} mm / esperado {esp_L:.0f} mm = {L/esp_L:.3f}")
