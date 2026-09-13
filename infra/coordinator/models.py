"""Modelos Pydantic de request/response de la API del coordinator."""
from pydantic import BaseModel


class WorkerRegister(BaseModel):
    worker_id: str
    hostname: str = ""
    cpu_count: int = 0
    ram_gb: float = 0.0
    label: str = ""


class WorkerRef(BaseModel):
    worker_id: str


class JobOut(BaseModel):
    job_id: int
    species: str
    bin_index: int
    offset_x_m: float
    repeticion: int
    n_events: int


class FailIn(BaseModel):
    worker_id: str
    error: str
    duration_s: float | None = None
