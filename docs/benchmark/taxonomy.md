# 2-Achsen-Taxonomie

Die Samples sind nach zwei unabhängigen Achsen kategorisiert (Definition in
`benchmark/spec/taxonomy.json` im polyschnack-benchmark-Repo) — angelehnt an
die Best Practice echter ASR-Benchmarks (GigaSpeechBench, LibriSpeech,
REVERB, CHiME).

## Kanal (Akustik) — wie klingt die Aufnahme?

| ID | Name | Szenarien |
|----|------|-----------|
| `clean` | Clean / Studio | clean |
| `transport` | Transport | flugzeug, hubschrauber, oepnv, auto |
| `broadcast` | Broadcast / Medien | radio, film |
| `telefon` | Telefon | telefon |
| `komprimiert` | Codec / Komprimiert | komprimiert |
| `vintage` | Vintage / historische Tonträger | schallplatte, tonband, historisch |
| `geraeusch` | Geräusch / Umwelt | strassenlaerm, babble |
| `nachhall` | Nachhall (Reverb) | hall |

## Inhalt (Schwierigkeit) — was wird gesprochen?

| ID | Name | Szenarien |
|----|------|-----------|
| `allgemein` | Allgemein | clean |
| `schnell` | Schnelles Sprechen | schnell |
| `zahlen` | Zahlen & Codes | zahlen |
| `fachsprache` | Fachsprache | medizin, jura |
| `akzent` | Akzente | akzent |
| `jugend` | Jugendstimmen | kinder → jugend |
| `codeswitch` | Sprachmischung (Code-Switch) | mixed |
| `durchsagen` | Durchsagen (PA) | pa |

## Quelle (Tag, keine Kategorie)

- `cv` = echte CommonVoice-Stimmen (CC0)
- `tts` = synthetisch (**Piper** Thorsten m / Ramona w — ersetzt edge-tts,
  Regenerationsskript `benchmark/scripts/regenerate_tts_piper.py`)

## Warum 2 Achsen?

Echte ASR-Benchmarks kategorisieren nicht flach („Hubschrauber", „ÖPNV"),
sondern nach **akustischer Umgebung** (wie klingt es?) und
**Sprech-Inhalt** (was wird gesprochen?). Das macht die Ergebnisse
aussagekräftig: Ein Backend kann bei Clean hervorragend sein, bei Transport
aber versagen — die Matrix macht solche Stärken/Schwächen sichtbar.
