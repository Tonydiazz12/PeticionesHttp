"""Pruebas de concurrencia, circuit-breaker y planificador con servidor HTTP local."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import itertools
import threading
import pytest

from config.settings import PresetScenarios, RunConfig, TargetConfig
from core.metrics_calculator import MetricsCalculator
from core.scheduler import ConcurrentScheduler
from models.request_result import RequestStatus


class MockHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Bienvenidos al Servidor 1")
        else:
            self.send_response(500)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def local_server():
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/"
    server.shutdown()


def test_scheduler_exact_requests_count(local_server):
    target_cfg = TargetConfig(target_url=local_server, allowed_hosts={"127.0.0.1"})
    run_cfg = RunConfig(
        scenario_name="TestScheduler",
        total_requests=25,
        max_workers=5,
        timeout_seconds=2.0
    )

    scheduler = ConcurrentScheduler(target_cfg, run_cfg)
    records, duration, cancelled = scheduler.run_scenario(repetition=1)

    assert len(records) == 25
    assert cancelled == 0
    assert all(r.status == RequestStatus.SUCCESS for r in records)
    assert duration > 0.0
    # Verificar que los IDs van de 1 a 25 exactamente una sola vez
    assert [r.request_id for r in records] == list(range(1, 26))


def test_scheduler_circuit_breaker():
    # Destino inexistente para forzar fallas consecutivas y verificar circuit breaker
    target_cfg = TargetConfig(target_url="http://127.0.0.1:59999/", allowed_hosts={"127.0.0.1"})
    run_cfg = RunConfig(
        scenario_name="CircuitBreakerTest",
        total_requests=50,
        max_workers=2,
        timeout_seconds=0.2,
        max_consecutive_failures=5  # Cortar tras 5 fallas
    )

    scheduler = ConcurrentScheduler(target_cfg, run_cfg)
    records, duration, cancelled = scheduler.run_scenario(repetition=1)

    # Deberían haberse registrado las 50 solicitudes (las ejecutadas con error y las restantes canceladas)
    assert len(records) == 50
    cancelled_records = [r for r in records if r.status == RequestStatus.CANCELLED]
    assert len(cancelled_records) > 0
    assert cancelled == len(cancelled_records)


def test_scheduler_alb_three_servers_and_fault_simulation():
    # Simulador local de ALB con 3 nodos sanos primero y luego caída del Servidor 3
    active_nodes = [1, 2, 3]
    cycle_iter = itertools.cycle(active_nodes)
    lock = threading.Lock()

    class MockALBHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock:
                srv_num = next(cycle_iter)
            body = f"Bienvenidos al Servidor {srv_num}".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    alb_server = HTTPServer(("127.0.0.1", 0), MockALBHandler)
    alb_port = alb_server.server_port
    t = threading.Thread(target=alb_server.serve_forever, daemon=True)
    t.start()

    try:
        alb_url = f"http://127.0.0.1:{alb_port}/"
        target_cfg = TargetConfig(alb_url=alb_url, allowed_hosts={"127.0.0.1"})

        # 1) Balanceo con 3 nodos activos
        run_cfg = RunConfig(scenario_name="ALB3", total_requests=30, max_workers=5, timeout_seconds=2.0)
        scheduler = ConcurrentScheduler(target_cfg, run_cfg)
        progress_snapshots = []

        def ext_cb(sc, wk, tot, comp, ok, fail, pct, elap, n1, n2, n3, url):
            progress_snapshots.append((comp, n1, n2, n3, url))

        records, duration, cancelled = scheduler.run_scenario(repetition=1, progress_callback=ext_cb)
        metrics = MetricsCalculator.compute_run_metrics("r_alb", "ALB3", 1, 5, 30, records, duration, target_url=alb_url)

        assert metrics.success_count == 30
        assert metrics.server_1_count > 0
        assert metrics.server_2_count > 0
        assert metrics.server_3_count > 0
        assert metrics.server_1_count + metrics.server_2_count + metrics.server_3_count == 30
        assert len(progress_snapshots) > 0
        assert progress_snapshots[-1][4] == alb_url

        # 2) Simulación de falla del Servidor 3 (solo responden Servidor 1 y Servidor 2 en 20 solicitudes)
        with lock:
            cycle_iter = itertools.cycle([1, 2])

        fault_cfg = PresetScenarios.fault_simulation()
        fault_scheduler = ConcurrentScheduler(target_cfg, fault_cfg)
        f_records, f_dur, _ = fault_scheduler.run_scenario(repetition=1)
        f_metrics = MetricsCalculator.compute_run_metrics("r_fault", fault_cfg.scenario_name, 1, 1, 20, f_records, f_dur)

        assert f_metrics.total_executed == 20
        assert f_metrics.success_count == 20
        assert f_metrics.server_1_count > 0
        assert f_metrics.server_2_count > 0
        assert f_metrics.server_3_count == 0
    finally:
        alb_server.shutdown()

