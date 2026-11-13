"""Aplicación principal CLI para pruebas de carga HTTP sobre AWS ALB + 3 instancias EC2.

Diseñado bajo buenas prácticas de ingeniería de software:
- Orientación a objetos y separación de responsabilidades.
- Validación estricta de destinos autorizados (DNS del ALB o entornos locales).
- Control seguro de concurrencia y circuit-breaker ante fallas.
- Identificación de respuestas de Servidor 1, Servidor 2 y Servidor 3.
- Comparación con resultados históricos de Práctica 4.1 sin inventar datos.
"""

import argparse
import datetime
import json
import logging
from pathlib import Path
import sys
import time
from typing import List, Optional, Set
from urllib.parse import urlparse

from config.settings import ConfigurationError, PresetScenarios, RunConfig, TargetConfig
from core.metrics_calculator import MetricsCalculator
from core.scheduler import ConcurrentScheduler
from export.exporters import DataExporter
from export.visualizer import ChartGenerator
from models.run_metrics import RunMetrics, ScenarioSummary


def setup_logging(output_dir: Path) -> logging.Logger:
    """Configura el sistema de registro dual hacia archivo de auditoría."""
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "ejecucion_pruebas.log"

    logger = logging.getLogger("LoadTestFramework")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


def print_progress(
    scenario: str,
    workers: int,
    total: int,
    completed: int,
    success: int,
    failures: int,
    progress_pct: float,
    elapsed_seconds: float,
    n1: int = 0,
    n2: int = 0,
    n3: int = 0,
    target_url: str = ""
) -> None:
    """Muestra el progreso periódico con distribución N1/N2/N3 en una sola línea."""
    bar_length = 20
    filled = int(round(bar_length * (progress_pct / 100.0)))
    bar = "=" * filled + "-" * (bar_length - filled)
    host = urlparse(target_url).hostname or target_url
    host_short = (host[:28] + "...") if len(host) > 31 else host
    dest_label = f"ALB:{host_short} | " if host_short else ""
    sys.stdout.write(
        f"\r[{dest_label}{scenario} | H:{workers}] [{bar}] {progress_pct:5.1f}% "
        f"({completed}/{total}) | OK:{success} Err:{failures} | S1:{n1} S2:{n2} S3:{n3} | {elapsed_seconds:5.1f}s"
    )
    sys.stdout.flush()


def _fmt_opt(val: Optional[float], suffix: str = "", decimals: int = 1) -> str:
    if val is None:
        return "No disponible"
    return f"{val:.{decimals}f}{suffix}"


def _prompt_cpu_observation(server_label: str, scenario_name: str, rep: int) -> Optional[float]:
    """Solicita manualmente el % de CPU observado con top/htop en una instancia EC2."""
    try:
        raw = input(
            f"  -> CPU máximo observado en {server_label} ({scenario_name} rep {rep}) "
            "[Enter para 'No disponible']: "
        ).strip()
        if not raw:
            return None
        val = float(raw.replace("%", "").strip())
        if not (0.0 <= val <= 100.0):
            print("     Valor fuera de rango [0-100]. Se registrará como 'No disponible'.")
            return None
        return val
    except ValueError:
        print("     Valor no numérico. Se registrará como 'No disponible'.")
        return None


def display_run_report(metrics: RunMetrics) -> None:
    """Presenta el informe técnico de una corrida en formato legible."""
    print("\n" + "=" * 78)
    print(f" REPORTE TÉCNICO DE CORRIDA: {metrics.scenario_name} (Repetición {metrics.repetition})")
    print(f" Identificador único : {metrics.run_id}")
    if metrics.target_url:
        print(f" Destino ALB         : {metrics.target_url}")
    print("=" * 78)
    print(f" Concurrencia máxima (Hilos)   : {metrics.max_workers}")
    print(f" Total de solicitudes pedidas  : {metrics.total_requested}")
    print(f" Total de solicitudes enviadas : {metrics.total_executed}")
    print(f" Respuestas exitosas (200 OK)  : {metrics.success_count}")
    print(f" Respuestas fallidas           : {metrics.failure_count} ({metrics.failure_percentage:.2f}%)")
    if metrics.cancelled_count > 0:
        print(f" Solicitudes canceladas        : {metrics.cancelled_count}")
    print(f" Tiempo global de ejecución    : {metrics.global_duration_seconds:.4f} segundos")
    print("-" * 78)

    if metrics.latency_avg_ms is not None:
        print(f" Latencia promedio (ms)        : {metrics.latency_avg_ms:.3f} ms")
        print(f" Latencia mínima (ms)          : {metrics.latency_min_ms:.3f} ms")
        print(f" Latencia máxima (ms)          : {metrics.latency_max_ms:.3f} ms")
        print(f" Percentil 95 (P95)            : {metrics.latency_p95_ms:.3f} ms")
    else:
        print(" Latencias y Percentil 95      : No disponible (0 peticiones exitosas)")

    print(f" Throughput exitoso            : {metrics.successful_throughput_req_s:.2f} req/s")
    print("-" * 78)
    print(" Distribución por Servidor (N1 + N2 + N3 = éxitos identificados):")
    print(f"   * Servidor 1 (N1)           : {metrics.server_1_count} ({metrics.server_1_pct:.2f}%)")
    print(f"   * Servidor 2 (N2)           : {metrics.server_2_count} ({metrics.server_2_pct:.2f}%)")
    print(f"   * Servidor 3 (N3)           : {metrics.server_3_count} ({metrics.server_3_pct:.2f}%)")
    print(f"   * Respuestas no identificadas: {metrics.unidentified_count}")
    print("-" * 78)
    print(" CPU máxima observada en EC2 (top/htop/CloudWatch):")
    print(f"   * CPU Servidor 1            : {_fmt_opt(metrics.observed_cpu_s1_percent, '%')}")
    print(f"   * CPU Servidor 2            : {_fmt_opt(metrics.observed_cpu_s2_percent, '%')}")
    print(f"   * CPU Servidor 3            : {_fmt_opt(metrics.observed_cpu_s3_percent, '%')}")

    if metrics.failure_breakdown:
        print("-" * 78)
        print(" Desglose de fallas detectadas:")
        for reason, count in metrics.failure_breakdown.items():
            print(f"   * {reason}: {count}")

    print("=" * 78 + "\n")


def display_scenario_comparison_table(summaries: List[ScenarioSummary]) -> None:
    """Despliega tabla por escenario con promedios, peores valores observados, CPU y N1/N2/N3."""
    valid = [s for s in summaries if s.runs]
    if not valid:
        return

    print("\n" + "=" * 124)
    print(" TABLA COMPARATIVA POR ESCENARIO - ALB + 3 INSTANCIAS EC2 (PROMEDIOS Y PEOR VALOR OBSERVADO)")
    print("=" * 124)
    header = (
        f"{'Escenario':<16} | {'H':<3} | {'T(s) Prom/Max':<14} | {'Éx/Fall Prom(MaxF)':<18} | "
        f"{'Lat/P95 Prom(MaxP95)':<22} | {'Thp Prom(Min)':<16} | {'Dist N1/N2/N3':<17} | {'CPU S1/S2/S3'}"
    )
    print(header)
    print("-" * 124)

    for s in valid:
        t_str = f"{s.avg_duration_s:.2f}/{s.max_duration_s:.2f}"
        ef_str = f"{s.avg_success_count:.0f}/{s.avg_failure_count:.1f}({s.max_failure_count})"
        lat_p95_str = (
            f"{s.avg_latency_ms:.1f}/{s.avg_p95_ms:.1f}({s.max_p95_ms:.1f})"
            if s.avg_p95_ms is not None and s.avg_latency_ms is not None and s.max_p95_ms is not None
            else "N/A"
        )
        thp_str = f"{s.avg_throughput:.1f}({s.min_throughput:.1f})"
        dist_str = f"{s.avg_n1:.0f}/{s.avg_n2:.0f}/{s.avg_n3:.0f}"
        cpu1 = f"{s.avg_cpu_s1:.0f}" if s.avg_cpu_s1 is not None else "N/A"
        cpu2 = f"{s.avg_cpu_s2:.0f}" if s.avg_cpu_s2 is not None else "N/A"
        cpu3 = f"{s.avg_cpu_s3:.0f}" if s.avg_cpu_s3 is not None else "N/A"
        cpu_str = f"{cpu1}/{cpu2}/{cpu3}%"

        print(
            f"{s.scenario_name:<16} | {s.max_workers:<3} | {t_str:<14} | {ef_str:<18} | "
            f"{lat_p95_str:<22} | {thp_str:<16} | {dist_str:<17} | {cpu_str}"
        )

    print("=" * 124)
    print("Nota: Hilos indica concurrencia máxima, NO req/s. El reparto del ALB no garantiza 33.3% exacto por nodo.\n")


def display_41_vs_42_comparison(summaries_41: List[ScenarioSummary], summaries_42: List[ScenarioSummary]) -> None:
    """Compara lado a lado métricas de Práctica 4.1 (1 EC2) contra Práctica 4.2 (ALB + 3 EC2)."""
    if not summaries_41 or not summaries_42:
        return

    map_41 = {s.max_workers: s for s in summaries_41 if s.runs}
    map_42 = {s.max_workers: s for s in summaries_42 if s.runs}
    all_workers = sorted(set(map_41.keys()) | set(map_42.keys()))

    print("\n" + "=" * 102)
    print(" COMPARATIVA DIRECTA: PRÁCTICA 4.1 (1 EC2) vs PRÁCTICA 4.2 (ALB + 3 EC2)")
    print("=" * 102)
    print(
        f"{'Hilos':<6} | {'Escenario':<15} | {'Thp 4.1 (req/s)':<16} | {'Thp 4.2 (req/s)':<16} | "
        f"{'P95 4.1 (ms)':<14} | {'P95 4.2 (ms)':<14}"
    )
    print("-" * 102)

    for w in all_workers:
        s41 = map_41.get(w)
        s42 = map_42.get(w)
        name = (s42.scenario_name if s42 else s41.scenario_name) if (s42 or s41) else "-"
        thp41 = f"{s41.avg_throughput:.2f}" if s41 else "No disponible"
        thp42 = f"{s42.avg_throughput:.2f}" if s42 else "No disponible"
        p95_41 = f"{s41.avg_p95_ms:.2f}" if (s41 and s41.avg_p95_ms is not None) else "No disponible"
        p95_42 = f"{s42.avg_p95_ms:.2f}" if (s42 and s42.avg_p95_ms is not None) else "No disponible"
        print(f"{w:<6} | {name:<15} | {thp41:<16} | {thp42:<16} | {p95_41:<14} | {p95_42:<14}")

    print("=" * 102)
    print("Nota: Las diferencias observadas entre 4.1 y 4.2 no prueban causalidad por sí solas (condiciones de red pueden variar).\n")


def execute_scenario_suite(
    target_config: TargetConfig,
    run_config: RunConfig,
    exporter: DataExporter,
    logger: logging.Logger,
    ask_cpu: bool = True,
    consolidated_filename: str = "consolidado_corridas_alb.csv"
) -> ScenarioSummary:
    """Ejecuta las repeticiones de un escenario específico, recolectando métricas y archivos."""
    summary = ScenarioSummary(scenario_name=run_config.scenario_name, max_workers=run_config.max_workers)
    scheduler = ConcurrentScheduler(target_config, run_config)

    for rep in range(1, run_config.repetitions + 1):
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_name = run_config.scenario_name.lower().replace(" ", "_")
        run_id = f"{timestamp_str}_{sanitized_name}_rep{rep}"

        print(f"\n>>> Iniciando {run_config.scenario_name} - Repetición {rep}/{run_config.repetitions}")
        print(f"    Destino ALB: {target_config.target_url} | Hilos: {run_config.max_workers} | Solicitudes: {run_config.total_requests}")
        logger.info(
            f"Iniciando corrida {run_id} | Destino={target_config.target_url} | "
            f"Hilos={run_config.max_workers} | Reqs={run_config.total_requests} | Timeout={run_config.timeout_seconds}s"
        )

        records, global_duration, cancelled_count = scheduler.run_scenario(
            repetition=rep,
            progress_callback=print_progress
        )
        print()  # Salto de línea tras barra de progreso

        cpu_s1: Optional[float] = None
        cpu_s2: Optional[float] = None
        cpu_s3: Optional[float] = None
        if ask_cpu:
            print("Registro manual de CPU máximo observado en EC2 (top/htop/CloudWatch con ventana de 60s):")
            cpu_s1 = _prompt_cpu_observation("Servidor 1", run_config.scenario_name, rep)
            cpu_s2 = _prompt_cpu_observation("Servidor 2", run_config.scenario_name, rep)
            cpu_s3 = _prompt_cpu_observation("Servidor 3", run_config.scenario_name, rep)

        metrics = MetricsCalculator.compute_run_metrics(
            run_id=run_id,
            scenario_name=run_config.scenario_name,
            repetition=rep,
            max_workers=run_config.max_workers,
            total_requested=run_config.total_requests,
            records=records,
            global_duration_seconds=global_duration,
            cancelled_count=cancelled_count,
            target_url=target_config.target_url,
            observed_cpu_s1_percent=cpu_s1,
            observed_cpu_s2_percent=cpu_s2,
            observed_cpu_s3_percent=cpu_s3
        )

        display_run_report(metrics)
        logger.info(
            f"Completada {run_id}: Éxitos={metrics.success_count}, Fallas={metrics.failure_count}, "
            f"N1={metrics.server_1_count}, N2={metrics.server_2_count}, N3={metrics.server_3_count}, "
            f"NoIdentificadas={metrics.unidentified_count}, "
            f"Throughput={metrics.successful_throughput_req_s:.2f} req/s, "
            f"P95={metrics.latency_p95_ms} ms"
        )

        exporter.export_run_detail_csv(run_id, records)
        exporter.export_run_summary_json(run_id, metrics)
        exporter.append_to_consolidated_csv(metrics, filename=consolidated_filename)

        summary.runs.append(metrics)

        if rep < run_config.repetitions and run_config.pause_between_runs_seconds > 0:
            print(f"Pausa de enfriamiento ({run_config.pause_between_runs_seconds:.1f}s) antes de la siguiente corrida...")
            time.sleep(run_config.pause_between_runs_seconds)

    return summary


def _normalize_target_url(raw_url: str) -> str:
    cleaned = raw_url.strip()
    if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
        cleaned = f"http://{cleaned}"
    parsed = urlparse(cleaned)
    if not parsed.path:
        cleaned = f"{cleaned}/"
    return cleaned


def load_target_from_args_or_prompt(cli_alb_url: Optional[str], config_path: Optional[str]) -> TargetConfig:
    """Obtiene y valida la configuración del destino ALB por archivo, CLI o entrada interactiva."""
    allowed_hosts: Set[str] = {"127.0.0.1", "localhost"}
    raw_url = cli_alb_url or ""

    if config_path:
        cfg_file = Path(config_path)
        if not cfg_file.is_file():
            print(f"[ERROR] Archivo de configuración no encontrado: {cfg_file}")
            sys.exit(1)
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        raw_url = data.get("alb_url") or data.get("target_url") or raw_url
        for h in data.get("allowed_hosts", []):
            if str(h).strip():
                allowed_hosts.add(str(h).strip().lower())

    if not raw_url:
        print("\n--- CONFIGURACIÓN DE DESTINO AUTORIZADO (AWS ALB) ---")
        print("Por seguridad, el generador solo enviará solicitudes al DNS del ALB o entorno local autorizado.")
        raw_url = input(
            "Ingresa el DNS público de tu ALB (ej. http://mi-alb-123.us-east-1.elb.amazonaws.com/): "
        ).strip()

    target_url = _normalize_target_url(raw_url)
    parsed = urlparse(target_url)
    hostname = (parsed.hostname or "").lower()

    if hostname:
        allowed_hosts.add(hostname)

    print(f"\nURL destino : {target_url}")
    print(f"Host ALB    : {hostname}")
    print(f"Lista blanca: {sorted(allowed_hosts)}")
    confirm = input(f"¿Confirmas autorizar EXCLUSIVAMENTE peticiones a '{target_url}'? (s/n): ").strip().lower()
    if confirm not in ("s", "si", "y", "yes"):
        print("Operación cancelada por el usuario. Saliendo...")
        sys.exit(0)

    try:
        return TargetConfig(target_url=target_url, allowed_hosts=allowed_hosts)
    except ConfigurationError as exc:
        print(f"\n[ERROR DE CONFIGURACIÓN] {exc}")
        sys.exit(1)


def _generate_all_reports_and_charts(
    exporter: DataExporter,
    visualizer: ChartGenerator,
    summaries_42: List[ScenarioSummary],
    results_dir: Path
) -> None:
    """Carga histórico 4.1 si existe, imprime tablas comparativas y genera gráficos PNG."""
    active_42 = summaries_42 or exporter.load_consolidated_csv(results_dir / "consolidado_corridas_alb.csv")
    if not active_42:
        print("\n[AVISO] No hay corridas de Práctica 4.2 registradas todavía para comparar o graficar.")
        return

    summaries_41 = exporter.load_consolidated_csv(results_dir / "consolidado_corridas.csv")

    display_scenario_comparison_table(active_42)
    if summaries_41:
        display_41_vs_42_comparison(summaries_41, active_42)
    else:
        print("[AVISO] No se encontró 'consolidado_corridas.csv' de Práctica 4.1; se generarán solo gráficas de 4.2.")

    print("Generando gráficas PNG...")
    outputs = [
        ("Throughput 4.1 vs 4.2", visualizer.plot_throughput_comparison(active_42, summaries_41 or None)),
        ("P95 4.1 vs 4.2", visualizer.plot_p95_comparison(active_42, summaries_41 or None)),
        ("Distribución N1/N2/N3", visualizer.plot_server_distribution_bars(active_42)),
        ("CPU 3 EC2", visualizer.plot_cpu_multi_server(active_42)),
    ]
    for label, path in outputs:
        if path:
            print(f" -> {label}: {path}")
        elif label == "CPU 3 EC2":
            print(" -> CPU 3 EC2: Omitida por no contar con mediciones numéricas de CPU suficientes.")


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generador de Carga HTTP para AWS ALB + 3 EC2 (Práctica 4.2)")
    parser.add_argument("--alb-url", default=None, help="URL HTTP del ALB (ej. http://mi-alb.elb.amazonaws.com/)")
    parser.add_argument("--config", default=None, help="Ruta a archivo JSON con alb_url y allowed_hosts")
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout por petición en segundos (default: 5.0)")
    parser.add_argument("--results-dir", default="resultados", help="Carpeta de resultados (default: resultados)")
    return parser.parse_args()


def main():
    args = parse_cli_args()

    print("=" * 74)
    print(" GENERADOR DE CARGA HTTP - ESCALAMIENTO CON AWS ALB + 3 EC2 (PRÁCTICA 4.2)")
    print(" Desarrollado para Windows / VS Code con Arquitectura Concurrente OOP")
    print("=" * 74)

    target_config = load_target_from_args_or_prompt(args.alb_url, args.config)

    results_dir = Path(args.results_dir)
    logger = setup_logging(results_dir)
    exporter = DataExporter(results_dir)
    visualizer = ChartGenerator(results_dir)

    all_summaries: List[ScenarioSummary] = []

    while True:
        print("\n" + "=" * 58)
        print(" MENÚ DE ESCENARIOS DE PRUEBA (ALB + 3 EC2)")
        print("=" * 58)
        print(" 0. Línea Base (20 solicitudes, 1 hilo, 1 corrida)")
        print(" 1. Escenario 1 (100 solicitudes, 10 hilos, 3 corridas)")
        print(" 2. Escenario 2 (1,000 solicitudes, 50 hilos, 3 corridas)")
        print(" 3. Escenario 3 (5,000 solicitudes, 100 hilos, 3 corridas)")
        print(" 4. BATERÍA COMPLETA (Línea Base + Escenarios 1, 2 y 3 = 10 corridas)")
        print(" 5. Simulación de Falla / Resiliencia (20 solicitudes, 1 hilo)")
        print(" 6. Comparar con Práctica 4.1 y Generar Gráficas PNG")
        print(" 7. Escenario Personalizado (máximo 5000 solicitudes, 100 hilos)")
        print(" 8. Salir")
        print("-" * 58)

        choice = input("Selecciona una opción [0-8]: ").strip()

        if choice == "8":
            print("\nFinalizando aplicación. ¡Hasta pronto!")
            break

        selected_configs: List[RunConfig] = []

        if choice == "0":
            cfg = PresetScenarios.baseline()
            cfg.timeout_seconds = args.timeout
            cfg.results_dir = results_dir
            selected_configs.append(cfg)
        elif choice == "1":
            cfg = PresetScenarios.scenario_1()
            cfg.timeout_seconds = args.timeout
            cfg.results_dir = results_dir
            selected_configs.append(cfg)
        elif choice == "2":
            cfg = PresetScenarios.scenario_2()
            cfg.timeout_seconds = args.timeout
            cfg.results_dir = results_dir
            selected_configs.append(cfg)
        elif choice == "3":
            cfg = PresetScenarios.scenario_3()
            cfg.timeout_seconds = args.timeout
            cfg.results_dir = results_dir
            selected_configs.append(cfg)
        elif choice == "4":
            print("\n>>> Has seleccionado la Batería Completa (10 corridas secuenciales).")
            for cfg in (
                PresetScenarios.baseline(),
                PresetScenarios.scenario_1(),
                PresetScenarios.scenario_2(),
                PresetScenarios.scenario_3(),
            ):
                cfg.timeout_seconds = args.timeout
                cfg.results_dir = results_dir
                selected_configs.append(cfg)
        elif choice == "5":
            print("\n>>> Simulación de Falla: 20 solicitudes para observar qué servidores sanos responden.")
            cfg = PresetScenarios.fault_simulation()
            cfg.timeout_seconds = args.timeout
            cfg.results_dir = results_dir
            selected_configs.append(cfg)
        elif choice == "6":
            _generate_all_reports_and_charts(exporter, visualizer, all_summaries, results_dir)
            continue
        elif choice == "7":
            try:
                name = input("Nombre del escenario [Personalizado]: ").strip() or "Personalizado"
                reqs = int(input("Total de solicitudes (máx 5000): ").strip())
                workers = int(input("Número de hilos (máx 100): ").strip())
                reps = int(input("Número de repeticiones (ej. 3): ").strip() or "1")
                pause = float(input("Pausa entre corridas en segundos (ej. 3.0): ").strip() or "3.0")
                timeout_in = float(input(f"Timeout en segundos [{args.timeout}]: ").strip() or str(args.timeout))
                cfg = RunConfig(
                    scenario_name=name,
                    total_requests=reqs,
                    max_workers=workers,
                    timeout_seconds=timeout_in,
                    repetitions=reps,
                    pause_between_runs_seconds=pause,
                    results_dir=results_dir
                )
                selected_configs.append(cfg)
            except (ValueError, ConfigurationError) as exc:
                print(f"\n[ERROR] Parámetros no válidos: {exc}")
                continue
        else:
            print("Opción inválida. Intenta nuevamente.")
            continue

        print("\n" + "=" * 68)
        print(" CONFIRMACIÓN PREVIA AL ENVÍO DE SOLICITUDES")
        print("=" * 68)
        print(f" URL de destino ALB : {target_config.target_url}")
        print(f" Timeout / Carpeta  : {selected_configs[0].timeout_seconds}s | {results_dir}")
        for c in selected_configs:
            total_envios = c.total_requests * c.repetitions
            print(
                f" -> {c.scenario_name}: {c.total_requests} reqs x {c.repetitions} reps = {total_envios} "
                f"solicitudes | Máx hilos: {c.max_workers} | Pausa: {c.pause_between_runs_seconds}s"
            )
        print(" RECORDATORIO: El número de hilos indica la concurrencia y NO las req/s.")
        print("=" * 68)

        start_confirm = input("¿Deseas iniciar la ejecución ahora? (s/n): ").strip().lower()
        if start_confirm not in ("s", "si", "y", "yes"):
            print("Ejecución cancelada por el usuario.")
            continue

        for cfg in selected_configs:
            summary = execute_scenario_suite(target_config, cfg, exporter, logger, ask_cpu=True)
            all_summaries.append(summary)

        _generate_all_reports_and_charts(exporter, visualizer, all_summaries, results_dir)


if __name__ == "__main__":
    main()
