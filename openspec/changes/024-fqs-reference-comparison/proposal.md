# Change 024 — FQS-Referenzvergleich: eigene Backends vs. kommerzielle ASR-Plattformen

## Problem

Die ASR-Evidenz (Change 021) stützt sich bislang auf den eigenen
207-Sample-Benchmark und auf **Fremdwerte** aus der FQS-Studie
(Wollin-Giering et al. 2024), die im Report nur als „nicht verifiziert"
referenziert werden. Damit fehlt ein **belastbarer Vergleich der eigenen
Backends gegen kommerzielle Transkriptionsplattformen auf identischem
Audio** — die zentrale Zahl für Verkaufsargument und Businessplan
(„unsere Genauigkeit im Vergleich zu Amberscript/Sonix/Trint/Happy Scribe").

Die Testdaten der Studie sind öffentlich: die Audio-Ausschnitte
(Zenodo Record 10209813) und die Transkripte **aller getesteten Tools je
Ausschnitt** (FQS-Supplement Tabellen 5/6). Damit lässt sich der Vergleich
erstmals real messen statt abzuschätzen.

## Ziel

1. Die 4 öffentlichen FQS-Audio-Ausschnitte (2 DE, 2 EN) reproduzierbar in
   den PolySchnack-Benchmark integrieren (Quelle `fqs`, neue Kategorien).
2. Alle eigenen ASR-Backends auf diesen Ausschnitten messen (WER/CER/RTF).
3. Die WER der kommerziellen Anbieter auf **denselben Ausschnitten** aus den
   publizierten Tabellen-Transkripten berechnen (nicht die 5-Minuten-
   Interviewwerte der Studie, sondern exakt die Ausschnitt-Transkripte).
4. Report-Sektion „FQS-Referenzvergleich" und Eintrag in den Decision-Log.

## Was sich für Nutzer/Entwickler ändert (Verhaltens-Delta)

- Der Benchmark (Repo `polyschnack-benchmark`) enthält ein neues Subset
  `fqs` mit 4 Samples (IDs `fqs_de_1`, `fqs_de_2`, `fqs_en_1`, `fqs_en_2`)
  inkl. Ground-Truth (manuelle Referenztranskripte der Studie).
- `python benchmark run` misst dieses Subset wie jede andere Kategorie mit;
  der Report zeigt zusätzlich eine eigene Sektion **„FQS-Referenzvergleich"**:
  je Backend WER/CER/RTF auf den Ausschnitten, daneben die auf identischem
  Audio berechneten WER der kommerziellen Anbieter (Amberscript, Dragon,
  F4x, Happy Scribe, NVivo, Otter, Sonix, Trint, Whisper) — klar markiert
  als „externe Daten, Tools von 2022, identisches Audio".
- Die Ergebnisse fließen als ASR-Evidenz in
  `docs/component-decisions.md` (Abschnitt ASR) und in den Businessplan
  (Kapitel 3.4) ein.

## Abgrenzung / Ehrlichkeit

- Die publizierten Wortgenauigkeiten der Studie beziehen sich auf die
  **vollen 5-Minuten-Interviews** (DE 984 Wörter); öffentlich sind nur die
  **Ausschnitte** (~1,7 Min. gesamt, exakt die Passagen der Tabellen 5/6).
  Ein direkter Vergleich mit den publizierten Prozentzahlen ist daher nicht
  zulässig — der Vergleich läuft über die Ausschnitt-Transkripte.
- Die kommerziellen Transkripte stammen aus der Studie (2022); Anbieter
  haben sich seither weiterentwickelt. Der Vergleich ist eine
  **Orientierung der Modellklasse**, kein Abnahme-Kriterium.
- WER-Normalisierung: jiwer-Standard (lowercase, Satzzeichen entfernt);
  die FQS-Sonderregeln (valide Alternativschreibungen wie „2" statt
  „two") werden dokumentiert, aber nicht nachgebaut (konservativ, alle
  Systeme gleich behandelt).

## Specs-Delta

`MODIFIED` — `specs/engineering/spec.md`: neue Requirement
„FQS-Referenzvergleich" (siehe `specs/engineering/spec.md`).

## Downgrade

Entfernen der 4 Manifest-Samples + der Report-Sektion; die
Extraktions- und Download-Skripte bleiben als Doku liegen; Decision-Log-
Eintrag wird mit Quellenverweis ergänzt (kein Löschen nötig).
