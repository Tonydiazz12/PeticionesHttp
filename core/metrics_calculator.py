"""Cálculo estandarizado y determinista de métricas de rendimiento y percentil 95."""

import math
from typing import Dict, List, Optional
from models.request_result import RequestRecord, RequestStatus
from models.run_metrics import RunMetrics


class MetricsCalculator:
    """Calculadora matemática de métricas de rendimiento con definición documentada de P95."""

    @staticmethod
    def calculate_percentile_95(latencies: List[float]) -> Optional[float]:
        """Calcula el Percentil 95 (P95) de una lista de latencias exitosas en milisegundos.
        
        MÉTODO DE CÁLCULO DOCUMENTADO:
        Se emplea el método estándar de rango porcentual con interpolación lineal
        (Método 7 de Hyndman & Fan, estándar en NumPy, R y pandas).
        
        Procedimiento:
        1. Se ordenan las N latencias en orden ascendente: x_0 <= x_1 <= ... <= x_{N-1}.
        2. Si N == 0: Retorna None ("No disponible").
        3. Si N == 1: Retorna x_0.
        4. Se calcula la posición virtual: index = 0.95 * (N - 1).
        5. Se separa en parte entera (i = int(index)) y parte fraccionaria (f = index - i).
        6. Si i + 1 < N:
               P95 = x_i + f * (x_{i+1} - x_i)
           De lo contrario:
               P95 = x_i
        """
        if not latencies:
            return None

        n = len(latencies)
        if n == 1:
            return latencies[0]

        sorted_latencies = sorted(latencies)
        virtual_index = 0.95 * (n - 1)
        lower_idx = int(math.floor(virtual_index))
        upper_idx = int(math.ceil(virtual_index))

        if lower_idx == upper_idx or upper_idx >= n:
            return sorted_latencies[lower_idx]

        fraction = virtual_index - lower_idx
        return sorted_latencies[lower_idx] + fraction * (sorted_latencies[upper_idx] - sorted_latencies[lower_idx])

    @classmethod
    def compute_run_metrics(
        cls,
        run_id: str,
        scenario_name: str,
        repetition: int,
        max_workers: int,
        total_requested: int,
        records: List[RequestRecord],
        global_duration_seconds: float,
        observed_cpu_percent: Optional[float] = None,
        cancelled_count: int = 0,
        target_url: str = "",
        observed_cpu_s1_percent: Optional[float] = None,
        observed_cpu_s2_percent: Optional[float] = None,
        observed_cpu_s3_percent: Optional[float] = None
    ) -> RunMetrics:
        """Calcula las métricas consolidadas a partir de la lista de registros de una corrida."""
        success_records = [r for r in records if r.is_success]
        failure_records = [r for r in records if not r.is_success and r.status != RequestStatus.CANCELLED]
        actual_cancelled = [r for r in records if r.status == RequestStatus.CANCELLED]
        total_cancelled = len(actual_cancelled) if actual_cancelled else cancelled_count

        success_count = len(success_records)
        failure_count = len(failure_records)
        total_executed = success_count + failure_count

        # Invariantes obligatorios de integridad (sin doble conteo)
        assert (success_count + failure_count) == total_executed, (
            f"Inconsistencia en el conteo: Éxitos ({success_count}) + Fallas ({failure_count}) "
            f"!= Ejecutadas ({total_executed})"
        )
        assert (total_executed + len(actual_cancelled)) == len(records), (
            f"Inconsistencia en registros: Ejecutadas ({total_executed}) + "
            f"Canceladas ({len(actual_cancelled)}) != Total registros ({len(records)})"
        )

        failure_percentage = (failure_count / total_executed * 100.0) if total_executed > 0 else 0.0

        # Distribución de respuestas exitosas por servidor
        n1 = sum(1 for r in success_records if r.server_id == "Servidor 1")
        n2 = sum(1 for r in success_records if r.server_id == "Servidor 2")
        n3 = sum(1 for r in success_records if r.server_id == "Servidor 3")
        denom = n1 + n2 + n3
        if denom > 0:
            pct1 = 100.0 * n1 / denom
            pct2 = 100.0 * n2 / denom
            pct3 = 100.0 * n3 / denom
        else:
            pct1 = 0.0
            pct2 = 0.0
            pct3 = 0.0

        unidentified_count = sum(
            1 for r in records
            if r.status != RequestStatus.CANCELLED and r.server_id not in ("Servidor 1", "Servidor 2", "Servidor 3")
        )

        # Latencias solo de peticiones exitosas
        successful_latencies = [r.duration_ms for r in success_records]

        if successful_latencies:
            lat_avg: Optional[float] = sum(successful_latencies) / len(successful_latencies)
            lat_min: Optional[float] = min(successful_latencies)
            lat_max: Optional[float] = max(successful_latencies)
            lat_p95: Optional[float] = cls.calculate_percentile_95(successful_latencies)
        else:
            lat_avg = None
            lat_min = None
            lat_max = None
            lat_p95 = None

        # Throughput exitoso = peticiones_exitosas / tiempo_global_en_segundos
        throughput = (success_count / global_duration_seconds) if global_duration_seconds > 0 else 0.0

        # Desglose de fallas
        failure_breakdown: Dict[str, int] = {}
        for r in failure_records:
            key = r.status.value
            failure_breakdown[key] = failure_breakdown.get(key, 0) + 1

        # Si no se pasó CPU general pero sí alguna de las 3 instancias EC2, calcular promedio observado
        if observed_cpu_percent is None:
            cpu_vals = [
                c for c in (observed_cpu_s1_percent, observed_cpu_s2_percent, observed_cpu_s3_percent)
                if c is not None
            ]
            if cpu_vals:
                observed_cpu_percent = sum(cpu_vals) / len(cpu_vals)

        return RunMetrics(
            run_id=run_id,
            scenario_name=scenario_name,
            repetition=repetition,
            max_workers=max_workers,
            total_requested=total_requested,
            total_executed=total_executed,
            success_count=success_count,
            failure_count=failure_count,
            failure_percentage=failure_percentage,
            global_duration_seconds=global_duration_seconds,
            latency_avg_ms=lat_avg,
            latency_min_ms=lat_min,
            latency_max_ms=lat_max,
            latency_p95_ms=lat_p95,
            successful_throughput_req_s=throughput,
            observed_cpu_percent=observed_cpu_percent,
            cancelled_count=total_cancelled,
            failure_breakdown=failure_breakdown,
            target_url=target_url,
            server_1_count=n1,
            server_2_count=n2,
            server_3_count=n3,
            unidentified_count=unidentified_count,
            server_1_pct=pct1,
            server_2_pct=pct2,
            server_3_pct=pct3,
            observed_cpu_s1_percent=observed_cpu_s1_percent,
            observed_cpu_s2_percent=observed_cpu_s2_percent,
            observed_cpu_s3_percent=observed_cpu_s3_percent
        )

