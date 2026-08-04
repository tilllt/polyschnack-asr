# Post-Processing & Delivery

Alles ist **opt-in** (nichts läuft automatisch): an der Transcribe-Zeile
wählst du pro Aufnahme, was nach der Transkription passieren soll.

## Optionen

- **Satzzeichen (`✍️ Punct`)** — Interpunktion nach der Erkennung. Modus per
  `POLYSCHNACK_PUNCTUATION_MODE` (Default `off`; `local` = offline, `llm` =
  kostenpflichtig).

  !!! note "Native Interpunktion"
      Die CrispASR-Backends (Qwen3-ASR, ARK-ASR, pk-cpp) punktieren **nativ**
      vom Server (`--punc-model fullstop` = EN/DE/FR/IT, `--truecase-model lstm`
      = deutsches Truecasing, 97,9 % F1) — dort wird das LLM-Punctuation
      automatisch übersprungen (keine doppelte Interpunktion).

- **Wort-Confidence (Per-Token)** — CrispASR-Backends liefern pro Wort eine
  Sicherheit (`probability` 0–100 %). Die Webapp färbt unsichere Wörter ein:
  **grün** ≥ 90 %, **gelb** ≥ 70 %, **rot** darunter. (Nur sichtbar, wenn das
  Backend Confidence liefert; kein Fake-Wert.)
- **LLM-Optimierung (`✨ LLM`)** — KI-Nachbearbeitung des Textes. **Nur für
  registrierte User** (kostenpflichtig), anonyme sehen den Schalter ausgegraut.
- **Vorlage (Template)** — eigene Prompt-Vorlagen im Panel
  `🧩 Post-Processing` (z. B. „Meeting-Zusammenfassung + ToDos"). Der Text
  ersetzt `{text}` im Prompt; das Ergebnis wird als **neue Version**
  (`kind="postprocess"`) abgelegt. Ebenfalls nur für registrierte User.
- **Senden an (Delivery-Target)** — fertige Transkription automatisch
  zustellen: **E-Mail** (SMTP) oder **WebDAV** (z. B. Nextcloud). Ziele werden
  im Panel angelegt; Passwörter werden **verschlüsselt** (Fernet, abgeleitet
  aus `SESSION_SECRET`) gespeichert und nie wieder ausgegeben. Auch für
  anonyme User nutzbar. Status (`pending`/`done`/`failed`) steht am Recording.

## BYOK — eigene LLM-Endpunkte (registrierte User)

Registrierte User (OIDC) können eigene OpenAI-kompatible Endpunkte
hinterlegen und sie pro Transkription für LLM-Optimierung/Vorlagen auswählen
(Tab „LLM-Endpunkte (BYOK)" im Panel `🧩 Post-Processing`, Select
„LLM-Endpunkt" an der Transcribe-Zeile). Priorität:
**User-Endpunkt > Server-Env**.

- **Anlegen:** Name, Base-URL (z. B. `https://api.example.com/v1`), API-Key,
  Modell. Der API-Key wird **Fernet-verschlüsselt** gespeichert (Schlüssel aus
  `SESSION_SECRET`) und **nie** in GUI/API/Logs ausgegeben — nur beim
  Speichern sichtbar; ohne neuen Key bleibt der alte erhalten (PUT).
- **Sicherheit (SSRF):** Beim Speichern wird die URL geprüft — nur http(s)
  und **öffentliche** Adressen. `localhost`, private Netze (10/8, 172.16/12,
  192.168/16, 127.0.0.0/8, ::1, Link-Local) und die Cloud-Metadata-IP
  (169.254.169.254) werden mit 422 abgelehnt.
- **Zugriff:** Nur der Ersteller sieht/ändert/löscht seine Endpunkte
  (owner-only). BYOK ist ein kostenpflichtiger Pfad → **anonyme User
  gesperrt** (403, Select ausgegraut). Endpunkte sind strikt User-privat
  (keine Admin-Einsicht).

## Umgebungsvariablen

Siehe [Env-Variablen](env.md) → Abschnitt „Post-Processing & Delivery".
