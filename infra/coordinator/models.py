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


class JobOut(BaseModel):
    attempt: int = 0
    job_id: int
    species: str
    bin_index: int
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
