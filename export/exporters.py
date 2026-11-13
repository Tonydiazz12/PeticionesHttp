"""Exportador de resultados a formatos CSV, JSON y archivo de registro unificado."""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from models.request_result import RequestRecord
from models.run_metrics import RunMetrics, ScenarioSummary


class DataExporter:
    """Administrador de persistencia de datos de pruebas en disco."""

    def __init__(self, output_dir: Path = Path("resultados")):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_run_detail_csv(self, run_id: str, records: List[RequestRecord]) -> Path:
        """Guarda el registro individual de cada petición enviada en un archivo CSV."""
        filepath = self.output_dir / f"{run_id}_detalle.csv"
        fieldnames = [
            "request_id",
            "scenario",
            "repetition",
            "timestamp_iso",
            "duration_ms",
            "http_status",
            "status",
            "server_id",
            "response_body",
            "error_detail"
        ]

        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for rec in records:
                writer.writerow(rec.to_dict())

        return filepath

    def export_run_summary_json(self, run_id: str, metrics: RunMetrics) -> Path:
        """Guarda el resumen de métricas de una corrida en formato JSON estructurado."""
        filepath = self.output_dir / f"{run_id}_resumen.json"
        with open(filepath, mode="w", encoding="utf-8") as f:
            json.dump(metrics.to_dict(), f, indent=4, ensure_ascii=False)
        return filepath

    def append_to_consolidated_csv(self, metrics: RunMetrics, filename: str = "consolidado_corridas.csv") -> Path:
        """Agrega de manera incremental la fila de una corrida al archivo consolidado CSV."""
        filepath = self.output_dir / filename
        if filepath.is_file():
            with open(filepath, mode="r", encoding="utf-8") as existing_f:
                header_line = existing_f.readline()
            if "server_1_count" not in header_line:
                filepath = self.output_dir / "consolidado_corridas_alb.csv"

        file_exists = filepath.is_file()

        fieldnames = [
            "run_id",
            "target_url",
            "scenario",
            "repetition",
            "max_workers",
            "total_requested",
            "total_executed",
            "success_count",
            "failure_count",
            "cancelled_count",
            "failure_percentage",
            "global_duration_s",
            "latency_avg_ms",
            "latency_min_ms",
            "latency_max_ms",
            "latency_p95_ms",
            "successful_throughput_req_s",
            "server_1_count",
            "server_2_count",
            "server_3_count",
            "unidentified_count",
            "server_1_pct",
            "server_2_pct",
            "server_3_pct",
            "observed_cpu_percent",
            "observed_cpu_s1_percent",
            "observed_cpu_s2_percent",
            "observed_cpu_s3_percent"
        ]

        data = metrics.to_dict()
        row = {k: data[k] for k in fieldnames}

        with open(filepath, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

        return filepath

    @staticmethod
    def _parse_optional_float(raw: Optional[str]) -> Optional[float]:
        if raw is None:
            return None
        cleaned = raw.strip()
        if not cleaned or cleaned.lower() in ("no disponible", "n/a", "none"):
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _parse_int(raw: Optional[str], default: int = 0) -> int:
        if raw is None:
            return default
        try:
            return int(float(raw.strip()))
        except ValueError:
            return default

    def load_consolidated_csv(self, csv_path: Optional[Path] = None) -> List[ScenarioSummary]:
        """Carga métricas desde un CSV consolidado (ej. Práctica 4.1) para análisis comparativo."""
        target_path = Path(csv_path) if csv_path is not None else (self.output_dir / "consolidado_corridas.csv")
        if not target_path.is_file():
            return []

        grouped_runs: Dict[Tuple[str, int], List[RunMetrics]] = {}

        with open(target_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                scenario = (row.get("scenario") or "").strip()
                if not scenario:
                    continue
                max_workers = self._parse_int(row.get("max_workers"))
                success_count = self._parse_int(row.get("success_count"))
                failure_count = self._parse_int(row.get("failure_count"))
                total_requested = self._parse_int(row.get("total_requested"))
                total_executed = self._parse_int(row.get("total_executed"))
                cancelled_count = self._parse_int(row.get("cancelled_count"))
                repetition = self._parse_int(row.get("repetition"), default=1)

                metrics = RunMetrics(
                    run_id=(row.get("run_id") or "").strip(),
                    scenario_name=scenario,
                    repetition=repetition,
                    max_workers=max_workers,
                    total_requested=total_requested,
                    total_executed=total_executed,
                    success_count=success_count,
                    failure_count=failure_count,
                    failure_percentage=self._parse_optional_float(row.get("failure_percentage")) or 0.0,
                    global_duration_seconds=self._parse_optional_float(row.get("global_duration_s")) or 0.0,
                    latency_avg_ms=self._parse_optional_float(row.get("latency_avg_ms")),
                    latency_min_ms=self._parse_optional_float(row.get("latency_min_ms")),
                    latency_max_ms=self._parse_optional_float(row.get("latency_max_ms")),
                    latency_p95_ms=self._parse_optional_float(row.get("latency_p95_ms")),
                    successful_throughput_req_s=self._parse_optional_float(row.get("successful_throughput_req_s")) or 0.0,
                    observed_cpu_percent=self._parse_optional_float(row.get("observed_cpu_percent")),
                    cancelled_count=cancelled_count,
                    target_url=(row.get("target_url") or "").strip(),
                    server_1_count=self._parse_int(row.get("server_1_count")),
                    server_2_count=self._parse_int(row.get("server_2_count")),
                    server_3_count=self._parse_int(row.get("server_3_count")),
                    unidentified_count=self._parse_int(row.get("unidentified_count")),
                    server_1_pct=self._parse_optional_float(row.get("server_1_pct")) or 0.0,
                    server_2_pct=self._parse_optional_float(row.get("server_2_pct")) or 0.0,
                    server_3_pct=self._parse_optional_float(row.get("server_3_pct")) or 0.0,
                    observed_cpu_s1_percent=self._parse_optional_float(row.get("observed_cpu_s1_percent")),
                    observed_cpu_s2_percent=self._parse_optional_float(row.get("observed_cpu_s2_percent")),
                    observed_cpu_s3_percent=self._parse_optional_float(row.get("observed_cpu_s3_percent")),
                )

                key = (scenario, max_workers)
                grouped_runs.setdefault(key, []).append(metrics)

        summaries: List[ScenarioSummary] = []
        for (scenario, max_workers), runs in grouped_runs.items():
            successful_runs = [r for r in runs if r.success_count > 0]
            selected_runs = successful_runs if successful_runs else runs
            limit = 1 if max_workers == 1 and "base" in scenario.lower() else 3
            if len(selected_runs) > limit:
                selected_runs = selected_runs[-limit:]
            summaries.append(ScenarioSummary(scenario_name=scenario, max_workers=max_workers, runs=selected_runs))

        summaries.sort(key=lambda s: s.max_workers)
        return summaries

