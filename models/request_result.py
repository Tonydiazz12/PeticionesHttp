"""Definición de estados y estructura de registro individual por petición."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RequestStatus(str, Enum):
    """Clasificación exhaustiva del resultado de cada petición HTTP."""
    SUCCESS = "SUCCESS"                         # 200 OK y contenido verificado
    HTTP_STATUS_ERROR = "HTTP_STATUS_ERROR"     # Código HTTP diferente a 200
    CONTENT_MISMATCH = "CONTENT_MISMATCH"       # 200 OK pero sin el contenido exacto esperado
    CONNECTION_ERROR = "CONNECTION_ERROR"       # Conexión rechazada, DNS no resuelto o caída TCP
    TIMEOUT = "TIMEOUT"                         # Tiempo de espera agotado
    OTHER_ERROR = "OTHER_ERROR"                 # Otras excepciones de red o sistema
    CANCELLED = "CANCELLED"                     # Petición no enviada debido a detención/interrupción


@dataclass(slots=True)
class RequestRecord:
    """Registro inmutable de una petición ejecutada en el generador."""
    request_id: int
    scenario: str
    repetition: int
    timestamp_iso: str
    duration_ms: float
    http_status: Optional[int]
    status: RequestStatus
    error_detail: str = ""
    server_id: str = "No identificado"
    response_body: str = ""

    @property
    def is_success(self) -> bool:
        return self.status == RequestStatus.SUCCESS

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "scenario": self.scenario,
            "repetition": self.repetition,
            "timestamp_iso": self.timestamp_iso,
            "duration_ms": round(self.duration_ms, 3),
            "http_status": self.http_status if self.http_status is not None else "N/A",
            "status": self.status.value,
            "server_id": self.server_id,
            "response_body": self.response_body,
            "error_detail": self.error_detail
        }

