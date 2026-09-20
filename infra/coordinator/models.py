"""Modelos Pydantic de request/response de la API del coordinator."""
from pydantic import BaseModel, Field


class WorkerRegister(BaseModel):
    worker_id: str
    hostname: str = ""
    cpu_count: int = 0
    ram_gb: float = 0.0
    label: str = ""
    ram_free_gb: float | None = None
    cpu_load_pct: float | None = None
    cpu_score: float | None = None
    image_digest: str | None = None


class WorkerRef(BaseModel):
    worker_id: str


class HeartbeatIn(BaseModel):
    active_job_id: int | None = None
    ram_free_gb: float | None = None
    cpu_load_pct: float | None = None
    image_digest: str | None = None
    # orphans_killed_total (2026-09-20, ver cleanup_orphaned_simulations()
    # en worker.py): contador acumulado DE ESTE PROCESO worker, no un
    # total historico -- None para un worker viejo que no lo manda todavia.
    orphans_killed_total: int | None = None


class JobOut(BaseModel):
    attempt: int = 0
    job_id: int
    species: str
    # phase (2026-09-20, bug real preexistente corregido aqui): faltaba
    # declarar este campo -- Pydantic descarta silenciosamente cualquier
    # kwarg no declarado (JobOut(**row_to_dict(row)) en app.py le pasaba
    # 'phase' igual, pero se perdia), asi que el JSON que recibia el
    # worker nunca traia 'phase', pese a que build_command() en worker.py
    # ya usa job["phase"] (agregado 2026-09-16) -- eso causaria KeyError
    # en produccion real si ese camino llegara a ejercitarse. Cero tests
    # cubrian esto. Declararlo aqui no cambia nada mas: el valor ya vivia
    # en la fila de la base, solo faltaba pasar por el modelo.
    phase: str
    bin_index: int
    offset_x_m: float
    repeticion: int
    n_events: int
    min_ram_gb: float = 0
    min_cpu_count: int = 0
    min_cpu_score: float = 0


class JobOutV2(BaseModel):
    """Igual que JobOut, mas n_bins (2026-09-20, ver db_v2.py) -- jobs_v2
    puede pedir una grilla de energia distinta de la de 8 bins fija de v1."""
    attempt: int = 0
    job_id: int
    species: str
    phase: str
    bin_index: int
    n_bins: int
    offset_x_m: float
    repeticion: int
    n_events: int
    min_ram_gb: float = 0
    min_cpu_count: int = 0
    min_cpu_score: float = 0


class FailIn(BaseModel):
    worker_id: str
    error: str
    duration_s: float | None = None


class JobLogIn(BaseModel):
    worker_id: str
    log_tail: str = Field(max_length=65536)
    request_id: str = Field(min_length=32, max_length=32)
    attempt: int = Field(ge=1)
