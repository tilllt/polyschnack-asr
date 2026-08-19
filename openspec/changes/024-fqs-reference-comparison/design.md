# Design — Change 024: FQS-Referenzvergleich

## Datenquellen (alle öffentlich, geprüft 2026-08-19)

| Quelle | Inhalt | Lizenz-/Nutzungshinweis |
|---|---|---|
| Zenodo Record 10209813 (`Appendix 2 - Sound files.zip`) | 4 MP3: `DE_example_1.mp3` (16,5 s), `DE_example_2.mp3` (44,7 s), `EN_example_1.mp3` (24,5 s), `EN_example_2.mp3` (16,2 s) | FQS-Artikel CC-BY 4.0; Zenodo-Lizenzfeld leer; Audio mit Einwilligung der Interviewten veröffentlicht. Nutzung mit Quellenangabe. |
| FQS-Supplement `24-1-8-e_tab5.pdf` (EN) / `tab6.pdf` (DE) | Manuelle Referenztranskripte („Manual") + Transkripte aller 9/10 Tools je Beispiel (Spalten: Beispiel 1 \| Beispiel 2) | ebenda |
| FQS-Artikel (Volltext-PDF, DOI 10.17169/fqs-25.1.4129) | Methodik (WER-Definition, Normalisierungsregeln), publizierte Interviewwerte als Kontext | CC-BY 4.0 |

**Zuordnung Audio ↔ Beispiel:** `*_example_N.mp3` ↔ „Beispiel N" der
entsprechenden Tabelle (Studie: „The recordings correspond to the
transcripts in Table 5 and Table 6").

## Extraktion der Tabellen-Transkripte (Erkenntnisse aus der Umsetzung)

Die PDFs sind zweispaltig (Beispiel 1 links, Beispiel 2 rechts), aber das
Layout unterscheidet sich:

- **tab6 (DE):** klare 2-Spalten-Trennung; jede Tool-Zeile = linke Spalte
  (Ex1) + rechte Spalte (Ex2).
- **tab5 (EN):** Beispiel 2 „schlangt" — der Text steht teils in der rechten
  Spalte UND teils als zweiter Block unter Beispiel 1 in der linken Spalte.

Lösung (im Benchmark-Repo als `scripts/fqs_extract_tables.py`):
1. Tool-Zeilen über Header-Wörter erkennen (x < 160); Band-Obergrenze =
   minimales y der Header-Gruppe (mehrzeilige Header wie „Dragon 15",
   „Happy Scribe", „Sonix-AI" vertikal verteilt).
2. Spaltengrenze pro Dokument aus den **Text-Block-x0-Werten** der ersten
   Seite (größter x-Gap; Wort-x0 ist verrauscht, Median-Split versagt bei
   asymmetrischen Spalten).
3. Pro Zeile: erster Links-Block = Beispiel 1; alle weiteren Links-Blöcke +
   Rechts-Blöcke = Beispiel 2 (deckt das „Schlangen"-Layout ab).
4. Fußnoten („Text in bold …") und Seitenkopfrüßen ausschließen;
   Fußnotenmarker („?1", „.1") entfernen.

Validierung: Manuelle Referenztexte der Studie („Manual") wurden gegen die
Lesereihenfolge des PDFs abgeglichen — Übereinstimmung.

## Ground Truth & Hypothesen

- `benchmark/data/fqs/ground_truth.json`: je Beispiel die „Manual"-Texte
  (Quelle: Tabellen 5/6, extrahiert; Quellenangabe im File).
- `benchmark/data/fqs/fqs_tables.json`: alle Tool-Transkripte je Beispiel
  (rohe Extraktion) — Grundlage für die WER-Berechnung der kommerziellen
  Anbieter auf denselben Ausschnitten.
- Audio: `benchmark/data/fqs/audio/*.mp3`, Download reproduzierbar über
  `scripts/fqs_download.py` (Zenodo-File-URL gepinnt, SHA-256-Verifikation).

## Metrik & Normalisierung

- jiwer `wer`/`cer` wie im bestehenden Benchmark (run.py nutzt jiwer).
- Normalisierung: lowercase, Satzzeichen entfernt (jiwer-Standard).
- FQS-Sonderregeln (Alternativschreibungen nicht als Fehler) werden
  dokumentiert, nicht nachgebaut — konservativ, alle Systeme gleich.
- RTF: wie bei den übrigen Kategorien gemessen (echte Zeit / Audiodauer).

## Testlauf

- Muster der Nacht-Suite (references/night-suite-orchestration.md):
  1 frische vast.ai-Instanz je Backend (EU, CUDA ≥ 12.8), onstart startet
  den ASR-Server, Destroy im finally + Wrapper-Cleanup + Watchdog.
- Backends: alle konfigurierten (`ps-pk-onnx`, `crispr-pk-cpp`,
  `crispr-moonshine-de`, `crispr-canary`; qwen3/ark dokumentiert fehlgeschlagen —
  optionaler Retry, kein Suite-Blocker).
- 4 Samples (~102 s Audio) → Lauf in Minuten; Kosten ≈ 0,01–0,05 $.

## Einschränkungen (dokumentiert, nicht verhandelbar)

1. **Ausschnitte ≠ volle Interviews:** publizierte Prozentwerte der Studie
   sind NICHT vergleichbar; Vergleich nur auf den Ausschnitten.
2. **Stichprobengröße:** ~102 s Audio gesamt → keine statistische Aussage,
   nur Orientierung; im Report explizit markiert.
3. **Tools von 2022:** Anbieter weiterentwickelt; Re-Benchmark heute via API
   (3–5 € je Anbieter, API-Zugänge geprüft) als dokumentiertes Follow-up.
4. **Alternative verworfen:** Autoren kontaktieren für volle Interviews —
   Aufwand/Nutzen gering, da der Vergleichszweck (Modellklassen-Orientierung)
   auch mit den Ausschnitten erfüllt wird.

## Warum diese Lösung

- **Ehrlichkeit:** keine Umrechnung fremder Prozentwerte; exakt dieselben
  Audiodateien für beide Seiten.
- **Reproduzierbarkeit:** Download gepinnt (SHA-256), Extraktion als Skript,
  Lauf per standard run.py — alles im Benchmark-Repo nachvollziehbar.
- **Kosten:** Testlauf ~0,01–0,05 $ statt 3–5 € je kommerziellem Anbieter.
