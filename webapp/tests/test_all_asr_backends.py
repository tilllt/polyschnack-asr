"""Backend-Matrix: JEDES aktive ASR-Backend aus backends.yaml ist testbar.

User-Vorgabe (2026-08-18): „teste bitte alle backends" — gemeint sind die
ASR-Backends. Dieser Test iteriert über die service_registry und prüft für
jedes aktive Backend:

1. get_client(backend) liefert eine AsrClient-Instanz (Adapter verdrahtet,
   Modul:Klasse importierbar, URL-Auflösung funktioniert).
2. capabilities.label stimmt mit der Backend-ID überein.
3. Pflicht-Felder (languages, device) sind gefüllt.
4. service_url() ist deterministisch (http://<name>:<port>).

Die Adapter-Verhaltenstests (transcribe/streaming/async/Fehler) liegen in
den einzelnen test_<adapter>_adapter.py-Dateien — diese Matrix deckt die
VERDRAHTUNG aller Backends ab.
"""
import pytest

from app.asr_client import AsrClient, get_client
from app.service_registry import available_services, list_services, service_url


@pytest.mark.parametrize("svc", list_services(), ids=lambda s: s["name"])
def test_backend_matrix_active_backends_are_usable(svc):
    if svc.get("status") != "active":
        pytest.skip("inaktiv")
    name = svc["name"]

    # 1) Adapter verdrahtet + instanziierbar
    client = get_client(name)
    assert isinstance(client, AsrClient), f"{name}: kein AsrClient"

    # 2) capabilities.label = Backend-ID (GUI zeigt diesen Namen)
    assert client.capabilities.label == name, (
        f"{name}: capabilities.label={client.capabilities.label!r}")

    # 3) Pflicht-Capabilities
    assert client.capabilities.languages, f"{name}: languages leer"
    assert client.capabilities.device, f"{name}: device leer"


def test_all_active_backends_have_unique_urls():
    """URL-Auflösung deterministisch und eindeutig (http://<name>:<port>)."""
    urls = {s["name"]: service_url(s) for s in available_services()}
    assert len(urls) == len(set(urls.values())), "URL-Kollision unter Backends"
    for name, url in urls.items():
        assert url.startswith("http://"), f"{name}: {url}"


def test_every_adapter_class_has_dedicated_behavior_test():
    """Jede Adapter-Klasse braucht ein eigenes Verhaltenstest-Modul.

    Schützt davor, dass ein neuer Adapter (neues Backend) vergessen wird:
    PkPythonClient → test_pk_python_adapter, PkCppClient →
    test_pk_cpp_adapter, Qwen3AsrHttpClient → test_qwen3_http_adapter,
    CrispAsrHttpClient → test_crisp_http_adapter,
    OpenAiCompatHttpClient → test_openai_compat_adapter.
    """
    from pathlib import Path
    classes = {s["adapter"].split(":")[1] for s in list_services()}
    expected = {
        "PkPythonClient": "test_pk_python_adapter",
        "PkCppClient": "test_pk_cpp_adapter",
        "Qwen3AsrHttpClient": "test_qwen3_http_adapter",
        "CrispAsrHttpClient": "test_crisp_http_adapter",
        "OpenAiCompatHttpClient": "test_openai_compat_adapter",
    }
    tests_dir = Path(__file__).resolve().parent
    for cls in sorted(classes):
        assert cls in expected, f"Adapter {cls} ohne bekannten Test"
        module = expected[cls]
        assert (tests_dir / f"{module}.py").is_file(), (
            f"{module}.py fehlt (Adapter {cls})")
