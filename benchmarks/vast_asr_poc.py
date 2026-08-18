#!/usr/bin/env python3
"""PoC-Messung Change 020: Parakeet-ASR auf vast.ai RTX 3060/3090 (EU).

Misst real: Walltime pro Audio-Stunde (RTF) + VRAM-Peak (nvidia-smi via
request_logs) — belegt die 12-GB-Eignung der ASR-Stufe, gemessen statt
geschätzt. Die Instanz wird in JEDEM Fall destruiert (try/finally).

Aufruf:
    python3 -S /opt/data/scripts/poc_vast_measure.py [--dry-run]

Erfordert: VAST_API_KEY + GITHUB_TOKEN in /opt/data/.env (sourced).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

VAST = "https://console.vast.ai/api/v0"
# nie sourcen — zeilenweise parsen; per ENV übersteuerbar für andere Hosts
ENV_FILE = os.environ.get("VAST_ENV_FILE", "/opt/data/.env")
AUDIO = os.environ.get(
    "POC_AUDIO", "/opt/data/pk-asr/businessplan/poc_test_audio.wav")


def env(key: str) -> str:
    """Key aus Umgebung oder /opt/data/.env (KEY=VALUE, zeilenweise)."""
    val = os.environ.get(key)
    if val:
        return val
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln.startswith(key + "="):
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    raise KeyError(f"{key} nicht in Umgebung oder {ENV_FILE}")
AUDIO_SECONDS = 13.9
IMAGE = "ghcr.io/tilllt/polyschnack-asr:latest"
DISK_GB = 30
EU_COUNTRIES = {
    "DE", "FR", "NL", "PL", "CZ", "FI", "SE", "RO", "BG", "ES", "IT",
    "PT", "IE", "AT", "BE", "HU", "DK", "EE", "LV", "LT", "SK", "SI",
    "HR", "GR", "LU", "MT", "CY", "NO",
}
GPU_PREF = ["RTX 3060", "RTX 3090", "RTX 4070", "RTX A4000", "RTX 4080"]
MAX_PRICE = 0.35
MAX_RENT_WAIT_S = 1500
MAX_HEALTH_WAIT_S = 1800
# WICHTIG (vast-Pitfall): onstart muss SOFORT enden, sonst wird der
# Image-Container-Start (Server) nie ausgeführt. Nur Hintergrund-Loop;
# onstart laut offizieller vast-Doku (docs.vast.ai, 2026-08-18):
# Bei SSH/Jupyter-runtypes ersetzt vasts SSH-Entrypoint den Image-ENTRYPOINT —
# das Image-CMD (python server.py) läuft NICHT automatisch; der onstart MUSS
# den Server starten. Der onstart wird als Shell-Skript (/root/onstart.sh)
# ausgeführt und endet sofort (Server + VRAM-Loop laufen im Hintergrund).
# tee: VRAM-Zeilen in Datei UND Container-Stdout (via request_logs sichtbar).
ONSTART_VRAM = (
    "mkdir -p /var/log/portal; cd /app; "
    "(nohup python server.py > /var/log/portal/server.log 2>&1 &); "
    "(while true; do nvidia-smi --query-gpu=memory.used "
    "--format=csv,noheader | tee -a /var/log/portal/vram.log; sleep 2; done) & "
    "echo onstart-ok"
)


def log(*a):
    print("[poc]", *a, flush=True)


def api(method, path, body=None):
    req = urllib.request.Request(
        VAST + path,
        method=method,
        headers={"Authorization": f"Bearer {env('VAST_API_KEY')}",
                 "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300]
        raise RuntimeError(f"vast-API {e.code} {path}: {detail}") from e


def search_offers(limit=3):
    """Top-N passende EU-Angebote — sortiert nach inet_down (mbps) ABSTEIGEND,
    nicht nach Preis (Skill vast-ai-gpu-instances, verifiziert 2026-08-12):
    hängender Image-Pull = Host-Bandbreite; Connectivity dominiert die
    Boot-Zeit mehr als der Preis. Preis-Deckel bleibt als Filter."""
    payload = {
        "gpu_name": {"in": GPU_PREF},
        "rentable": {"eq": True},
        "type": "ondemand",
        "num_gpus": {"eq": 1},
        "limit": 120,
        "order": [["dph_total", "asc"]],
    }
    offers = api("POST", "/bundles/", payload).get("offers", [])
    cands = []
    for o in offers:
        geo = o.get("geolocation") or ""
        cc = geo.split(", ")[-1] if ", " in geo else ""
        if cc not in EU_COUNTRIES:
            continue
        if o.get("dph_total", 99) > MAX_PRICE:
            continue
        if (o.get("inet_down") or 0) < 300:
            continue
        cands.append(o)
    if not cands:
        raise RuntimeError("Kein EU-Angebot gefunden (3060/3090 <= 0.35 $/h, >= 300 MB/s)")
    best = sorted(cands, key=lambda o: o.get("inet_down") or 0,
                  reverse=True)[:limit]
    for o in best:
        log(f"Kandidat: {o['gpu_name']} {o['dph_total']:.3f} $/h "
            f"{o['geolocation']} id={o['id']} mbps={o.get('inet_down')} "
            f"rel={o.get('reliability2')}")
    return best


def rent(offer):
    body = {
        "offer_id": offer["id"],
        "image": IMAGE,
        "disk": DISK_GB,
        # runtype laut offizieller vast-Doku (docs.vast.ai, 2026-08-18):
        # gültig sind ssh_direct|ssh_proxy|ssh|jupyter_direct|jupyter_proxy|
        # jupyter|args — "docker" existiert NICHT (Fehlerquelle Lauf 8!).
        # ssh_direct: Port 22, onstart läuft als Shell-Skript; muss den
        # Server selbst starten (Image-CMD läuft nicht automatisch).
        "runtype": "ssh_direct",
        "env": {"-p 5092:5092": "1"},
        "onstart": ONSTART_VRAM,
        "duration": "1 hour",
        "image_login": f"-u tilllt -p {env('GITHUB_TOKEN')} ghcr.io",
        "cancel_unavail": True,
    }
    resp = api("PUT", f"/asks/{offer['id']}/", body)
    if not isinstance(resp, dict) or not resp.get("success"):
        # vast liefert bei 400 "insufficient_credit" als {error,msg} mit
        # Status 400 — api() wirft dann HTTPError; hier fangen wir beides.
        raise RuntimeError(f"Miete abgelehnt: {resp}")
    nc = resp.get("new_contract")
    iid = nc["id"] if isinstance(nc, dict) else nc
    log(f"Instanz gemietet: {iid}")
    # Verifikation: runtype der Instanz (muss ssh_direct sein)
    for _ in range(6):
        try:
            d = api("GET", f"/instances/{iid}/")
            insts = d.get("instances")
            if isinstance(insts, dict):
                insts = [insts]
            rt = (insts[0] if insts else {}).get("runtype")
            if rt:
                log(f"runtype der Instanz: {rt}")
                if rt != "ssh_direct":
                    raise RuntimeError(
                        f"Instanz läuft mit runtype={rt} statt ssh_direct — "
                        "Instanz wird destruiert"
                    )
                break
        except Exception as e:
            if "läuft mit runtype" in str(e):
                raise
        time.sleep(5)
    return iid


def wait_running(iid):
    """Wartet auf running MIT Port. Frühdiagnose (Skill, 2026-08-11/12):
    status_msg lesen; hängender Pull (unveränderte Waiting-Logs) sofort
    abbrechen statt 25 min blind zu warten."""
    t0 = time.time()
    last_log_sig = None
    while time.time() - t0 < MAX_RENT_WAIT_S:
        d = api("GET", f"/instances/{iid}/")
        insts = d.get("instances", [{}])
        if isinstance(insts, dict):
            insts = [insts]
        inst = insts[0] if insts else {}
        status = inst.get("actual_status")
        msg = inst.get("status_msg", "")
        if status == "running":
            ports = inst.get("ports") or {}
            hp = None
            for p in ports.get("5092/tcp", []):
                hp = p.get("HostPort")
            if hp:
                ip = inst.get("public_ipaddr")
                log(f"running: http://{ip}:{hp}")
                return f"http://{ip}:{hp}", inst
        if status == "error":
            raise RuntimeError(f"Instanz error: {msg}")
        # Frühdiagnose: verdächtiger Zustand -> Daemon-Logs (Pull-Fortschritt)
        if time.time() - t0 >= 120 and int(time.time() - t0) % 60 < 10:
            try:
                sig = _pull_signal(iid)
                if sig is None:
                    log(f"  ...({int(time.time()-t0)}s) {status}: {msg[:80]}")
                elif sig == last_log_sig:
                    raise RuntimeError(
                        f"Pull hängt (unveränderte Logs, {int(time.time()-t0)}s) "
                        f"— {msg[:80]}")
                else:
                    last_log_sig = sig
                    log(f"  ...({int(time.time()-t0)}s) Pull läuft: {sig[:60]}")
            except RuntimeError:
                raise
            except Exception as e:
                log(f"  ...({int(time.time()-t0)}s) {status}: {msg[:80]} "
                    f"(log-check: {e})")
        time.sleep(10)
    raise TimeoutError("Instanz wurde nicht running")


def _pull_signal(iid):
    """Kurzer Daemon-Log-Check: Signatur des Pull-Fortschritts."""
    resp = api("PUT", f"/instances/request_logs/{iid}/",
               {"tail": "300", "daemon_logs": "true"})
    ru = resp.get("result_url")
    if not ru:
        return None
    time.sleep(4)
    with urllib.request.urlopen(urllib.request.Request(
            ru, headers={"User-Agent": "poc"}), timeout=20) as r:
        txt = r.read().decode(errors="ignore")
    lines = [ln for ln in txt.splitlines() if ln.strip()]
    if not lines:
        return None
    # Signatur: die letzten 3 inhaltsvollen Zeilen (Pull-Status)
    return "|".join(lines[-3:])[-120:]


def wait_health(url):
    t0 = time.time()
    while time.time() - t0 < MAX_HEALTH_WAIT_S:
        try:
            with urllib.request.urlopen(url + "/health", timeout=5) as r:
                if r.status == 200:
                    log(f"Server bereit nach {int(time.time()-t0)}s")
                    return
        except Exception:
            pass
        time.sleep(5)
    raise TimeoutError("ASR-Server /health nicht erreichbar")


def multipart_post(url, path, field="file", filename="audio.wav", mime="audio/wav"):
    boundary = "----poc" + os.urandom(8).hex()
    with open(path, "rb") as f:
        data = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        url + "/v1/audio/transcriptions",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read().decode())


def vram_peak(iid):
    """nvidia-smi-Zeilen aus den Container-Logs (request_logs) ziehen."""
    try:
        resp = api("PUT", f"/instances/request_logs/{iid}", {"tail": "4000"})
        result_url = resp.get("result_url")
        if not result_url:
            return None
        time.sleep(6)
        with urllib.request.urlopen(result_url, timeout=20) as r:
            txt = r.read().decode(errors="ignore")
        peak = 0
        lines = []
        for ln in txt.splitlines():
            if "MiB" in ln or ln.strip()[:1].isdigit():
                try:
                    val = int(ln.split()[0])
                    peak = max(peak, val)
                    lines.append(val)
                except (ValueError, IndexError):
                    pass
        return {"peak_mib": peak, "samples": len(lines)}
    except Exception as e:
        return {"error": str(e)}


def destroy(iid):
    try:
        r = api("DELETE", f"/instances/{iid}/")
        log(f"Destroy: {r.get('success')}")
    except Exception as e:
        log(f"Destroy-Fehler: {e}")


def report_machine(iid, problem="Instance Takes Too Long To Load", message=""):
    """Defekte Maschine an vast reporten (best effort, Skill 2026-08-12).
    machine_id aus der Instanz-API; Rate-Limit 3/h wird respektiert."""
    try:
        d = api("GET", f"/instances/{iid}/")
        insts = d.get("instances", [{}])
        if isinstance(insts, dict):
            insts = [insts]
        inst = insts[0] if insts else {}
        mid = inst.get("machine_id")
        if not mid:
            return
        api("PUT", f"/machines/{mid}/report/", {
            "machine_id": mid,
            "instance_id": iid,
            "problem": problem,
            "message": message[:200],
        })
        log(f"Report gesendet: machine={mid} ({problem})")
    except Exception as e:
        log(f"Report fehlgeschlagen (best effort): {e}")


def destroy_with_report(iid, problem="Instance Takes Too Long To Load",
                        message=""):
    report_machine(iid, problem, message)
    destroy(iid)


def main():
    dry = "--dry-run" in sys.argv
    result = {"status": "ok", "attempts": []}
    try:
        offers = search_offers()
        if dry:
            print(json.dumps({"dry_run": True,
                              "offers": [o["id"] for o in offers]}))
            return
        last_err = None
        for offer in offers:
            iid = None
            failed = False
            try:
                iid = rent(offer)
                result["offer"] = offer["id"]
                result["price_usd_h"] = offer["dph_total"]
                result["gpu"] = offer["gpu_name"]
                result["region"] = offer["geolocation"]
                result["instance"] = iid
                url, inst = wait_running(iid)
                wait_health(url)
                t0 = time.time()
                res = multipart_post(url, AUDIO)
                wall = time.time() - t0
                result["wall_s"] = round(wall, 2)
                result["rtf"] = round(wall / AUDIO_SECONDS, 3)
                result["text_head"] = (res.get("text") or "")[:80]
                time.sleep(4)  # letzte VRAM-Samples einsammeln
                result["vram"] = vram_peak(iid)
                result["attempts"].append({"offer": offer["id"], "ok": True})
                log(f"RTF={result['rtf']} wall={result['wall_s']}s "
                    f"vram={result['vram']}")
                break
            except Exception as e:
                failed = True
                last_err = str(e)
                result["attempts"].append({"offer": offer["id"], "ok": False,
                                           "error": last_err})
                log(f"Versuch {offer['id']} fehlgeschlagen: {last_err}")
            finally:
                if iid:
                    if failed:
                        destroy_with_report(
                            iid,
                            "Unable To Start Instance"
                            if "health" in (last_err or "")
                            else "Instance Takes Too Long To Load",
                            last_err or "")
                    else:
                        destroy(iid)
        else:
            raise RuntimeError(f"Alle Versuche fehlgeschlagen: {last_err}")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        log(f"FEHLER: {e}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
