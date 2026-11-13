"""Pruebas de exportación a CSV/JSON y generación de gráficas Matplotlib."""

from pathlib import Path
import pytest
from core.metrics_calculator import MetricsCalculator
from export.exporters import DataExporter
from export.visualizer import ChartGenerator
from models.request_result import RequestRecord, RequestStatus
from models.run_metrics import ScenarioSummary


@pytest.fixture
def temp_results_dir(tmp_path):
    d = tmp_path / "resultados_test"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_data_exporter(temp_results_dir):
    exporter = DataExporter(temp_results_dir)
    records = [
        RequestRecord(1, "Test", 1, "2026-11-11T00:00:00Z", 12.5, 200, RequestStatus.SUCCESS),
        RequestRecord(2, "Test", 1, "2026-11-11T00:00:01Z", 0.0, None, RequestStatus.TIMEOUT, "Timeout")
    ]
    metrics = MetricsCalculator.compute_run_metrics(
        run_id="run_exp_test",
        scenario_name="Test",
        repetition=1,
        max_workers=2,
        total_requested=2,
        records=records,
        global_duration_seconds=1.5,
        observed_cpu_percent=22.0
    )

    csv_file = exporter.export_run_detail_csv("run_exp_test", records)
    json_file = exporter.export_run_summary_json("run_exp_test", metrics)
    cons_file = exporter.append_to_consolidated_csv(metrics)

    assert csv_file.is_file()
    assert json_file.is_file()
    assert cons_file.is_file()

    # Comprobar contenido CSV
    content = csv_file.read_text(encoding="utf-8")
    assert "request_id,scenario" in content
    assert "SUCCESS" in content
    assert "TIMEOUT" in content


def test_chart_generator(temp_results_dir):
    visualizer = ChartGenerator(temp_results_dir)

    # Crear resúmenes sintéticos para verificar el renderizado de gráficos
    records_1 = [RequestRecord(i, "Escenario 1", 1, "2026-11-11T00:00:00Z", 15.0, 200, RequestStatus.SUCCESS) for i in range(1, 11)]
    m1 = MetricsCalculator.compute_run_metrics("r1", "Escenario 1", 1, 10, 10, records_1, 1.0, 10.0)
    s1 = ScenarioSummary("Escenario 1", 10, [m1])

    records_2 = [RequestRecord(i, "Escenario 2", 1, "2026-11-11T00:00:00Z", 25.0, 200, RequestStatus.SUCCESS) for i in range(1, 21)]
    m2 = MetricsCalculator.compute_run_metrics("r2", "Escenario 2", 1, 50, 20, records_2, 1.0, 45.0)
    s2 = ScenarioSummary("Escenario 2", 50, [m2])

    summaries = [s1, s2]

    p1 = visualizer.plot_throughput_vs_workers(summaries)
    p2 = visualizer.plot_p95_vs_workers(summaries)
    p3 = visualizer.plot_cpu_vs_workers(summaries)

    assert p1 is not None and p1.is_file()
    assert p2 is not None and p2.is_file()
    assert p3 is not None and p3.is_file()
    assert p1.stat().st_size > 0
    assert p2.stat().st_size > 0
    assert p3.stat().st_size > 0


def test_exporter_preserves_41_csv_and_loads_comparison(temp_results_dir):
    # Crear un consolidado estilo Práctica 4.1 sin columnas de 4.2
    csv_41 = temp_results_dir / "consolidado_corridas.csv"
    csv_41.write_text(
        "run_id,scenario,repetition,max_workers,total_requested,total_executed,success_count,failure_count,"
        "cancelled_count,failure_percentage,global_duration_s,latency_avg_ms,latency_min_ms,latency_max_ms,"
        "latency_p95_ms,successful_throughput_req_s,observed_cpu_percent\n"
        "20261111_fail,Escenario 3,1,100,5000,50,0,50,4950,100.0,1.0,No disponible,No disponible,No disponible,No disponible,0.0,No disponible\n"
        "20261111_ok,Escenario 3,1,100,5000,5000,5000,0,0,0.0,18.7,327.9,167.2,4723.7,924.3,266.4,No disponible\n",
        encoding="utf-8"
    )

    exporter = DataExporter(temp_results_dir)
    loaded_41 = exporter.load_consolidated_csv(csv_41)
    assert len(loaded_41) == 1
    assert loaded_41[0].max_workers == 100
    # Debe descartar la corrida abortada de 0 éxitos porque existe una válida
    assert loaded_41[0].total_runs == 1
    assert abs(loaded_41[0].avg_throughput - 266.4) < 1e-4

    # Al intentar escribir métricas 4.2 hacia consolidado_corridas.csv, debe redirigir a consolidado_corridas_alb.csv
    records = [
        RequestRecord(1, "Escenario 3", 1, "2026-11-12T00:00:00Z", 20.0, 200, RequestStatus.SUCCESS, "", "Servidor 1", "Bienvenidos al Servidor 1"),
        RequestRecord(2, "Escenario 3", 1, "2026-11-12T00:00:01Z", 22.0, 200, RequestStatus.SUCCESS, "", "Servidor 2", "Bienvenidos al Servidor 2"),
    ]
    m42 = MetricsCalculator.compute_run_metrics(
        run_id="r42", scenario_name="Escenario 3", repetition=1, max_workers=100,
        total_requested=2, records=records, global_duration_seconds=0.5,
        target_url="http://mi-alb.elb.amazonaws.com/",
        observed_cpu_s1_percent=15.0, observed_cpu_s2_percent=16.0, observed_cpu_s3_percent=14.0
    )
    out_csv = exporter.append_to_consolidated_csv(m42, filename="consolidado_corridas.csv")
    assert out_csv.name == "consolidado_corridas_alb.csv"
    assert "server_1_count" in out_csv.read_text(encoding="utf-8")
    assert "server_1_count" not in csv_41.read_text(encoding="utf-8")


def test_alb_comparative_charts(temp_results_dir):
    visualizer = ChartGenerator(temp_results_dir)
    recs_42 = [
        RequestRecord(1, "Escenario 1", 1, "2026-11-12T00:00:00Z", 15.0, 200, RequestStatus.SUCCESS, "", "Servidor 1", "Bienvenidos al Servidor 1"),
        RequestRecord(2, "Escenario 1", 1, "2026-11-12T00:00:01Z", 18.0, 200, RequestStatus.SUCCESS, "", "Servidor 2", "Bienvenidos al Servidor 2"),
        RequestRecord(3, "Escenario 1", 1, "2026-11-12T00:00:02Z", 19.0, 200, RequestStatus.SUCCESS, "", "Servidor 3", "Bienvenidos al Servidor 3"),
    ]
    m42 = MetricsCalculator.compute_run_metrics(
        "r42_1", "Escenario 1", 1, 10, 3, recs_42, 0.2,
        observed_cpu_s1_percent=10.0, observed_cpu_s2_percent=12.0, observed_cpu_s3_percent=11.0
    )
    s42 = [ScenarioSummary("Escenario 1", 10, [m42])]
    m41 = MetricsCalculator.compute_run_metrics("r41_1", "Escenario 1", 1, 10, 3, recs_42, 0.3)
    s41 = [ScenarioSummary("Escenario 1", 10, [m41])]

    c1 = visualizer.plot_throughput_comparison(s42, s41)
    c2 = visualizer.plot_p95_comparison(s42, s41)
    c3 = visualizer.plot_server_distribution_bars(s42)
    c4 = visualizer.plot_cpu_multi_server(s42)

    for chart in (c1, c2, c3, c4):
        assert chart is not None and chart.is_file() and chart.stat().st_size > 0

