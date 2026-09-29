"""Invariante: Die ``transcribe``-Signatur kommt aus dem ABC (Change 234).

Anlass: Change 186/187 gab dem OpenAI-Proxy ein Kwarg ``language=...``, das
KEIN Adapter kannte — jeder Aufruf von ``/v1/audio/transcriptions`` endete mit
502 (``unexpected keyword argument 'language'``). Der Proxy-Test blieb grün,
weil sein Test-Double das Kwarg selbst definierte: ein Double, das mehr kann
als die echten Klassen, prüft nur sich selbst.

Diese Datei prüft deshalb die ECHTEN Klassen gegen die Basisklasse:
  1. jeder Adapter hat exakt die Parameter der Basisklasse (Namen, Reihenfolge,
     Vorgabewerte),
  2. jeder Adapter im Paket ist erfasst (ein neuer Adapter kann sich nicht
     stillschweigend ausnehmen),
  3. die Legacy-Funktionen im Paket passen zur gleichen Signatur.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Dict, List, Tuple

import app.asr_client as asr_client
import app.asr_client.adapters as adapters_pkg
from app.asr_client import AsrClient, language_field

ERWARTETE_ADAPTER = {
    "CrispAsrHttpClient",
    "OpenAiCompatHttpClient",
    "PkCppClient",
    "PkPythonClient",
    "Qwen3AsrHttpClient",
}


def _params(func) -> List[Tuple[str, str, object]]:
    """(Name, Kind, Vorgabewert) je Parameter — in Deklarationsreihenfolge."""
    return [
        (p.name, str(p.kind), p.default)
        for p in inspect.signature(func).parameters.values()
    ]


def _adapter_klassen() -> Dict[str, type]:
    gefunden: Dict[str, type] = {}
    for mod in pkgutil.iter_modules(adapters_pkg.__path__):
        modul = importlib.import_module(f"{adapters_pkg.__name__}.{mod.name}")
        for obj in vars(modul).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, AsrClient)
                and obj is not AsrClient
            ):
                gefunden[obj.__name__] = obj
    return gefunden


def test_adapter_paket_liefert_alle_bekannten_adapter():
    assert ERWARTETE_ADAPTER <= set(_adapter_klassen())


def test_jeder_adapter_hat_die_signatur_der_basisklasse():
    basis = _params(AsrClient.transcribe)
    abweichungen = {
        name: _params(cls.transcribe)
        for name, cls in _adapter_klassen().items()
        if _params(cls.transcribe) != basis
    }
    assert abweichungen == {}, (
        "Adapter weichen von AsrClient.transcribe ab — Signatur im ABC UND in "
        f"den Adaptern im selben Schritt ändern: {abweichungen}"
    )


def test_language_ist_optionaler_teil_der_signatur():
    for name, cls in _adapter_klassen().items():
        params = inspect.signature(cls.transcribe).parameters
        assert "language" in params, f"{name} kennt kein language"
        assert params["language"].default is None, f"{name}: AUTO muss None sein"


def test_legacy_funktionen_passen_zur_signatur():
    # ohne `self`: die Legacy-Funktion ist eine freie Funktion, keine Methode
    basis = list(inspect.signature(AsrClient.transcribe).parameters)[1:]
    assert list(inspect.signature(asr_client.transcribe).parameters) == basis


def test_language_field_laesst_auto_weg():
    assert language_field(None) == {}
    assert language_field("") == {}
    assert language_field("de") == {"language": "de"}
