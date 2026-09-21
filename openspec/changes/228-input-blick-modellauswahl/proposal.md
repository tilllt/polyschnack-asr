# Change 228 — „Input"-Blick: Quelle / Optionen / Postprocessing / Target + Modellauswahl aus dem Provider

## Nachtrag: zwei LLM-Stufen (Auftrag 21.09.2026)

**Auftrag (wörtlich):** „Mache das LLM Processing doppelt, einmal LLM postprocessing
wie du es vorgeschlagen hast (um den text Glattbügeln zu lassen) und einmal ‚KI
Formatierung' um z.b. eine Transkription in ein srichwortartiges Protokoll zu wandeln."

Damit hat die Nachbearbeitung künftig **zwei getrennte Stufen**, jede mit eigenem
Schalter, eigener Vorlage und eigenem KI-Server:

1. **LLM-Postprocessing** (bestehend, unverändert in der Wirkung): ASR-Fehler
   korrigieren/glattbügeln. Wörtlicher Text bleibt erhalten.
2. **KI-Formatierung** (neu): wandelt den Text in eine andere Form — z. B. ein
   stichwortartiges Protokoll. Der Wortlaut wird dabei bewusst verändert.

**Geplanter Zuschnitt** (Bestand geprüft: `TranscriptionRun` trägt heute genau ein
Paar `prompt_template_id`/`llm_endpoint_id` + `enable_llm_enhance`; der LLM-Aufruf
steht in `service.py` nach der Transkription, die Sicherung über
`versions.snapshot(...)` mit den Arten `transcribe`, `retranscribe`, `edit`,
`postprocess`):

- Lauf: zusätzlich `enable_formatting`, `format_template_id`, `format_endpoint_id`.
- Kette: Stufe 1 wie bisher → Stufe 2 nur bei eingeschaltetem Schalter, mit eigener
  Vorlage und eigenem Server (Vorgabe: Server der Stufe 1 bzw. der Plattform-Dienst).
- Ergebnis: die formatierte Fassung wird zum ausgelieferten Text (Ziel-Zustellung
  schickt sie), die wörtliche und die geglättete Fassung bleiben als eigene
  Fassungen erhalten — nichts wird überschrieben.
- Kosten/Latenz: die zweite Stufe ist ein zweiter LLM-Aufruf (mehr Zeit und Token);
  sie läuft nur, wenn sie eingeschaltet ist.
- Kennzeichnung: die Fassung heißt „KI-Formatierung" und ist als umgeformt
  gekennzeichnet — der Wortlaut stimmt dort nicht mehr mit dem Audio überein.

Offene Festlegungen stehen in der Rückfrage an den Nutzer (Ergebnisort, Herkunft
des Formatierungs-Prompts).

## Status
Entwurf (21.09.2026), Nutzerauftrag. **Umsetzung erst nach Klärung der offenen
Rückfragen** (unten), weil sie Datenmodell und Ort der Oberfläche bestimmen.

## Nutzer-Vorgabe (21.09.2026, wörtlich)

> „Wir wollen die Felder oben zu einem 'Input' Blick graphisch zusammenfassen,
> d.h. Quelle (Upload, Quelle, Download), Optionen (Default collapsed),
> postprocessing (default collapsed), und target (Default collapsed)
> postprocessing und target is optional, wenn nichts konfiguriert ist wird diese
> Spalte nicht angezeigt. Es ist jeweils das default ausgewählt. Wir müssen in
> der config ein Default auswählbar machen."

> „In der config, bei byok und LLM config muss die Modellauswahl automatisch
> aufgefüllt werden anhand des konfigurierten Providers - wenn einer
> konfiguriert ist."

## Ausgangslage / Befund (heute, geprüft am Code)

- **Quelle:** `UploadZone.tsx` rendert oben eine Zeile mit drei Umschaltern
  (`SourceTab` upload/record/download, `ps-source-row`, Change 222) und darunter
  die Zone der gewählten Quelle (`ps-tab-body`, Zonen aus Change 215).
- **Ein Panel für alles:** darunter genau EIN aufklappbares Panel
  (`options-panel`, Change 212/220). Es enthält die Matrix aus
  `optionMatrix.ts` **und** die Postprocessing-/Target-Felder
  (`pp={{templates, targets, endpoints, isOidc}}`); die Zeilenart `target`
  steckt heute als Option in der Matrix (`OptionsPanel.tsx`, `case "target"`).
  Zustand: `optsOpen` ist **standardmäßig offen**.
- **Postprocessing** = `TemplatesSection` + `LlmEndpointsSection`,
  **Target** = `TargetsSection` (Auslieferungsziel, `DeliveryTarget`,
  `kind ∈ {email, webdav}`) — beide werden in `UserSettingsPage.tsx` verwaltet.
- **BYOK/LLM:** `llm_endpoints.py` verwaltet `UserLlmEndpoint` (Felder u. a.
  `provider`, `model`, `base_url`); `model` hat den Vorgabewert
  `"deepseek-chat"` und wird im Frontend frei eingetippt — es gibt **keine**
  Liste der beim Provider verfügbaren Modelle.
- **Defaults:** es gibt heute **keinen** in der Config wählbaren Vorgabewert
  für Optionen, Postprocessing oder Target. Die Optionen starten aus
  `SOURCE_OPTION_DEFAULTS` im Code.

## Ziel

Ein „Input"-Blick, der die Felder oben grafisch zusammenfasst — vier Spalten:

1. **Quelle** — die drei Quellen (Datei-Upload, Aufnahme, Download/URL).
2. **Optionen** — die Optionsmatrix, **standardmäßig eingeklappt**.
3. **Postprocessing** — Vorlage + LLM-Endpunkt, **standardmäßig eingeklappt**,
   **optional**.
4. **Target** — Auslieferungsziel, **standardmäßig eingeklappt**, **optional**.

„Optional" heißt: ist für die Spalte nichts konfiguriert, wird sie **gar nicht
angezeigt**. In jeder Spalte ist der **Default** ausgewählt; welcher das ist,
muss in der Config auswählbar sein. Zusätzlich muss die Modellauswahl in der
Config (BYOK und LLM) automatisch aus dem konfigurierten Provider gefüllt
werden.

## Entscheidungen (aus dem Auftrag ableitbar, ohne Rückfrage)

1. **Vier Spalten, ein Block.** Die drei Options-/Postprocessing-/Target-Teile
   werden aus dem gemeinsamen Panel herausgezogen und zu eigenen Spalten. Die
   Optionsmatrix behält ihren Inhalt unverändert — es wird nichts umbenannt und
   keine Option hinzugefügt (Regel „Auftrag wörtlich").
2. **Eingeklappt ist nur die Darstellung.** Eingeklappt zeigt die Spalte ihre
   aktuelle Auswahl in einer Zeile (Default), aufgeklappt die Bedienelemente.
   Der Zustand ist rein lokal in der Oberfläche, nicht persistiert.
3. **Ausblenden ist datengetrieben.** Eine Spalte verschwindet, wenn ihre Liste
   leer ist: Postprocessing ohne Vorlagen *und* ohne LLM-Endpunkt, Target ohne
   Auslieferungsziel. Nicht ausgeblendet wird, solange der Server die Liste noch
   lädt (sonst flackert die Oberfläche).
4. **Modellliste kommt vom Provider, serverseitig.** Ein neuer Endpunkt fragt
   mit dem hinterlegten Schlüssel die Modellliste des konfigurierten Providers
   ab (OpenAI-kompatible `/v1/models` bzw. litellm `/v1/models`) und liefert sie
   an die Oberfläche. Ist kein Provider konfiguriert oder antwortet er nicht,
   bleibt die Auswahl ein Freitextfeld wie heute (kein stiller Fehler: die
   Oberfläche zeigt, dass keine Liste geladen werden konnte).

## Offene Rückfragen (bestimmen Datenmodell und Ort)

1. **Spalte „Quelle":** Sind damit die drei vorhandenen Quellen gemeint
   (Datei-Upload, **Aufnahme**, Download/URL) — also „Aufnahme" an der Stelle,
   wo im Auftrag „Quelle" steht?
2. **Ort des Defaults:** Soll der Vorgabewert **global im Admin-Bereich**
   einstellbar sein (gilt für alle), **je Nutzer in den Einstellungen**, oder
   beides (Nutzerwert schlägt Admin-Wert)?
3. **„Nichts konfiguriert":** Ist das Ausblenden an den **vorhandenen Einträgen
   des Nutzers** festgemacht (meine Annahme oben) oder an einer
   **systemweiten** Freigabe (z. B. Postprocessing nur für freigeschaltete
   Nutzer)?

## Umsetzungsschritte (nach Klärung)

1. OpenSpec-Änderung finalisieren; Vorgabe wörtlich abbilden.
2. Backend: Endpunkt für die Modellliste des konfigurierten Providers
   (`/api/llm/models` o. ä.), mit Fehlerweg; Default-Einstellung lesen/schreiben.
3. Frontend: `InputView` mit den vier Spalten; `OptionsPanel` in die
   Optionsspalte, Postprocessing- und Target-Sektionen in ihre Spalten; keine
   inhaltlichen Änderungen an der Matrix.
4. Config: Default-Auswahl (Ort nach Rückfrage) + Modell-Auswahlliste in BYOK
   und LLM-Config.
5. Testtor wie immer: `npx tsc --noEmit`, `npx vitest run`, `npm run build` mit
   Merker-Gegenprobe, dann Rollout per Skriptdatei und Gegenprobe am lebenden
   System (Assets, `/health`, Geometrie im Browser).

## Nicht Teil dieses Changes

- Keine Umbenennung von Reitern/Beschriftungen ohne Auftrag.
- Keine Änderung an Aufnahme-, Wiedergabe- oder Exportverhalten.
- Keine Änderung an der Optionsmatrix (Werte, Reihenfolge, Bedeutung).
