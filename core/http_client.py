"""Cliente HTTP seguro, con timeout estricto, sin redirecciones ni reintentos automáticos."""

import datetime
import re
import time
from typing import Dict, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import DEFAULT_SERVER_MESSAGES, TargetConfig
from models.request_result import RequestRecord, RequestStatus


class SafeHttpClient:
    """Ejecutor individual de solicitudes HTTP con validación estricta y clasificación por servidor."""

    def __init__(
        self,
        target_config: TargetConfig,
        expected_text: str = "Bienvenidos al Servidor 1",
        timeout: float = 5.0,
        valid_server_messages: Optional[Dict[str, str]] = None
    ):
        self.target_config = target_config
        self.expected_text = expected_text
        self.timeout = timeout
        self.valid_server_messages: Dict[str, str] = (
            dict(valid_server_messages) if valid_server_messages is not None else dict(DEFAULT_SERVER_MESSAGES)
        )

        # Configurar sesión sin reintentos automáticos
        self.session = requests.Session()
        no_retry_strategy = Retry(
            total=False,
            connect=False,
            read=False,
            redirect=False,
            status=False,
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=no_retry_strategy, pool_connections=100, pool_maxsize=100)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _identify_server(self, body_text: str) -> Optional[str]:
        """Identifica el servidor si el cuerpo contiene exactamente uno de los mensajes válidos."""
        matches = []
        for srv_name, expected_msg in self.valid_server_messages.items():
            pattern = rf"(?<!\w){re.escape(expected_msg)}(?!\w)"
            if re.search(pattern, body_text):
                matches.append(srv_name)

        if len(matches) == 1:
            return matches[0]

        if not matches and self.expected_text and self.expected_text not in self.valid_server_messages.values():
            pattern = rf"(?<!\w){re.escape(self.expected_text)}(?!\w)"
            if re.search(pattern, body_text):
                return "Servidor 1"

        return None

    def execute_request(self, request_id: int, scenario: str, repetition: int) -> RequestRecord:
        """Ejecuta una petición GET y clasifica exhaustivamente el resultado."""
        timestamp_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        start_time = time.perf_counter()

        http_status: Optional[int] = None
        status: RequestStatus = RequestStatus.OTHER_ERROR
        error_detail: str = ""
        server_id: str = "No identificado"
        response_body: str = ""

        try:
            # allow_redirects=False garantiza que no se sigan redirecciones a otros dominios
            response = self.session.get(
                self.target_config.target_url,
                timeout=self.timeout,
                allow_redirects=False,
                headers={"User-Agent": "LoadTestClient/1.0", "Accept": "text/html,text/plain"}
            )
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            http_status = response.status_code
            body_text = response.text or ""
            response_body = body_text.strip().replace("\r", " ").replace("\n", " ")[:120]

            if http_status == 200:
                matched_server = self._identify_server(body_text)
                if matched_server is not None:
                    status = RequestStatus.SUCCESS
                    server_id = matched_server
                else:
                    status = RequestStatus.CONTENT_MISMATCH
                    server_id = "No identificado"
                    error_detail = (
                        f"Texto esperado de Servidor 1/2/3 no encontrado en respuesta. "
                        f"Primeros 60 caracteres recibidos: '{body_text[:60]}'"
                    )
            else:
                status = RequestStatus.HTTP_STATUS_ERROR
                error_detail = f"Código HTTP inesperado: {http_status}"

        except requests.exceptions.Timeout as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            status = RequestStatus.TIMEOUT
            error_detail = f"Timeout tras {duration_ms:.2f} ms (límite {self.timeout}s): {str(exc)}"

        except requests.exceptions.ConnectionError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            status = RequestStatus.CONNECTION_ERROR
            error_detail = f"Falla de conexión o rechazo TCP: {type(exc).__name__}"

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            status = RequestStatus.OTHER_ERROR
            error_detail = f"Error imprevisto: {type(exc).__name__} - {str(exc)}"

        return RequestRecord(
            request_id=request_id,
            scenario=scenario,
            repetition=repetition,
            timestamp_iso=timestamp_iso,
            duration_ms=duration_ms,
            http_status=http_status,
            status=status,
            error_detail=error_detail,
            server_id=server_id,
            response_body=response_body
        )

    def close(self):
        """Cierra el pool de conexiones."""
        self.session.close()

