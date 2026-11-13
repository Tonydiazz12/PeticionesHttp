"""Pruebas para el cálculo matemático de métricas y percentil 95."""

import pytest
from core.metrics_calculator import MetricsCalculator
from models.request_result import RequestRecord, RequestStatus


def test_percentile_95_empty():
    assert MetricsCalculator.calculate_percentile_95([]) is None


def test_percentile_95_single_element():
    assert MetricsCalculator.calculate_percentile_95([42.5]) == 42.5


def test_percentile_95_known_values():
    # 100 valores uniformes de 1 a 100 ms
    # Para N = 100, index = 0.95 * (100 - 1) = 94.05
    # lower_idx = 94 (valor 95), upper_idx = 95 (valor 96), fraction = 0.05
    # Resultado esperado = 95 + 0.05 * (96 - 95) = 95.05
    data = list(range(1, 101))
    p95 = MetricsCalculator.calculate_percentile_95([float(x) for x in data])
    assert p95 is not None
    assert abs(p95 - 95.05) < 1e-4


def test_compute_run_metrics_all_success():
    records = [
        RequestRecord(1, "Test", 1, "2026-11-11T00:00:00Z", 10.0, 200, RequestStatus.SUCCESS),
        RequestRecord(2, "Test", 1, "2026-11-11T00:00:01Z", 20.0, 200, RequestStatus.SUCCESS),
        RequestRecord(3, "Test", 1, "2026-11-11T00:00:02Z", 30.0, 200, RequestStatus.SUCCESS),
        RequestRecord(4, "Test", 1, "2026-11-11T00:00:03Z", 40.0, 200, RequestStatus.SUCCESS),
    ]
    # Tiempo global: 2.0 segundos -> Throughput = 4 / 2.0 = 2.0 req/s
    metrics = MetricsCalculator.compute_run_metrics(
        run_id="run_1",
        scenario_name="Test",
        repetition=1,
        max_workers=2,
        total_requested=4,
        records=records,
        global_duration_seconds=2.0,
        observed_cpu_percent=15.5
    )

    assert metrics.total_requested == 4
    assert metrics.total_executed == 4
    assert metrics.success_count == 4
    assert metrics.failure_count == 0
    assert metrics.failure_percentage == 0.0
    assert metrics.latency_avg_ms == 25.0
    assert metrics.latency_min_ms == 10.0
    assert metrics.latency_max_ms == 40.0
    assert metrics.latency_p95_ms is not None
    assert metrics.successful_throughput_req_s == 2.0
    assert metrics.observed_cpu_percent == 15.5


def test_compute_run_metrics_with_failures():
    records = [
        RequestRecord(1, "Test", 1, "2026-11-11T00:00:00Z", 10.0, 200, RequestStatus.SUCCESS),
        RequestRecord(2, "Test", 1, "2026-11-11T00:00:01Z", 5.0, 500, RequestStatus.HTTP_STATUS_ERROR, "Error 500"),
        RequestRecord(3, "Test", 1, "2026-11-11T00:00:02Z", 5000.0, None, RequestStatus.TIMEOUT, "Timeout"),
        RequestRecord(4, "Test", 1, "2026-11-11T00:00:03Z", 2.0, 200, RequestStatus.CONTENT_MISMATCH, "Bad body"),
    ]
    metrics = MetricsCalculator.compute_run_metrics(
        run_id="run_failures",
        scenario_name="Test",
        repetition=1,
        max_workers=2,
        total_requested=4,
        records=records,
        global_duration_seconds=5.0
    )

    assert metrics.total_executed == 4
    assert metrics.success_count == 1
    assert metrics.failure_count == 3
    assert metrics.failure_percentage == 75.0
    # Latencias solo de la exitosa
    assert metrics.latency_avg_ms == 10.0
    assert metrics.latency_min_ms == 10.0
    assert metrics.latency_max_ms == 10.0
    assert metrics.latency_p95_ms == 10.0
    # Throughput exitoso: 1 / 5.0 = 0.2 req/s
    assert metrics.successful_throughput_req_s == 0.2
    assert metrics.failure_breakdown["HTTP_STATUS_ERROR"] == 1
    assert metrics.failure_breakdown["TIMEOUT"] == 1
    assert metrics.failure_breakdown["CONTENT_MISMATCH"] == 1


def test_compute_run_metrics_zero_success():
    records = [
        RequestRecord(1, "Test", 1, "2026-11-11T00:00:00Z", 5.0, 502, RequestStatus.HTTP_STATUS_ERROR, "Bad Gateway")
    ]
    metrics = MetricsCalculator.compute_run_metrics(
        run_id="run_zero",
        scenario_name="Test",
        repetition=1,
        max_workers=1,
        total_requested=1,
        records=records,
        global_duration_seconds=1.0
    )

    assert metrics.success_count == 0
    assert metrics.failure_count == 1
    assert metrics.latency_avg_ms is None
    assert metrics.latency_min_ms is None
    assert metrics.latency_max_ms is None
    assert metrics.latency_p95_ms is None
    assert metrics.successful_throughput_req_s == 0.0
    assert metrics.to_dict()["latency_avg_ms"] == "No disponible"
    assert metrics.to_dict()["latency_p95_ms"] == "No disponible"
    assert metrics.server_1_pct == 0.0
    assert metrics.server_2_pct == 0.0
    assert metrics.server_3_pct == 0.0
    assert metrics.unidentified_count == 1


def test_compute_run_metrics_alb_distribution_and_cancelled_no_double_count():
    records = [
        RequestRecord(1, "ALB", 1, "2026-11-12T00:00:00Z", 10.0, 200, RequestStatus.SUCCESS, "", "Servidor 1", "Bienvenidos al Servidor 1"),
        RequestRecord(2, "ALB", 1, "2026-11-12T00:00:01Z", 12.0, 200, RequestStatus.SUCCESS, "", "Servidor 2", "Bienvenidos al Servidor 2"),
        RequestRecord(3, "ALB", 1, "2026-11-12T00:00:02Z", 14.0, 200, RequestStatus.SUCCESS, "", "Servidor 2", "Bienvenidos al Servidor 2"),
        RequestRecord(4, "ALB", 1, "2026-11-12T00:00:03Z", 16.0, 200, RequestStatus.SUCCESS, "", "Servidor 3", "Bienvenidos al Servidor 3"),
        RequestRecord(5, "ALB", 1, "2026-11-12T00:00:04Z", 5.0, 200, RequestStatus.CONTENT_MISMATCH, "Unknown", "No identificado", "Hola"),
        RequestRecord(6, "ALB", 1, "2026-11-12T00:00:05Z", 0.0, None, RequestStatus.CANCELLED, "Cancelada"),
    ]
    metrics = MetricsCalculator.compute_run_metrics(
        run_id="run_alb",
        scenario_name="ALB",
        repetition=1,
        max_workers=2,
        total_requested=6,
        records=records,
        global_duration_seconds=2.0,
        cancelled_count=1,
        target_url="http://mi-alb.elb.amazonaws.com/",
        observed_cpu_s1_percent=12.0,
        observed_cpu_s2_percent=18.0,
        observed_cpu_s3_percent=None
    )

    # Cuadre exacto sin doble conteo
    assert metrics.total_executed == 5
    assert metrics.success_count == 4
    assert metrics.failure_count == 1
    assert metrics.cancelled_count == 1
    assert metrics.server_1_count == 1
    assert metrics.server_2_count == 2
    assert metrics.server_3_count == 1
    assert metrics.unidentified_count == 1
    assert abs(metrics.server_1_pct - 25.0) < 1e-6
    assert abs(metrics.server_2_pct - 50.0) < 1e-6
    assert abs(metrics.server_3_pct - 25.0) < 1e-6
    assert metrics.observed_cpu_s1_percent == 12.0
    assert metrics.observed_cpu_s2_percent == 18.0
    assert metrics.observed_cpu_s3_percent is None
    assert metrics.to_dict()["observed_cpu_s3_percent"] == "No disponible"

