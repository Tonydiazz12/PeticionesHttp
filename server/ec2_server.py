"""Servidor HTTP multihilo para desplegar en las instancias AWS EC2 Linux.

Requisitos cumplidos:
- Escucha en TCP 80 (o puerto especificado por argumento de línea de comandos).
- Responde a GET / con estado HTTP 200 y cuerpo exacto 'Bienvenidos al Servidor <id>'.
- Responde a GET /health con estado HTTP 200 y cuerpo 'OK' para Health Checks del ALB.
- Emplea ThreadingHTTPServer para manejar solicitudes concurrentes adecuadamente.
"""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys


class BenchmarkHTTPRequestHandler(BaseHTTPRequestHandler):
    """Manejador HTTP ligero para pruebas de carga detrás de un ALB."""

    SERVER_ID: int = 1

    def do_GET(self):
        """Responde a GET / y GET /health con HTTP 200."""
        if self.path in ("/", "/index.html"):
            response_bytes = f"Bienvenidos al Servidor {self.SERVER_ID}".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(response_bytes)))
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(response_bytes)
        elif self.path == "/health":
            health_bytes = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(health_bytes)))
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(health_bytes)
        else:
            not_found = b"Recurso no encontrado"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(not_found)))
            self.end_headers()
            self.wfile.write(not_found)

    def log_message(self, format, *args):
        """Suprimir el registro por solicitud en consola para evitar cuellos de botella de E/S en pruebas masivas."""
        pass


def run_server(host: str = "0.0.0.0", port: int = 80, server_id: int = 1):
    BenchmarkHTTPRequestHandler.SERVER_ID = server_id
    response_text = f"Bienvenidos al Servidor {server_id}"
    server_address = (host, port)
    try:
        httpd = ThreadingHTTPServer(server_address, BenchmarkHTTPRequestHandler)
        print("==================================================")
        print(f" Servidor HTTP {server_id} de Pruebas de Carga Iniciado")
        print(f" Escuchando en   : http://{host}:{port}/")
        print(f" Health Check    : http://{host}:{port}/health -> 200 OK")
        print(f" Respuesta fija  : '{response_text}'")
        print(" Presiona Ctrl+C para detener el servidor.")
        print("==================================================")
        httpd.serve_forever()
    except PermissionError:
        print(f"\n[ERROR] Permiso denegado para enlazar el puerto {port}.")
        print("En Linux, los puertos menores a 1024 requieren privilegios de superusuario.")
        print(f"Ejecuta: sudo python3 ec2_server.py --port {port} --server-id {server_id}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nDeteniendo servidor HTTP...")
        httpd.server_close()
        print("Servidor detenido exitosamente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor HTTP para pruebas de escalamiento y carga en AWS EC2 con ALB")
    parser.add_argument("--host", default="0.0.0.0", help="Dirección IP de escucha (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=80, help="Puerto TCP de escucha (default: 80)")
    parser.add_argument("--server-id", type=int, choices=[1, 2, 3], default=1, help="Identificador del servidor EC2 (1, 2 o 3)")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, server_id=args.server_id)

