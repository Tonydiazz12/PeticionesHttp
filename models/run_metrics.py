"""Estructuras de datos para almacenar métricas por corrida y resúmenes comparativos."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RunMetrics:
    """Métricas consolidadas de una única corrida de prueba."""
    run_id: str
    scenario_name: str
    repetition: int
    max_workers: int
    total_requested: int
    total_executed: int
    success_count: int
    failure_count: int
    failure_percentage: float
    global_duration_seconds: float
    latency_avg_ms: Optional[float]
    latency_min_ms: Optional[float]
    latency_max_ms: Optional[float]
    latency_p95_ms: Optional[float]
    successful_throughput_req_s: float
    observed_cpu_percent: Optional[float] = None
    cancelled_count: int = 0
    failure_breakdown: dict = field(default_factory=dict)
    target_url: str = ""
    server_1_count: int = 0
    server_2_count: int = 0
    server_3_count: int = 0
    unidentified_count: int = 0
    server_1_pct: float = 0.0
    server_2_pct: float = 0.0
    server_3_pct: float = 0.0
    observed_cpu_s1_percent: Optional[float] = None
    observed_cpu_s2_percent: Optional[float] = None
    observed_cpu_s3_percent: Optional[float] = None

    def to_dict(self) -> dict:
        def fmt_num(val: Optional[float], decimals: int = 2):
            return round(val, decimals) if val is not None else "No disponible"

        return {
            "run_id": self.run_id,
            "target_url": self.target_url,
            "scenario": self.scenario_name,
            "repetition": self.repetition,
            "max_workers": self.max_workers,
            "total_requested": self.total_requested,
            "total_executed": self.total_executed,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "cancelled_count": self.cancelled_count,
            "failure_percentage": round(self.failure_percentage, 2),
            "global_duration_s": round(self.global_duration_seconds, 4),
            "latency_avg_ms": fmt_num(self.latency_avg_ms, 3),
            "latency_min_ms": fmt_num(self.latency_min_ms, 3),
            "latency_max_ms": fmt_num(self.latency_max_ms, 3),
            "latency_p95_ms": fmt_num(self.latency_p95_ms, 3),
            "successful_throughput_req_s": round(self.successful_throughput_req_s, 2),
            "server_1_count": self.server_1_count,
            "server_2_count": self.server_2_count,
            "server_3_count": self.server_3_count,
            "unidentified_count": self.unidentified_count,
            "server_1_pct": round(self.server_1_pct, 2),
            "server_2_pct": round(self.server_2_pct, 2),
            "server_3_pct": round(self.server_3_pct, 2),
            "observed_cpu_percent": fmt_num(self.observed_cpu_percent, 1),
            "observed_cpu_s1_percent": fmt_num(self.observed_cpu_s1_percent, 1),
            "observed_cpu_s2_percent": fmt_num(self.observed_cpu_s2_percent, 1),
            "observed_cpu_s3_percent": fmt_num(self.observed_cpu_s3_percent, 1),
            "failure_breakdown": self.failure_breakdown
        }


@dataclass
class ScenarioSummary:
    """Consolidado de múltiples repeticiones de un mismo escenario para análisis comparativo."""
    scenario_name: str
    max_workers: int
    runs: List[RunMetrics] = field(default_factory=list)

    @property
    def total_runs(self) -> int:
        return len(self.runs)

    @property
    def avg_throughput(self) -> float:
        if not self.runs:
            return 0.0
        return sum(r.successful_throughput_req_s for r in self.runs) / len(self.runs)

    @property
    def max_throughput(self) -> float:
        if not self.runs:
            return 0.0
        return max(r.successful_throughput_req_s for r in self.runs)

    @staticmethod
    def _avg_optional(values: List[Optional[float]]) -> Optional[float]:
        valid = [v for v in values if v is not None]
        return (sum(valid) / len(valid)) if valid else None

    @staticmethod
    def _max_optional(values: List[Optional[float]]) -> Optional[float]:
        valid = [v for v in values if v is not None]
        return max(valid) if valid else None

    @property
    def avg_p95_ms(self) -> Optional[float]:
        return self._avg_optional([r.latency_p95_ms for r in self.runs])

    @property
    def max_p95_ms(self) -> Optional[float]:
        return self._max_optional([r.latency_p95_ms for r in self.runs])

    @property
    def avg_latency_ms(self) -> Optional[float]:
        return self._avg_optional([r.latency_avg_ms for r in self.runs])

    @property
    def max_latency_ms(self) -> Optional[float]:
        return self._max_optional([r.latency_max_ms for r in self.runs])

    @property
    def avg_cpu_percent(self) -> Optional[float]:
        return self._avg_optional([r.observed_cpu_percent for r in self.runs])

    @property
    def max_cpu_percent(self) -> Optional[float]:
        return self._max_optional([r.observed_cpu_percent for r in self.runs])

    @property
    def avg_duration_s(self) -> float:
        if not self.runs:
            return 0.0
        return sum(r.global_duration_seconds for r in self.runs) / len(self.runs)

    @property
    def max_duration_s(self) -> float:
        if not self.runs:
            return 0.0
        return max(r.global_duration_seconds for r in self.runs)

    @property
    def avg_success_count(self) -> float:
        if not self.runs:
            return 0.0
        return sum(r.success_count for r in self.runs) / len(self.runs)

    @property
    def avg_failure_count(self) -> float:
        if not self.runs:
            return 0.0
        return sum(r.failure_count for r in self.runs) / len(self.runs)

    @property
    def max_failure_count(self) -> int:
        if not self.runs:
            return 0
        return max(r.failure_count for r in self.runs)

    @property
    def min_throughput(self) -> float:
        if not self.runs:
            return 0.0
        return min(r.successful_throughput_req_s for r in self.runs)

    @property
    def avg_n1(self) -> float:
        return (sum(r.server_1_count for r in self.runs) / len(self.runs)) if self.runs else 0.0

    @property
    def avg_n2(self) -> float:
        return (sum(r.server_2_count for r in self.runs) / len(self.runs)) if self.runs else 0.0

    @property
    def avg_n3(self) -> float:
        return (sum(r.server_3_count for r in self.runs) / len(self.runs)) if self.runs else 0.0

    @property
    def avg_unidentified(self) -> float:
        return (sum(r.unidentified_count for r in self.runs) / len(self.runs)) if self.runs else 0.0

    @property
    def avg_pct_s1(self) -> float:
        total = self.avg_n1 + self.avg_n2 + self.avg_n3
        return (100.0 * self.avg_n1 / total) if total > 0 else 0.0

    @property
    def avg_pct_s2(self) -> float:
        total = self.avg_n1 + self.avg_n2 + self.avg_n3
        return (100.0 * self.avg_n2 / total) if total > 0 else 0.0

    @property
    def avg_pct_s3(self) -> float:
        total = self.avg_n1 + self.avg_n2 + self.avg_n3
        return (100.0 * self.avg_n3 / total) if total > 0 else 0.0

    @property
    def avg_cpu_s1(self) -> Optional[float]:
        return self._avg_optional([r.observed_cpu_s1_percent for r in self.runs])

    @property
    def max_cpu_s1(self) -> Optional[float]:
        return self._max_optional([r.observed_cpu_s1_percent for r in self.runs])

    @property
    def avg_cpu_s2(self) -> Optional[float]:
        return self._avg_optional([r.observed_cpu_s2_percent for r in self.runs])

    @property
    def max_cpu_s2(self) -> Optional[float]:
        return self._max_optional([r.observed_cpu_s2_percent for r in self.runs])

    @property
    def avg_cpu_s3(self) -> Optional[float]:
        return self._avg_optional([r.observed_cpu_s3_percent for r in self.runs])

    @property
    def max_cpu_s3(self) -> Optional[float]:
        return self._max_optional([r.observed_cpu_s3_percent for r in self.runs])

