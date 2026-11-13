"""Configuración y reglas de validación para el generador de carga HTTP."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Set
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Excepción lanzada cuando los parámetros de configuración violan restricciones de seguridad o límites."""
    pass


@dataclass(init=False)
class TargetConfig:
    """Configuración del destino de pruebas (ALB o servidor local) con lista blanca de seguridad."""
    target_url: str
    allowed_hosts: Set[str]

    def __init__(
        self,
        target_url: str = "",
        allowed_hosts: Optional[Set[str]] = None,
        alb_url: Optional[str] = None
    ):
        self.target_url = (target_url or alb_url or "").strip()
        self.allowed_hosts = set(allowed_hosts) if allowed_hosts is not None else set()
        self._hostname: str = ""
        self.validate()

    @property
    def alb_url(self) -> str:
        """Alias descriptivo de la URL del Application Load Balancer."""
        return self.target_url

    @property
    def hostname(self) -> str:
        """Hostname validado en minúsculas."""
        return self._hostname

    def validate(self) -> None:
        """Valida que la URL sea sintácticamente correcta, el puerto sea válido y el host esté autorizado."""
        if not self.target_url or not isinstance(self.target_url, str):
            raise ConfigurationError("La URL de destino no puede estar vacía.")

        parsed = urlparse(self.target_url.strip())
        if parsed.scheme not in ("http", "https"):
            raise ConfigurationError(
                f"Esquema de URL no válido: '{parsed.scheme}'. Solo se admite 'http' o 'https'."
            )

        hostname = parsed.hostname
        if not hostname:
            raise ConfigurationError(f"No se pudo extraer el host de la URL '{self.target_url}'.")

        try:
            explicit_port = parsed.port
        except ValueError as exc:
            raise ConfigurationError(f"Puerto no válido en la URL '{self.target_url}': {exc}") from exc

        normalized_host = hostname.lower()
        if normalized_host not in {"127.0.0.1", "localhost"} and explicit_port is not None and explicit_port != 80:
            raise ConfigurationError("El puerto para el ALB remoto debe ser TCP 80.")

        # Limpiar lista blanca (minúsculas y sin espacios)
        normalized_allowed = {h.strip().lower() for h in self.allowed_hosts if h.strip()}

        if not normalized_allowed:
            raise ConfigurationError(
                "La lista de hosts autorizados (allowed_hosts) está vacía. "
                "Por seguridad, debe registrar al menos el DNS de su ALB o entorno local permitido."
            )

        if normalized_host not in normalized_allowed:
            raise ConfigurationError(
                f"Destino NO autorizado: '{hostname}'. No coincide con ningún host permitido: {sorted(list(normalized_allowed))}."
            )

        self._hostname = normalized_host


DEFAULT_SERVER_MESSAGES: Dict[str, str] = {
    "Servidor 1": "Bienvenidos al Servidor 1",
    "Servidor 2": "Bienvenidos al Servidor 2",
    "Servidor 3": "Bienvenidos al Servidor 3",
}


@dataclass
class RunConfig:
    """Configuración de ejecución para un escenario de carga."""
    scenario_name: str
    total_requests: int
    max_workers: int
    timeout_seconds: float = 5.0
    repetitions: int = 1
    pause_between_runs_seconds: float = 3.0
    results_dir: Path = Path("resultados")
    expected_text: str = "Bienvenidos al Servidor 1"
    valid_server_messages: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SERVER_MESSAGES))
    max_consecutive_failures: int = 50  # Circuit-breaker ante caída persistente

    MAX_ALLOWED_REQUESTS: int = 5000
    MAX_ALLOWED_WORKERS: int = 100

    def __post_init__(self):
        if isinstance(self.results_dir, str):
            self.results_dir = Path(self.results_dir)
        self.validate()

    def validate(self) -> None:
        """Asegura el cumplimiento estricto de las restricciones impuestas."""
        if not (1 <= self.total_requests <= self.MAX_ALLOWED_REQUESTS):
            raise ConfigurationError(
                f"Total de solicitudes ({self.total_requests}) fuera de rango. Debe estar entre 1 y {self.MAX_ALLOWED_REQUESTS}."
            )

        if not (1 <= self.max_workers <= self.MAX_ALLOWED_WORKERS):
            raise ConfigurationError(
                f"Número de hilos ({self.max_workers}) fuera de rango. Debe estar entre 1 y {self.MAX_ALLOWED_WORKERS}."
            )

        if self.timeout_seconds <= 0:
            raise ConfigurationError(f"El timeout ({self.timeout_seconds}s) debe ser mayor a 0.")

        if self.repetitions < 1:
            raise ConfigurationError(f"Las repeticiones ({self.repetitions}) deben ser al menos 1.")

        if self.pause_between_runs_seconds < 0:
            raise ConfigurationError("La pausa entre corridas no puede ser negativa.")


class PresetScenarios:
    """Definición estandarizada de los escenarios obligatorios de la práctica."""

    @staticmethod
    def baseline() -> RunConfig:
        return RunConfig(
            scenario_name="Línea Base",
            total_requests=20,
            max_workers=1,
            repetitions=1,
            pause_between_runs_seconds=2.0
        )

    @staticmethod
    def scenario_1() -> RunConfig:
        return RunConfig(
            scenario_name="Escenario 1",
            total_requests=100,
            max_workers=10,
            repetitions=3,
            pause_between_runs_seconds=3.0
        )

    @staticmethod
    def scenario_2() -> RunConfig:
        return RunConfig(
            scenario_name="Escenario 2",
            total_requests=1000,
            max_workers=50,
            repetitions=3,
            pause_between_runs_seconds=4.0
        )

    @staticmethod
    def scenario_3() -> RunConfig:
        return RunConfig(
            scenario_name="Escenario 3",
            total_requests=5000,
            max_workers=100,
            repetitions=3,
            pause_between_runs_seconds=5.0
        )

    @staticmethod
    def fault_simulation() -> RunConfig:
        """Prueba de tolerancia a fallos de 20 solicitudes ante caída de un servidor en el Target Group."""
        return RunConfig(
            scenario_name="Simulación de Falla",
            total_requests=20,
            max_workers=1,
            repetitions=1,
            pause_between_runs_seconds=2.0
        )

