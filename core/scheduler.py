"""Planificador concurrente basado en ThreadPoolExecutor con seguridad de hilos y circuit-breaker."""

from concurrent.futures import ThreadPoolExecutor, as_completed, Future
import datetime
import inspect
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from config.settings import RunConfig, TargetConfig
from core.http_client import SafeHttpClient
from models.request_result import RequestRecord, RequestStatus


class ConcurrentScheduler:
    """Orquestador de solicitudes HTTP concurrentes con protección de concurrencia y corte seguro."""

    def __init__(self, target_config: TargetConfig, run_config: RunConfig):
        self.target_config = target_config
        self.run_config = run_config

        # Sincronización y protección contra condiciones de carrera
        self._lock = threading.Lock()
        self._records: List[RequestRecord] = []
        self._completed_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._consecutive_failures = 0
        self._server_counts: Dict[str, int] = {"Servidor 1": 0, "Servidor 2": 0, "Servidor 3": 0}
        self._stop_requested = threading.Event()

    def run_scenario(
        self,
        repetition: int,
        progress_callback: Optional[Callable[..., None]] = None
    ) -> Tuple[List[RequestRecord], float, int]:
        """Ejecuta una corrida del escenario con concurrencia acotada a run_config.max_workers.
        
        Retorna: (records, global_duration_seconds, cancelled_count)
        """
        self._records.clear()
        self._completed_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._consecutive_failures = 0
        self._server_counts = {"Servidor 1": 0, "Servidor 2": 0, "Servidor 3": 0}
        self._stop_requested.clear()

        accepts_extended_progress = False
        if progress_callback is not None:
            try:
                sig = inspect.signature(progress_callback)
                accepts_extended_progress = len(sig.parameters) >= 12
            except (TypeError, ValueError):
                accepts_extended_progress = False

        client = SafeHttpClient(
            target_config=self.target_config,
            expected_text=self.run_config.expected_text,
            timeout=self.run_config.timeout_seconds,
            valid_server_messages=self.run_config.valid_server_messages
        )

        total = self.run_config.total_requests
        max_workers = self.run_config.max_workers
        futures: List[Future] = []

        # Marca de tiempo global de inicio
        global_start = time.perf_counter()
        last_progress_time = global_start

        try:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="LoadWorker") as executor:
                # Programar exactamente el número de solicitudes solicitado
                future_to_id = {
                    executor.submit(client.execute_request, req_id, self.run_config.scenario_name, repetition): req_id
                    for req_id in range(1, total + 1)
                }
                futures = list(future_to_id.keys())

                for future in as_completed(futures):
                    # Verificar si se activó el circuit breaker
                    if self._stop_requested.is_set():
                        continue

                    try:
                        record: RequestRecord = future.result()
                    except Exception as exc:
                        # Fallback defensivo si el futuro arrojó excepción no capturada
                        record = RequestRecord(
                            request_id=future_to_id[future],
                            scenario=self.run_config.scenario_name,
                            repetition=repetition,
                            timestamp_iso=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            duration_ms=0.0,
                            http_status=None,
                            status=RequestStatus.OTHER_ERROR,
                            error_detail=f"Excepción en hilo de ejecución: {str(exc)}"
                        )

                    with self._lock:
                        self._records.append(record)
                        self._completed_count += 1

                        if record.is_success:
                            self._success_count += 1
                            self._consecutive_failures = 0
                            if record.server_id in self._server_counts:
                                self._server_counts[record.server_id] += 1
                        else:
                            self._failure_count += 1
                            self._consecutive_failures += 1

                        # Circuit-breaker ante fallas consecutivas persistentes
                        if self._consecutive_failures >= self.run_config.max_consecutive_failures:
                            self._stop_requested.set()

                        completed_snap = self._completed_count
                        success_snap = self._success_count
                        failure_snap = self._failure_count
                        n1_snap = self._server_counts["Servidor 1"]
                        n2_snap = self._server_counts["Servidor 2"]
                        n3_snap = self._server_counts["Servidor 3"]

                    # Reporte de progreso periódico (controlado por tiempo y porcentaje para no saturar)
                    now = time.perf_counter()
                    if progress_callback and (now - last_progress_time >= 0.4 or completed_snap == total):
                        pct = (completed_snap / total) * 100.0
                        elapsed = now - global_start
                        if accepts_extended_progress:
                            progress_callback(
                                self.run_config.scenario_name,
                                max_workers,
                                total,
                                completed_snap,
                                success_snap,
                                failure_snap,
                                pct,
                                elapsed,
                                n1_snap,
                                n2_snap,
                                n3_snap,
                                self.target_config.target_url
                            )
                        else:
                            progress_callback(
                                self.run_config.scenario_name,
                                max_workers,
                                total,
                                completed_snap,
                                success_snap,
                                failure_snap,
                                pct,
                                elapsed
                            )
                        last_progress_time = now

                    if self._stop_requested.is_set():
                        # Cancelar futuros pendientes
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        break

        except KeyboardInterrupt:
            self._stop_requested.set()
            # Cancelar todas las tareas no iniciadas
            for f in futures:
                if not f.done():
                    f.cancel()
            print("\n[ALERTA] Interrupción por teclado (Ctrl+C). Esperando que finalicen los hilos activos...")
        finally:
            client.close()

        global_end = time.perf_counter()
        global_duration = global_end - global_start

        # Registrar peticiones canceladas si no alcanzaron a ejecutarse (conteo exacto y sin duplicados)
        cancelled_count = 0
        with self._lock:
            recorded_ids = {r.request_id for r in self._records}
            for req_id in range(1, total + 1):
                if req_id not in recorded_ids:
                    cancelled_count += 1
                    cancel_record = RequestRecord(
                        request_id=req_id,
                        scenario=self.run_config.scenario_name,
                        repetition=repetition,
                        timestamp_iso=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        duration_ms=0.0,
                        http_status=None,
                        status=RequestStatus.CANCELLED,
                        error_detail="Solicitud cancelada por detención anticipada o interrupción."
                    )
                    self._records.append(cancel_record)

            # Ordenar por request_id para consistencia
            self._records.sort(key=lambda r: r.request_id)
            final_records = list(self._records)

        return final_records, global_duration, cancelled_count

