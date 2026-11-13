# Generador de Carga HTTP y Análisis de Rendimiento en AWS EC2 y ALB

Aplicación modular en Python para pruebas de carga y medición de rendimiento HTTP, adaptada de la Práctica 4.1 (1 instancia EC2) a la Práctica 4.2 (**Application Load Balancer público + 3 instancias EC2 Linux**).

---

## 1. Arquitectura del Sistema

```
+------------------------------------+             +---------------------------------------+
|   Estación Windows (Cliente)       |             |   AWS Application Load Balancer (ALB) |
|------------------------------------|             |---------------------------------------|
|  - VS Code                         |  Internet   |  - DNS público del ALB                |
|  - Python 3.11+                    | ----------> |  - Listener HTTP:80                   |
|  - ThreadPoolExecutor (1-100 hilos)|   HTTP GET  |  - Target Group HTTP:80               |
|  - SafeHttpClient (sin redirects)  |             |  - Health Check: GET /health -> 200   |
|  - MetricsCalculator (P95, N1-N3)  |             +-------------------+-------------------+
|  - Matplotlib & DataExporter       |                                 |
+------------------------------------+             +-------------------+-------------------+
                                                   |                   |                   |
                                                   v                   v                   v
                                            +-------------+     +-------------+     +-------------+
                                            | EC2 Linux 1 |     | EC2 Linux 2 |     | EC2 Linux 3 |
                                            | Server ID 1 |     | Server ID 2 |     | Server ID 3 |
                                            | TCP 80      |     | TCP 80      |     | TCP 80      |
                                            +-------------+     +-------------+     +-------------+
```

### Principios Fundamentales de Seguridad
- El cliente consulta exclusivamente el **nombre DNS del ALB** (o entornos locales `127.0.0.1`/`localhost`) registrados en `allowed_hosts`, sin depender de IPs fijas del ALB ni de las IPs públicas de los nodos.
- Valida esquema (`http`) y puerto `80` para destinos remotos.
- No permite redirecciones automáticas (`allow_redirects=False`) ni reintentos implícitos (`Retry(total=False)`).
- Incluye *circuit-breaker* y manejo seguro de `KeyboardInterrupt` (Ctrl+C).

---

## 2. Estructura del Código y Responsabilidades

| Módulo | Responsabilidad |
|---|---|
| `config/settings.py` | `TargetConfig` (validación DNS/URL ALB, puerto 80 y lista blanca), `RunConfig` (límites ≤ 5,000 reqs y ≤ 100 hilos) y `PresetScenarios` (Línea Base, Escenarios 1–3 y Simulación de Falla). |
| `models/request_result.py` | `RequestStatus` y `RequestRecord` (incluye `server_id` y `response_body`). |
| `models/run_metrics.py` | `RunMetrics` (`N1`, `N2`, `N3`, porcentajes, no identificadas, 3 CPUs EC2) y `ScenarioSummary` (promedios y peores valores observados). |
| `core/http_client.py` | `SafeHttpClient`: clasifica HTTP 200 con mensaje exacto de Servidor 1, 2 o 3; cuerpo desconocido como `CONTENT_MISMATCH`; HTTP != 200; timeout; error de conexión. |
| `core/scheduler.py` | `ConcurrentScheduler`: `ThreadPoolExecutor` con `threading.Lock`, contadores en tiempo real de `N1/N2/N3` y cancelación segura sin doble conteo. |
| `core/metrics_calculator.py` | `MetricsCalculator`: throughput exitoso, P95 (Método 7 de Hyndman & Fan) y porcentajes $100 \times N_i / (N_1+N_2+N_3)$. |
| `export/exporters.py` | `DataExporter`: CSV detallado, JSON resumen, `consolidado_corridas_alb.csv` (sin sobrescribir `consolidado_corridas.csv` de 4.1) y carga comparativa de 4.1. |
| `export/visualizer.py` | `ChartGenerator`: gráficas comparativas 4.1 vs 4.2 (Throughput y P95), barras de distribución `N1/N2/N3` y CPU de las 3 instancias. |
| `server/ec2_server.py` | Servidor HTTP multihilo para las 3 EC2 (`--server-id 1|2|3`, responde `GET /` y `GET /health`). |
| `main.py` | Interfaz CLI (`--alb-url`, `--config`, menú de escenarios, simulación de falla y comparación con 4.1). |

---

## 3. Fórmulas y Métodos de Medición

### Throughput Exitoso ($\text{req/s}$)
$$\text{Throughput} = \frac{\text{Número de peticiones exitosas (HTTP 200 de Servidor 1, 2 o 3)}}{\text{Tiempo global de la corrida en segundos}}$$

### Percentil 95 de Latencias ($P95$)
Se mantiene exactamente el método de Práctica 4.1 (interpolación lineal estándar, Método 7 de Hyndman & Fan):
$$k = 0.95 \times (N - 1), \quad i = \lfloor k \rfloor, \quad f = k - i \implies P95 = x_i + f \times (x_{i+1} - x_i)$$

### Distribución por Servidor (%)
Cuando $N_1 + N_2 + N_3 > 0$:
$$\%\,\text{Servidor}_i = 100 \times \frac{N_i}{N_1 + N_2 + N_3}, \quad i \in \{1, 2, 3\}$$
*Nota: El algoritmo de balanceo del ALB no garantiza exactamente $33.3\%$ por nodo en cada corrida.*

### Monitoreo de CPU de las tres EC2
El generador corre en Windows y no infiere ni inventa métricas de CPU. Al finalizar cada corrida se solicita manualmente el porcentaje máximo observado mediante `top` o `htop` para **Servidor 1**, **Servidor 2** y **Servidor 3** (o Enter para registrar `"No disponible"`). Si se usa CloudWatch, debe considerarse su granularidad estándar de 60 segundos y verificar que coincida exactamente con la ventana de tiempo de la corrida.

---

## 4. Puesta en Marcha en AWS (3 EC2 + Target Group + ALB)

### Paso 1: Desplegar el Servidor en cada Instancia EC2
Copia `server/ec2_server.py` en las tres instancias Linux e inicia cada una con su identificador:
```bash
# En Servidor 1:
sudo python3 ec2_server.py --port 80 --server-id 1

# En Servidor 2:
sudo python3 ec2_server.py --port 80 --server-id 2

# En Servidor 3:
sudo python3 ec2_server.py --port 80 --server-id 3
```
Abre `htop` o `top` en una segunda terminal SSH de cada instancia para observar la carga de CPU durante las pruebas.

### Paso 2: Configurar Target Group y ALB en AWS
1. **Target Group (HTTP, puerto 80):**
   - Registra las tres instancias EC2 en el puerto `80`.
   - Configura **Health Check path**: `/health` (responderá HTTP `200 OK`).
2. **Application Load Balancer (ALB):**
   - Listener **HTTP : 80** reenviando al Target Group anterior.
   - Security Group del ALB: permitir TCP `80` desde tu IP pública de Windows.
   - Security Group de las EC2: permitir TCP `80` desde el Security Group del ALB.

---

## 5. Instalación y Ejecución en Windows (VS Code)

### Paso 1: Activar Entorno Virtual e Instalar Dependencias
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Paso 2: Ejecutar Pruebas Automatizadas Locales (obligatorio antes de AWS)
```powershell
pytest -v
```

### Paso 3: Ejecutar el Generador hacia el ALB
Puedes ingresar el DNS del ALB de forma interactiva o pasarlo por parámetro/archivo:
```powershell
# Modo interactivo
python main.py

# Pasando la URL del ALB directamente
python main.py --alb-url http://mi-alb-123456.us-east-1.elb.amazonaws.com/

# O mediante archivo JSON de configuración (ej. config_alb.json)
python main.py --config config_alb.json
```

Ejemplo de `config_alb.json`:
```json
{
    "alb_url": "http://mi-alb-123456.us-east-1.elb.amazonaws.com/",
    "allowed_hosts": ["mi-alb-123456.us-east-1.elb.amazonaws.com"]
}
```

### Menú de Ejecución
- `0`: Línea Base (20 solicitudes, 1 hilo, 1 corrida).
- `1`: Escenario 1 (100 solicitudes, 10 hilos, 3 corridas).
- `2`: Escenario 2 (1,000 solicitudes, 50 hilos, 3 corridas).
- `3`: Escenario 3 (5,000 solicitudes, 100 hilos, 3 corridas).
- `4`: Batería Completa (10 corridas secuenciales).
- `5`: Simulación de Falla / Resiliencia (20 solicitudes tras detener una instancia EC2).
- `6`: Comparar con `resultados/consolidado_corridas.csv` (Práctica 4.1) y generar gráficas PNG.

---

## 6. Reportes y Artefactos Generados en `resultados/`

- **`{run_id}_detalle.csv`**: Detalle por petición (`request_id`, `scenario`, `repetition`, `timestamp_iso`, `duration_ms`, `http_status`, `status`, `server_id`, `response_body`, `error_detail`).
- **`{run_id}_resumen.json`**: Resumen individual con métricas, `N1/N2/N3`, porcentajes, CPUs observadas y desglose de errores.
- **`consolidado_corridas.csv`**: Histórico preservado de la Práctica 4.1 (no se sobrescribe).
- **`consolidado_corridas_alb.csv`**: Consolidado de las corridas de la Práctica 4.2 con el ALB.
- **`ejecucion_pruebas.log`**: Registro cronológico de eventos y errores.
- **Gráficas PNG**:
  - `grafica_throughput_comparativa_41_42.png`
  - `grafica_p95_comparativa_41_42.png`
  - `grafica_distribucion_servidores_alb.png`
  - `grafica_cpu_tres_ec2.png` (generada solo si existen mediciones reales suficientes)
