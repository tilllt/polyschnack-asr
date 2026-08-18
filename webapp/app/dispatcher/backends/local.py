"""dispatcher/backends/local.py — die Box selbst als Backend (Change 020).

Erstes Backend: Jobs laufen lokal wie heute — der Dispatcher ist damit im
Ist-Betrieb nutzbar (Queue/Router), bevor überhaupt Cloud-Backends
existieren. Jurisdiktion "eu" → auch im EU-only-Modus (Stufe 2) erlaubt.

Der Job-Ausführer ist konfigurierbar (`run_command`): ein Shell-Kommando,
das den Job-Pfad als Argument bekommt. Ergebnisdateien werden als
`result_url` (file://) gemeldet.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import (
    Endpoint,
    GpuFilter,
    InferenceBackend,
    Instance,
    JobResult,
    Offer,
)

# Annahme: Betriebskosten der Box (Strom) ≈ 0,05 $/h — als Preis der
# lokalen "Offer" für die Kostenrechnung (keine echte Abrechnung).
LOCAL_PRICE_USD_H = 0.05
LOCAL_GPU = "RTX 3090 Ti (lokal)"
LOCAL_VRAM_GB = 24


@dataclass
class LocalBackend(InferenceBackend):
    """Führt Jobs als Subprozesse auf der lokalen Box aus.

    run_command: Kommando, das als letzten Parameter den Job-Ordner erhält;
                 legt dort `result.json` an (oder exit-code != 0 = Fehler).
    workdir:     Basis für Job-Ordner (default: tempfile-Verzeichnis).
    """

    provider_name: str = "local"
    jurisdiction: str = "eu"
    run_command: str = "true"
    workdir: Path = field(
        default_factory=lambda: Path(os.environ.get("TMPDIR", "/tmp"))
    )

    # ── Interface ────────────────────────────────────────────────────────

    def list_offers(self, flt: GpuFilter) -> list[Offer]:
        # Eine synthetische Offer: die Box selbst.
        return [
            Offer(
                provider=self.provider_name,
                offer_id="local-box",
                gpu_name=LOCAL_GPU,
                vram_gb=LOCAL_VRAM_GB,
                price_usd_h=LOCAL_PRICE_USD_H,
                region="EU",
                reliability=0.99,
            )
        ]

    def acquire(
        self,
        offer: Offer,
        image: str = "",
        disk_gb: int = 50,
        env: dict[str, str] | None = None,
    ) -> Instance:
        # Lokal gibt es nichts zu mieten — die Instanz IST die Box.
        return Instance(
            provider=self.provider_name,
            instance_id=f"local-{uuid.uuid4().hex[:8]}",
            offer_id=offer.offer_id,
            region="EU",
            status="running",
        )

    def wait_ready(self, instance: Instance, timeout_s: int = 900) -> Endpoint:
        return Endpoint(url="local://box", token="")

    def submit_job(self, endpoint: Endpoint, job: dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        job_dir = self.workdir / f"psjob-{job_id}"
        job_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Job-Payload (z. B. Pfad zur verschlüsselten Datei) nach job.json:
        (job_dir / "job.json").write_text(
            __import__("json").dumps(job), encoding="utf-8"
        )
        cmd = f"{self.run_command} {shlex.quote(str(job_dir))}"
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._procs[job_id] = proc
        return job_id

    def poll(self, instance: Instance, job_id: str) -> JobResult:
        proc = self._procs.get(job_id)
        if proc is None:
            return JobResult(status="failed", job_id=job_id, error="unbekannte job_id")
        job_dir = self.workdir / f"psjob-{job_id}"
        result_file = job_dir / "result.json"
        if proc.poll() is None:
            return JobResult(status="running", job_id=job_id)
        if proc.returncode == 0 and result_file.exists():
            return JobResult(
                status="done",
                job_id=job_id,
                progress=1.0,
                result_url=result_file.as_uri(),
            )
        stderr = (proc.stderr.read() if proc.stderr else "") or ""
        return JobResult(
            status="failed",
            job_id=job_id,
            error=f"exit={proc.returncode}: {stderr[:300]}",
        )

    def destroy(self, instance: Instance) -> None:
        # Lokal nichts zu tun — laufende Jobs werden nicht abgebrochen.
        return None

    # ── intern ───────────────────────────────────────────────────────────

    _procs: dict[str, subprocess.Popen] = field(default_factory=dict)


# Wiederverwendbarer Default-Ausführer: kopiert die Eingabe-Audiodatei nach
# result.json-freundlich — für Tests; echte Jobs ersetzen run_command.
def _sleep_job(job_dir: str) -> None:
    time.sleep(0.1)
