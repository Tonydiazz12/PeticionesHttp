"""Generación de gráficas de rendimiento comparativo con Matplotlib."""

from pathlib import Path
from typing import List, Optional
import matplotlib
# Configurar backend no interactivo para asegurar compatibilidad en Windows y entornos de ejecución automatizados
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from models.run_metrics import ScenarioSummary


class ChartGenerator:
    """Generador de gráficos estadísticos con anotaciones técnicas rigurosas."""

    def __init__(self, output_dir: Path = Path("resultados")):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_throughput_vs_workers(self, summaries: List[ScenarioSummary], filename: str = "grafica_throughput_vs_hilos.png") -> Optional[Path]:
        """Genera gráfica de Hilos de Concurrencia vs Throughput Exitoso Promedio (req/s)."""
        valid_summaries = [s for s in summaries if s.runs]
        if not valid_summaries:
            return None

        # Ordenar por número de hilos
        sorted_s = sorted(valid_summaries, key=lambda s: s.max_workers)
        workers = [s.max_workers for s in sorted_s]
        avg_tps = [s.avg_throughput for s in sorted_s]
        max_tps = [s.max_throughput for s in sorted_s]

        fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
        ax.plot(workers, avg_tps, marker="o", color="#1f77b4", linewidth=2, label="Throughput Promedio (req/s)")
        ax.plot(workers, max_tps, marker="s", linestyle="--", color="#aec7e8", label="Throughput Máximo Observado (req/s)")

        for x, y in zip(workers, avg_tps):
            ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9, fontweight="bold")

        ax.set_title("Concurrencia vs Throughput Exitoso en Servidor HTTP EC2 / ALB", fontsize=12, pad=12)
        ax.set_xlabel("Número Máximo de Hilos Concurrentes (Workers)", fontsize=10)
        ax.set_ylabel("Throughput Exitoso (solicitudes HTTP 200 / segundo)", fontsize=10)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="upper left")

        plt.figtext(
            0.5, -0.02,
            "Nota: Mediciones obtenidas empíricamente en el entorno de pruebas. No son estimaciones teóricas.",
            wrap=True, horizontalalignment="center", fontsize=8, fontstyle="italic", color="#555555"
        )

        output_path = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    def plot_p95_vs_workers(self, summaries: List[ScenarioSummary], filename: str = "grafica_p95_vs_hilos.png") -> Optional[Path]:
        """Genera gráfica de Hilos de Concurrencia vs Latencia P95 Promedio (ms)."""
        valid_summaries = [s for s in summaries if s.avg_p95_ms is not None]
        if not valid_summaries:
            return None

        sorted_s = sorted(valid_summaries, key=lambda s: s.max_workers)
        workers = [s.max_workers for s in sorted_s]
        avg_p95 = [s.avg_p95_ms for s in sorted_s]
        max_p95 = [s.max_p95_ms for s in sorted_s]

        fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
        ax.plot(workers, avg_p95, marker="D", color="#d62728", linewidth=2, label="Latencia P95 Promedio (ms)")
        ax.plot(workers, max_p95, marker="^", linestyle="--", color="#ff9896", label="Latencia P95 Máxima Observada (ms)")

        for x, y in zip(workers, avg_p95):
            ax.annotate(f"{y:.1f} ms", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9, fontweight="bold")

        ax.set_title("Concurrencia vs Latencia Percentil 95 (P95) en Servidor HTTP EC2 / ALB", fontsize=12, pad=12)
        ax.set_xlabel("Número Máximo de Hilos Concurrentes (Workers)", fontsize=10)
        ax.set_ylabel("Latencia P95 de Peticiones Exitosas (milisegundos)", fontsize=10)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="upper left")

        plt.figtext(
            0.5, -0.02,
            "Nota: P95 calculado por interpolación lineal estandarizada sobre respuestas exitosas verificadas.",
            wrap=True, horizontalalignment="center", fontsize=8, fontstyle="italic", color="#555555"
        )

        output_path = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    def plot_cpu_vs_workers(self, summaries: List[ScenarioSummary], filename: str = "grafica_cpu_vs_hilos.png") -> Optional[Path]:
        """Genera gráfica de Hilos de Concurrencia vs Carga de CPU en EC2 (%) solo con datos suficientes."""
        valid_summaries = [s for s in summaries if s.avg_cpu_percent is not None]
        if not valid_summaries:
            return None

        sorted_s = sorted(valid_summaries, key=lambda s: s.max_workers)
        workers = [s.max_workers for s in sorted_s]
        avg_cpu = [s.avg_cpu_percent for s in sorted_s]
        max_cpu = [s.max_cpu_percent for s in sorted_s]

        fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
        ax.plot(workers, avg_cpu, marker="o", color="#2ca02c", linewidth=2, label="CPU Promedio Observada en EC2 (%)")
        ax.plot(workers, max_cpu, marker="v", linestyle="--", color="#98df8a", label="CPU Máxima Observada en EC2 (%)")

        for x, y in zip(workers, avg_cpu):
            ax.annotate(f"{y:.1f}%", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9, fontweight="bold")

        ax.set_title("Concurrencia vs Uso de CPU en Instancia EC2", fontsize=12, pad=12)
        ax.set_xlabel("Número Máximo de Hilos Concurrentes (Workers)", fontsize=10)
        ax.set_ylabel("Carga de CPU en EC2 (%)", fontsize=10)
        ax.set_ylim(0, 105)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="upper left")

        plt.figtext(
            0.5, -0.02,
            "Nota: Valores recolectados mediante observación directa en EC2 (top/htop/CloudWatch). No simulados.",
            wrap=True, horizontalalignment="center", fontsize=8, fontstyle="italic", color="#555555"
        )

        output_path = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    def plot_throughput_comparison(
        self,
        summaries_42: List[ScenarioSummary],
        summaries_41: Optional[List[ScenarioSummary]] = None,
        filename: str = "grafica_throughput_comparativa_41_42.png"
    ) -> Optional[Path]:
        """Compara Hilos vs Throughput Promedio entre Práctica 4.1 (1 EC2) y Práctica 4.2 (ALB + 3 EC2)."""
        valid_42 = sorted([s for s in summaries_42 if s.runs], key=lambda s: s.max_workers)
        if not valid_42:
            return None

        fig, ax = plt.subplots(figsize=(8.5, 5), dpi=150)

        w42 = [s.max_workers for s in valid_42]
        t42 = [s.avg_throughput for s in valid_42]
        ax.plot(w42, t42, marker="o", color="#1f77b4", linewidth=2.2, label="4.2 ALB + 3 EC2 (req/s)")
        for x, y in zip(w42, t42):
            ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8.5, fontweight="bold")

        if summaries_41:
            valid_41 = sorted([s for s in summaries_41 if s.runs], key=lambda s: s.max_workers)
            if valid_41:
                w41 = [s.max_workers for s in valid_41]
                t41 = [s.avg_throughput for s in valid_41]
                ax.plot(w41, t41, marker="s", linestyle="--", color="#ff7f0e", linewidth=2, label="4.1 1 EC2 Directa (req/s)")
                for x, y in zip(w41, t41):
                    ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=8, color="#b35900")

        ax.set_title("Concurrencia vs Throughput Promedio: 1 EC2 (4.1) vs ALB + 3 EC2 (4.2)", fontsize=11.5, pad=12)
        ax.set_xlabel("Número Máximo de Hilos Concurrentes (Workers)", fontsize=10)
        ax.set_ylabel("Throughput Exitoso Promedio (req/s)", fontsize=10)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="upper left")

        plt.figtext(
            0.5, -0.02,
            "Nota: Mediciones obtenidas empíricamente. Las diferencias entre corridas no prueban causalidad por sí solas (red/instancia pueden variar).",
            wrap=True, horizontalalignment="center", fontsize=8, fontstyle="italic", color="#555555"
        )

        output_path = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    def plot_p95_comparison(
        self,
        summaries_42: List[ScenarioSummary],
        summaries_41: Optional[List[ScenarioSummary]] = None,
        filename: str = "grafica_p95_comparativa_41_42.png"
    ) -> Optional[Path]:
        """Compara Hilos vs Latencia P95 Promedio entre Práctica 4.1 (1 EC2) y Práctica 4.2 (ALB + 3 EC2)."""
        valid_42 = sorted([s for s in summaries_42 if s.avg_p95_ms is not None], key=lambda s: s.max_workers)
        if not valid_42:
            return None

        fig, ax = plt.subplots(figsize=(8.5, 5), dpi=150)

        w42 = [s.max_workers for s in valid_42]
        p42 = [s.avg_p95_ms for s in valid_42]
        ax.plot(w42, p42, marker="D", color="#d62728", linewidth=2.2, label="4.2 ALB + 3 EC2 P95 (ms)")
        for x, y in zip(w42, p42):
            ax.annotate(f"{y:.1f} ms", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8.5, fontweight="bold")

        if summaries_41:
            valid_41 = sorted([s for s in summaries_41 if s.avg_p95_ms is not None], key=lambda s: s.max_workers)
            if valid_41:
                w41 = [s.max_workers for s in valid_41]
                p41 = [s.avg_p95_ms for s in valid_41]
                ax.plot(w41, p41, marker="^", linestyle="--", color="#9467bd", linewidth=2, label="4.1 1 EC2 Directa P95 (ms)")
                for x, y in zip(w41, p41):
                    ax.annotate(f"{y:.1f} ms", (x, y), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=8, color="#5c3d7a")

        ax.set_title("Concurrencia vs Latencia P95 Promedio: 1 EC2 (4.1) vs ALB + 3 EC2 (4.2)", fontsize=11.5, pad=12)
        ax.set_xlabel("Número Máximo de Hilos Concurrentes (Workers)", fontsize=10)
        ax.set_ylabel("Latencia Percentil 95 Promedio (ms)", fontsize=10)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="upper left")

        plt.figtext(
            0.5, -0.02,
            "Nota: Mediciones obtenidas por interpolación lineal (Hyndman & Fan R-7). Las variaciones observadas no prueban causalidad por sí solas.",
            wrap=True, horizontalalignment="center", fontsize=8, fontstyle="italic", color="#555555"
        )

        output_path = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    def plot_server_distribution_bars(
        self,
        summaries_42: List[ScenarioSummary],
        filename: str = "grafica_distribucion_servidores_alb.png"
    ) -> Optional[Path]:
        """Genera gráfico de barras agrupadas de distribución promedio (N1, N2, N3) por escenario."""
        valid = [s for s in summaries_42 if s.runs and (s.avg_n1 + s.avg_n2 + s.avg_n3) > 0]
        if not valid:
            return None

        sorted_s = sorted(valid, key=lambda s: s.max_workers)
        labels = [f"{s.scenario_name}\n({s.max_workers}h)" for s in sorted_s]
        n1_vals = [s.avg_n1 for s in sorted_s]
        n2_vals = [s.avg_n2 for s in sorted_s]
        n3_vals = [s.avg_n3 for s in sorted_s]
        p1_vals = [s.avg_pct_s1 for s in sorted_s]
        p2_vals = [s.avg_pct_s2 for s in sorted_s]
        p3_vals = [s.avg_pct_s3 for s in sorted_s]

        x = list(range(len(labels)))
        width = 0.25

        fig, ax = plt.subplots(figsize=(9.5, 5.2), dpi=150)
        b1 = ax.bar([i - width for i in x], n1_vals, width, label="Servidor 1 (N1)", color="#1f77b4")
        b2 = ax.bar(x, n2_vals, width, label="Servidor 2 (N2)", color="#2ca02c")
        b3 = ax.bar([i + width for i in x], n3_vals, width, label="Servidor 3 (N3)", color="#ff7f0e")

        for bars, pcts in ((b1, p1_vals), (b2, p2_vals), (b3, p3_vals)):
            for bar, pct in zip(bars, pcts):
                h = bar.get_height()
                if h > 0:
                    ax.annotate(
                        f"{h:.0f}\n({pct:.1f}%)",
                        xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha="center", va="bottom", fontsize=7.5
                    )

        ax.set_title("Distribución de Solicitudes Exitosas entre los 3 Servidores EC2 detrás del ALB", fontsize=11.5, pad=12)
        ax.set_xlabel("Escenario de Prueba (Concurrencia)", fontsize=10)
        ax.set_ylabel("Promedio de Respuestas Exitosas (HTTP 200)", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.grid(True, axis="y", linestyle=":", alpha=0.6)
        ax.legend(loc="upper left")

        plt.figtext(
            0.5, -0.02,
            "Nota: Mediciones obtenidas empíricamente. El algoritmo del ALB no garantiza reparto exacto de 33.3% en cada corrida.",
            wrap=True, horizontalalignment="center", fontsize=8, fontstyle="italic", color="#555555"
        )

        output_path = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path

    def plot_cpu_multi_server(
        self,
        summaries_42: List[ScenarioSummary],
        filename: str = "grafica_cpu_tres_ec2.png"
    ) -> Optional[Path]:
        """Grafica Hilos vs CPU máxima promedio observada en Servidor 1, 2 y 3 solo si hay datos suficientes."""
        valid = [
            s for s in summaries_42
            if any(v is not None for v in (s.avg_cpu_s1, s.avg_cpu_s2, s.avg_cpu_s3))
        ]
        if not valid:
            return None

        sorted_s = sorted(valid, key=lambda s: s.max_workers)
        fig, ax = plt.subplots(figsize=(8.5, 5), dpi=150)

        series = [
            ("Servidor 1 CPU (%)", [s.avg_cpu_s1 for s in sorted_s], "#1f77b4", "o"),
            ("Servidor 2 CPU (%)", [s.avg_cpu_s2 for s in sorted_s], "#2ca02c", "s"),
            ("Servidor 3 CPU (%)", [s.avg_cpu_s3 for s in sorted_s], "#ff7f0e", "^"),
        ]

        plotted_any = False
        for label, vals, color, marker in series:
            pts = [(s.max_workers, v) for s, v in zip(sorted_s, vals) if v is not None]
            if pts:
                plotted_any = True
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                ax.plot(xs, ys, marker=marker, color=color, linewidth=2, label=label)
                for x_val, y_val in pts:
                    ax.annotate(f"{y_val:.1f}%", (x_val, y_val), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8)

        if not plotted_any:
            plt.close(fig)
            return None

        ax.set_title("Concurrencia vs Uso de CPU Observado en las 3 Instancias EC2", fontsize=11.5, pad=12)
        ax.set_xlabel("Número Máximo de Hilos Concurrentes (Workers)", fontsize=10)
        ax.set_ylabel("Carga de CPU Observada en EC2 (%)", fontsize=10)
        ax.set_ylim(0, 105)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="upper left")

        plt.figtext(
            0.5, -0.02,
            "Nota: Valores registrados manualmente desde top/htop/CloudWatch en cada instancia EC2. No simulados.",
            wrap=True, horizontalalignment="center", fontsize=8, fontstyle="italic", color="#555555"
        )

        output_path = self.output_dir / filename
        plt.tight_layout()
        plt.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return output_path
