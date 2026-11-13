"""Pruebas de validación de configuración, límites y listas blancas."""

import pytest
from config.settings import ConfigurationError, RunConfig, TargetConfig, PresetScenarios


def test_target_config_valid():
    cfg = TargetConfig(target_url="http://54.210.12.34/", allowed_hosts={"54.210.12.34"})
    assert cfg.target_url == "http://54.210.12.34/"


def test_target_config_unauthorized_host():
    with pytest.raises(ConfigurationError, match="Destino NO autorizado"):
        TargetConfig(target_url="http://google.com/", allowed_hosts={"54.210.12.34"})


def test_target_config_invalid_scheme():
    with pytest.raises(ConfigurationError, match="Esquema de URL no válido"):
        TargetConfig(target_url="ftp://54.210.12.34/", allowed_hosts={"54.210.12.34"})


def test_target_config_empty_allowed_hosts():
    with pytest.raises(ConfigurationError, match="lista de hosts autorizados .* está vacía"):
        TargetConfig(target_url="http://54.210.12.34/", allowed_hosts=set())


def test_run_config_limits():
    # Exceder peticiones
    with pytest.raises(ConfigurationError, match="Total de solicitudes"):
        RunConfig(scenario_name="Test", total_requests=5001, max_workers=10)

    # Exceder hilos
    with pytest.raises(ConfigurationError, match="Número de hilos"):
        RunConfig(scenario_name="Test", total_requests=100, max_workers=101)

    # Timeout no positivo
    with pytest.raises(ConfigurationError, match="timeout"):
        RunConfig(scenario_name="Test", total_requests=100, max_workers=10, timeout_seconds=0)


def test_preset_scenarios_comply_with_limits():
    scenarios = [
        PresetScenarios.baseline(),
        PresetScenarios.scenario_1(),
        PresetScenarios.scenario_2(),
        PresetScenarios.scenario_3(),
        PresetScenarios.fault_simulation()
    ]
    for sc in scenarios:
        assert 1 <= sc.total_requests <= 5000
        assert 1 <= sc.max_workers <= 100
        assert sc.timeout_seconds > 0
        assert sc.repetitions >= 1


def test_alb_dns_config_and_port_80_validation():
    alb_dns = "mi-alb-123.us-east-1.elb.amazonaws.com"
    cfg = TargetConfig(alb_url=f"http://{alb_dns}/", allowed_hosts={alb_dns})
    assert cfg.alb_url == f"http://{alb_dns}/"
    assert cfg.hostname == alb_dns

    # Puerto distinto de 80 en destino remoto debe rechazarse
    with pytest.raises(ConfigurationError, match="TCP 80"):
        TargetConfig(target_url=f"http://{alb_dns}:8080/", allowed_hosts={alb_dns})


def test_fault_simulation_preset():
    fs = PresetScenarios.fault_simulation()
    assert fs.total_requests == 20
    assert fs.max_workers == 1
    assert fs.repetitions == 1

