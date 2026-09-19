#!/usr/bin/env python3
"""Contrato de estado entre fases del workflow de pilotos (2026-09-19,
pedido explicito del equipo: encadenar Fases 7->10 sin bloquear la
ejecucion de un script mientras se espera una decision humana en un
punto donde el propio plan dice que hace falta juicio, no un numero).

Cada analyze_faseN.py escribe UN objeto FaseResult a
pilots/results/state/faseN_estado.json al terminar su analisis. El
orquestador (run_pilot_workflow.py) lee ese archivo, decide si puede
seguir solo a la fase siguiente o si tiene que detenerse, y nunca
inventa un veredicto que el propio analyze_faseN.py no haya escrito --
la logica de "cumple/no cumple/limitrofe" vive en cada fase (que conoce
sus propios numeros y umbrales), no en el orquestador (que solo
encadena).

Veredictos posibles (VERDICT_*): deliberadamente pocos y genericos,
para que las 4 fases los compartan sin que el orquestador tenga que
conocer el significado especifico de cada fase.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent / "results" / "state"

# AUTO: el gate puede decidir solo, sin ambiguedad -- el propio plan da
#   un numero/umbral para este caso (ej. Fase 8: B_8_16 claramente <=2.5pp
#   o claramente >2.5pp, sin zona gris).
# LIMITROFE: el propio plan dice explicitamente que este caso requiere
#   comprobacion adicional (ej. Fase 8: "si 8->16 es limitrofe, comprobar
#   16->32") -- el orquestador se detiene, pero con instrucciones
#   concretas de que correr para resolver la ambiguedad.
# REVISAR: el resultado esta fuera de lo que el plan anticipo (ej. ratios
#   SE_within/s_between con muy pocas seeds, o un valor "inesperado" como
#   >>1 en vez de ~1 o <<1) -- requiere que una persona mire los datos
#   antes de decidir cualquier cosa, el orquestador no tiene ninguna regla
#   de fallback razonable para este caso.
# FALLO: la fase no pudo completarse (corridas fallidas, datos
#   insuficientes) -- no es un veredicto cientifico, es un problema
#   operativo que hay que resolver antes de poder evaluar nada.
VERDICT_AUTO_CONTINUE = "auto_continue"
VERDICT_LIMITROFE = "limitrofe"
VERDICT_REVISAR = "revisar"
VERDICT_FALLO = "fallo"
ALL_VERDICTS = {VERDICT_AUTO_CONTINUE, VERDICT_LIMITROFE, VERDICT_REVISAR, VERDICT_FALLO}


@dataclass
class FaseResult:
    fase: str  # "fase7", "fase8", etc.
    veredicto: str  # uno de ALL_VERDICTS
    resumen: str  # una linea legible, lo primero que lee un humano
    detalle: dict = field(default_factory=dict)  # numeros/paths especificos de la fase, libre por fase
    instrucciones_si_no_auto: str = ""  # como continuar a mano si veredicto != AUTO_CONTINUE
    out_dir: str = ""  # directorio de resultados de ESTA corrida de la fase
    generado_en: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if self.veredicto not in ALL_VERDICTS:
            raise ValueError(f"veredicto invalido: {self.veredicto!r} (debe ser uno de {ALL_VERDICTS})")


def write_state(result: FaseResult) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{result.fase}_estado.json"
    path.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    return path


def read_state(fase: str) -> FaseResult | None:
    path = STATE_DIR / f"{fase}_estado.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    return FaseResult(**data)
