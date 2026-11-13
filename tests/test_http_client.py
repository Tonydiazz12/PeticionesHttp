"""Pruebas unitarias para el cliente HTTP con simulación aislada (Mock)."""

from unittest.mock import MagicMock, patch
import requests
from config.settings import TargetConfig
from core.http_client import SafeHttpClient
from models.request_result import RequestStatus


def test_http_client_success():
    target_cfg = TargetConfig(target_url="http://127.0.0.1:8080/", allowed_hosts={"127.0.0.1"})
    client = SafeHttpClient(target_cfg, expected_text="Bienvenidos al Servidor 1", timeout=2.0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><body>Bienvenidos al Servidor 1</body></html>"

    with patch.object(client.session, "get", return_value=mock_resp):
        record = client.execute_request(request_id=1, scenario="Test", repetition=1)

    assert record.status == RequestStatus.SUCCESS
    assert record.http_status == 200
    assert record.is_success is True
    assert record.error_detail == ""


def test_http_client_content_mismatch():
    target_cfg = TargetConfig(target_url="http://127.0.0.1:8080/", allowed_hosts={"127.0.0.1"})
    client = SafeHttpClient(target_cfg, expected_text="Bienvenidos al Servidor 1", timeout=2.0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "Error del servidor proxy apache"

    with patch.object(client.session, "get", return_value=mock_resp):
        record = client.execute_request(request_id=2, scenario="Test", repetition=1)

    assert record.status == RequestStatus.CONTENT_MISMATCH
    assert record.http_status == 200
    assert record.is_success is False
    assert "Texto esperado" in record.error_detail


def test_http_client_http_500():
    target_cfg = TargetConfig(target_url="http://127.0.0.1:8080/", allowed_hosts={"127.0.0.1"})
    client = SafeHttpClient(target_cfg, timeout=2.0)

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch.object(client.session, "get", return_value=mock_resp):
        record = client.execute_request(request_id=3, scenario="Test", repetition=1)

    assert record.status == RequestStatus.HTTP_STATUS_ERROR
    assert record.http_status == 500
    assert "Código HTTP inesperado: 500" in record.error_detail


def test_http_client_timeout():
    target_cfg = TargetConfig(target_url="http://127.0.0.1:8080/", allowed_hosts={"127.0.0.1"})
    client = SafeHttpClient(target_cfg, timeout=2.0)

    with patch.object(client.session, "get", side_effect=requests.exceptions.Timeout("Read timed out")):
        record = client.execute_request(request_id=4, scenario="Test", repetition=1)

    assert record.status == RequestStatus.TIMEOUT
    assert record.http_status is None
    assert "Timeout tras" in record.error_detail


def test_http_client_connection_error():
    target_cfg = TargetConfig(target_url="http://127.0.0.1:8080/", allowed_hosts={"127.0.0.1"})
    client = SafeHttpClient(target_cfg, timeout=2.0)

    with patch.object(client.session, "get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        record = client.execute_request(request_id=5, scenario="Test", repetition=1)

    assert record.status == RequestStatus.CONNECTION_ERROR
    assert record.http_status is None
    assert "Falla de conexión" in record.error_detail


def test_http_client_identifies_three_servers():
    target_cfg = TargetConfig(
        alb_url="http://mi-alb.us-east-1.elb.amazonaws.com/",
        allowed_hosts={"mi-alb.us-east-1.elb.amazonaws.com"}
    )
    client = SafeHttpClient(target_cfg, timeout=2.0)

    for idx, expected_srv in ((1, "Servidor 1"), (2, "Servidor 2"), (3, "Servidor 3")):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = f"Bienvenidos al {expected_srv}"
        with patch.object(client.session, "get", return_value=mock_resp):
            rec = client.execute_request(request_id=idx, scenario="ALB", repetition=1)
        assert rec.status == RequestStatus.SUCCESS
        assert rec.server_id == expected_srv
        assert rec.response_body == f"Bienvenidos al {expected_srv}"


def test_http_client_unknown_server_body_rejected():
    target_cfg = TargetConfig(target_url="http://127.0.0.1:8080/", allowed_hosts={"127.0.0.1"})
    client = SafeHttpClient(target_cfg, timeout=2.0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "Bienvenidos al Servidor 4"
    with patch.object(client.session, "get", return_value=mock_resp):
        rec = client.execute_request(request_id=6, scenario="ALB", repetition=1)

    assert rec.status == RequestStatus.CONTENT_MISMATCH
    assert rec.server_id == "No identificado"
    assert rec.is_success is False

