# Change 086 — Credits & Monetarisierung (User-sichtbare Job-Kosten)

Status: Proposal
Autor: Hermes (Till-Auftrag 2026-08-22: „Ja einbauen … Kostenübersicht für
den User für jeden Job. Virtuelles Top-Up, Kostenübersicht und Credit-
Verwaltung für Admin auch in GUI")

## Problem

- GPU-Transkription kostet echtes Geld (vast-Instanzen, Strom, LLM-APIs),
  aber kein User sieht, was ein Job kostet → Kosten laufen im Verborgenen.
- Es gibt keine Zugangskontrolle: jeder kann GPU-Jobs auslösen.
- Change 085 (GPU-Provisioning) braucht eine monetäre Steuergröße
  (Rentabilitäts-Gate, Budget-Cap) — ohne Credits/Preise keine Entscheidung.

## Ziel

1. **Kostenübersicht für den User pro Job**: jede Transkription zeigt, was
   sie gekostet hat (EUR-Cent) — aus den gemessenen Phasenzeiten ×
   Kostensätzen (Change 085 liefert `phase_times_ms`).
2. **Virtuelle Credits**: Testgeld für die Erprobung des ganzen Systems —
   Admin vergibt per Top-Up; Credits sind Zugangskontrolle (Rubén-
   Vereinfachung), keine echte Währung in v1.
3. **Admin-Steuerzentrale in der GUI**: Credit-Verwaltung (Top-Up, Tier),
   Kostenübersicht (Journal: Einnahmen vs. Instanzkosten), Budget.
4. Grundlage für das 085-Rentabilitäts-Gate (Σ Credit-Wert ≥ Instanzkosten).

## Nicht-Ziele (v1)

- Echte Zahlungen (Stripe o. Ä.) — später.
- Währungsumrechnung/Steuer — später.
- Automatische Deaktivierung bei Negativ-Konto (Reserve-System verhindert
  das; bei 0 Credits: GPU-Jobs nur mit Admin-Freigabe).

## Offene Fragen

- Soll ein User mit 0 Credits GPU-Jobs gar nicht erst starten können
  (403) oder mit Warnung durchlaufen (Phase: nur Test-Tier)? Vorschlag:
  Default `test`-Tier für alle bestehenden User (virtuelles Geld,
  Startguthaben 10 €), damit nichts bricht.
