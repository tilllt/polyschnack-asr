"""ASS-Caption-Generator (Change 193): Wort-Timings → .ass-Dokument.

Datenfluss:

1. :func:`extract_words` — flacht ``recording.segments[*].words[]`` zu einer
   monotonen Wortliste ab (gleiche Invarianten wie der Timing-Editor:
   ``start >= voriges Ende``, ``ende > start``).
2. :func:`build_lines` — gruppiert Wörter zu Caption-Zeilen
   (``words_per_line``, Sprecherwechsel, Satzende).
3. :func:`build_steps` — zerlegt jede Zeile in Schritte (ein Schritt pro
   hervorgehobenem Wort); jeder Schritt ist ein ASS-``Dialogue``-Event.
4. Vorlage rendern (``presets/<name>.ass.j2``) — die Vorlage entscheidet,
   ob sie ``lines`` (ganze Zeile) oder ``steps`` (Wort-Hervorhebung) malt.

Zeitbasis: alles intern in Millisekunden, ASS bekommt ``h:mm:ss.cc``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import fitwidth, textfit
from .presets import (
    POSITION_ALIGNMENT,
    COLOR_PARAMS,
    Preset,
    load_preset,
)
from .template_engine import (
    AssTemplateError,
    ass_color,
    render_preset_file,
    tc,
)

#: Kürzestes Event (ASS rechnet in Zentisekunden → unter 10 ms gibt es nichts).
MIN_EVENT_MS = 20
#: Wortzeiten ab hier gelten als echt; kürzere sind Fallback-Artefakte der UI.
MIN_WORD_MS = 80
#: Satzzeichen, nach denen eine Caption-Zeile enden darf.
SENTENCE_END = ".!?…:;"

#: Schriftgrößen-Tag ``{\fs108}`` im Event-Text (Change 202). Bewusst mit Ziffer:
#: ``\fscx`` und ``\fscy`` sind Skalierungen und keine Schriftgrößen.
_FS_TAG_RE = re.compile(r"\\fs\d+")

GENERATOR = "PolySchnack ASS-Export (Change 193)"


class NoWordTimestamps(Exception):
    """Keine brauchbaren Wortzeiten im Recording (→ HTTP 409)."""


@dataclass
class Word:
    """Ein Wort mit (auf Monotonie normalisierter) Zeit."""

    index: int
    text: str
    start_ms: int
    end_ms: int
    speaker: str
    segment_index: int
    real_timing: bool

    @property
    def dur_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


@dataclass
class Step:
    """Ein Hervorhebungs-Schritt: Fenster + aktives Wort."""

    index: int
    line_index: int
    active: int
    start_ms: int
    end_ms: int


@dataclass
class Line:
    """Eine Caption-Zeile (Fenster von Wörtern) inkl. Event-Zeit und Schritten."""

    index: int
    words: List[Word]
    start_ms: int
    end_ms: int
    steps: List[Step] = field(default_factory=list)

    @property
    def speaker(self) -> str:
        return self.words[0].speaker if self.words else ""

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class AssResult:
    """Ergebnis eines ASS-Exports."""

    content: str
    filename: str
    preset: str
    params: Dict[str, Any]
    timing: str  # "real" | "mixed"
    words: int
    lines: int
    steps: int
    duration_ms: int
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _to_ms(value: Any) -> Optional[int]:
    """Sekunden (float/int, wie in der App) → Millisekunden; None bei Unbrauchbarem."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(round(float(value) * 1000.0))
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str:
    """Wort-Text ausräumen: Whitespace normalisieren, nichts erfinden."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def clean_speaker(value: Any) -> str:
    """Sprecher-Label für die ASS-Name-Spalte (Komma würde die Zeile zerreissen)."""
    if value is None:
        return ""
    return " ".join(str(value).replace(",", " ").split())


def _raw_segment_words(segment: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Wörter eines Segments als ``[{"text", "start_s", "end_s"}]``."""
    out: List[Dict[str, Any]] = []
    for entry in segment.get("words") or []:
        if not isinstance(entry, dict):
            continue
        text = _clean_text(entry.get("text") or entry.get("word"))
        if not text:
            continue
        out.append({
            "text": text,
            "start_s": entry.get("start"),
            "end_s": entry.get("end"),
        })
    if not out:
        # Segment ohne Wortliste: Text zerlegen (kein Timing → Fallback unten).
        text = _clean_text(segment.get("text"))
        if text:
            out = [{"text": tok, "start_s": None, "end_s": None}
                   for tok in text.split()]
    return out


def _distribute(words: List[Dict[str, Any]], start_ms: int, end_ms: int) -> None:
    """Verteilt Wörter ohne Zeit gleichmässig über [start_ms, end_ms] (in place)."""
    n = len(words)
    if n == 0:
        return
    span = max(end_ms - start_ms, MIN_EVENT_MS * n)
    for i, w in enumerate(words):
        w["start_ms"] = start_ms + int(round(span * i / n))
        w["end_ms"] = start_ms + int(round(span * (i + 1) / n))


# ---------------------------------------------------------------------------
# Aufbau
# ---------------------------------------------------------------------------


def extract_words(segments: Sequence[Dict[str, Any]]) -> tuple:
    """Baut die Wortliste; gibt ``(words, stats)`` zurück.

    ``stats``: ``{"real": n, "distributed": n, "skipped_segments": n}``.

    Fallback-Regel (bewusst konservativ):

    * Wörter MIT Zeit bleiben, wie sie sind (nur Monotonie geklemmt).
    * Wörter OHNE Zeit erben den Zwischenraum ihrer zeitlich bekannten
      Nachbarn bzw. die Segmentgrenzen — gleichmässig verteilt. Das passiert
      NUR, wenn das Recording überhaupt echte Wortzeiten hat (Mischfall).
    * Ein Segment ohne jede Zeitangabe (weder Wörter noch Segment) wird
      ausgelassen und gezählt (``skipped_segments``), statt zu raten.
    * Hat das Recording *nirgends* eine echte Wortdauer, wird gar nicht
      gerechnet: :class:`NoWordTimestamps` (→ 409, „zuerst alignen"). Ein
      Transkript nur mit Segmentzeiten würde sonst mit erfundenen Wortzeiten
      exportiert — genau das soll der Export nicht tun.
    """
    segments = list(segments or [])
    if not has_real_word_timings(segments):
        raise NoWordTimestamps("recording has no valid word timings")

    words: List[Word] = []
    distributed = skipped_segments = skipped_words = 0
    prev_end = 0

    for seg_index, segment in enumerate(segments or []):
        if not isinstance(segment, dict):
            continue
        raw = _raw_segment_words(segment)
        if not raw:
            continue
        speaker = clean_speaker(segment.get("speaker"))
        seg_start = _to_ms(segment.get("start"))
        seg_end = _to_ms(segment.get("end"))

        # Zeiten einsammeln; unvollständige Paare gelten als "ohne Zeit".
        for w in raw:
            s, e = _to_ms(w.get("start_s")), _to_ms(w.get("end_s"))
            ok = s is not None and e is not None and e > s
            w["start_ms"], w["end_ms"] = (s, e) if ok else (None, None)
            w["real"] = ok

        if not any(w["real"] for w in raw):
            if seg_start is None or seg_end is None or seg_end <= seg_start:
                skipped_segments += 1
                continue
            _distribute(raw, seg_start, seg_end)
            distributed += len(raw)
        elif not all(w["real"] for w in raw):
            # Lücken zwischen zeitlich bekannten Nachbarn gleichmässig füllen.
            index = 0
            while index < len(raw):
                if raw[index]["real"]:
                    index += 1
                    continue
                run_start = index
                while index < len(raw) and not raw[index]["real"]:
                    index += 1
                run = raw[run_start:index]
                left = raw[run_start - 1]["end_ms"] if run_start > 0 else seg_start
                right = raw[index]["start_ms"] if index < len(raw) else seg_end
                if left is None and right is None:
                    for w in run:  # nirgends verankert → nicht raten
                        w["start_ms"] = w["end_ms"] = None
                    skipped_words += len(run)
                    continue
                if left is None:
                    left = max(0, int(right or 0) - MIN_WORD_MS * len(run))
                if right is None or int(right) <= int(left):
                    right = int(left) + MIN_WORD_MS * len(run)
                _distribute(run, int(left), int(right))
                distributed += len(run)

        for w in raw:
            if w["start_ms"] is None or w["end_ms"] is None:
                skipped_words += 1
                continue
            start = max(int(w["start_ms"]), prev_end)
            end = max(int(w["end_ms"]), start + 1)
            prev_end = end
            words.append(Word(
                index=len(words),
                text=w["text"],
                start_ms=start,
                end_ms=end,
                speaker=speaker,
                segment_index=seg_index,
                real_timing=bool(w["real"]),
            ))

    return words, {
        "real": sum(1 for w in words if w.real_timing),
        "distributed": distributed,
        "skipped_segments": skipped_segments,
        "skipped_words": skipped_words,
    }


def has_real_word_timings(segments: Sequence[Dict[str, Any]]) -> bool:
    """Mindestens ein Wort mit echter Dauer (``end > start``) im Recording?"""
    for segment in segments or []:
        if not isinstance(segment, dict):
            continue
        for entry in segment.get("words") or []:
            if not isinstance(entry, dict):
                continue
            s, e = _to_ms(entry.get("start")), _to_ms(entry.get("end"))
            if s is not None and e is not None and e > s:
                return True
    return False


def build_lines(words: Sequence[Word], words_per_line: int,
                sentence_breaks: bool = True,
                measure: Optional[Callable[[str], float]] = None,
                available: float = 0.0) -> List[Line]:
    """Gruppiert Wörter zu Caption-Zeilen.

    *measure* entscheidet über den Umbruch:

    * ``None`` — wie bisher nach **fester Wortzahl** (``words_per_line``).
    * gesetzt — nach **Breite** ausbalanciert (``fit_mode="balanced"``, siehe
      *available*):
      ``words_per_line`` bleibt Obergrenze je Zeile, die Zeilen werden aber
      möglichst gleich breit, damit eine gemeinsame Schriftgröße sie alle
      ausfüllt. Die Messfunktion liefert Breiten in PlayRes-Pixeln und
      berücksichtigt Großschreibung und fette Schrift.

    Harte Grenzen gelten in beiden Fällen: Segmentwechsel, Sprecherwechsel und
    (wenn eingeschaltet) das Satzende.
    """
    # Erst die Blöcke zwischen den harten Grenzen bilden …
    blocks: List[List[Word]] = []
    current: List[Word] = []
    for word in words:
        if current:
            prev = current[-1]
            new_segment = word.segment_index != prev.segment_index
            new_speaker = word.speaker != prev.speaker
            full = len(current) >= words_per_line
            sentence_done = (
                sentence_breaks and len(current) >= 2
                and prev.text.rstrip()[-1:] in SENTENCE_END
            )
            if new_segment or new_speaker or full or sentence_done:
                blocks.append(current)
                current = []
        current.append(word)
    if current:
        blocks.append(current)

    # … dann jeden Block in Zeilen teilen.
    lines: List[Line] = []
    for block in blocks:
        if measure is None:
            groups: List[List[Word]] = [
                block[i:i + words_per_line] for i in range(0, len(block), words_per_line)
            ]
        else:
            widths = []
            for k, word in enumerate(block):
                breite = measure(word.text)
                if k + 1 < len(block):
                    breite += measure(" ")      # Leerzeichen zählt zur Zeile
                widths.append(breite)
            groups = [[block[j] for j in group]
                      for group in fitwidth.balanced_split(widths, words_per_line, available)]
        for group in groups:
            lines.append(Line(index=len(lines), words=group, start_ms=0, end_ms=0))
    return lines


def apply_timing(lines: List[Line], lead_ms: int, tail_ms: int) -> int:
    """Setzt Event-Zeiten (inkl. Vorlauf/Nachlauf) und baut die Schritte.

    Invarianten (getestet):

    * Events derselben Ebene überlappen nie (jede Zeile endet spätestens dort,
      wo die nächste sichtbar wird).
    * ``end > start`` für jedes Event; Starts monoton nicht fallend.
    * Die ``\\k``/``\\kf``-Dauern einer Zeile summieren sich exakt auf die
      Event-Dauer (Karaoke bleibt synchron).
    """
    lead = max(0, int(lead_ms))
    tail = max(0, int(tail_ms))
    prev_end = 0

    for idx, line in enumerate(lines):
        first, last = line.words[0], line.words[-1]
        start = max(0, first.start_ms - lead)
        start = max(start, prev_end)
        next_start = None
        if idx + 1 < len(lines):
            next_first = lines[idx + 1].words[0]
            next_start = max(0, next_first.start_ms - lead)
        end = last.end_ms + tail
        if next_start is not None:
            end = min(end, max(next_start, last.end_ms))
        end = max(end, start + MIN_EVENT_MS)
        line.start_ms, line.end_ms = start, end

        steps: List[Step] = []
        step_start = start
        for i, word in enumerate(line.words):
            step_end = (line.words[i + 1].start_ms
                        if i + 1 < len(line.words) else end)
            step_end = max(step_end, step_start + MIN_EVENT_MS)
            if i + 1 < len(line.words):
                step_end = min(step_end, max(line.words[i + 1].start_ms,
                                             step_start + MIN_EVENT_MS))
            steps.append(Step(index=i, line_index=idx, active=i,
                              start_ms=step_start, end_ms=step_end))
            step_start = step_end
        line.steps = steps
        prev_end = line.end_ms
    return prev_end


# ---------------------------------------------------------------------------
# Template-Kontext
# ---------------------------------------------------------------------------


def _word_view(word: Word, params: Dict[str, Any], span_ms: int,
               active: Optional[int] = None) -> Dict[str, Any]:
    """Template-Ansicht eines Wortes (reine Daten, keine Python-Objekte).

    ``k_cs`` ist die Karaoke-Dauer in **Zentisekunden** (ASS-Zeitbasis) —
    nicht in Millisekunden; ein Faktor-10-Fehler dort lässt den Farbbalken
    zehnmal zu langsam laufen.
    """
    text = word.text.upper() if params.get("uppercase") else word.text
    view: Dict[str, Any] = {
        "index": word.index,
        "text": text,
        "start_ms": word.start_ms,
        "end_ms": word.end_ms,
        "dur_ms": word.dur_ms,
        "k_cs": max(1, int(round(max(int(span_ms), 10) / 10.0))),
        "dur_cs": max(1, int(round(word.dur_ms / 10.0))),
        "speaker": word.speaker,
    }
    if active is not None:
        view["is_active"] = word.index == active
        view["is_past"] = word.index < active
        view["is_future"] = word.index > active
    return view


def _line_context(line: Line, params: Dict[str, Any],
                  font_size: int = 0) -> Dict[str, Any]:
    """Zeilen-Kontext inkl. ``\\k``-Dauern und ``\\fs``-Tag.

    Karaoke-Regel: ``k_cs`` eines Wortes ist der Abstand bis zum nächsten Wort
    (der letzte bekommt seine ECHTE Wortdauer). Damit füllt sich der letzte
    Balken genau beim Sprechen und bleibt danach gefüllt, statt sich in den
    Nachlauf hinein zu ziehen. Die Summe ist deshalb ``<=`` Event-Dauer und
    exakt gleich, wenn kein Nachlauf (``tail_ms=0``) anfällt.

    *font_size* (Change 202) ist die Größe **dieser** Zeile; sie wird als
    fertiger ``fs_tag`` an Vorlage und Schritt gereicht (``0`` → leerer Tag,
    dann greift der Stil wie bisher).
    """
    words = line.words
    fs_tag = font_size_tag(font_size)

    def span(i: int) -> int:
        word = words[i]
        if i + 1 < len(words):
            value = words[i + 1].start_ms - word.start_ms
        else:
            value = word.end_ms - word.start_ms
        if i == 0:
            # Karaoke-Fill beginnt mit dem Event (inkl. Vorlauf).
            value += max(0, word.start_ms - line.start_ms)
        return max(value, 10)

    views: List[Dict[str, Any]] = [
        _word_view(word, params, span(i)) for i, word in enumerate(words)
    ]
    step_views: List[Dict[str, Any]] = []
    for step in line.steps:
        active_index = words[step.active].index
        step_views.append({
            "index": step.index,
            "line_index": line.index,
            "active_index": step.active,
            "start_ms": step.start_ms,
            "end_ms": step.end_ms,
            "start_tc": tc(step.start_ms),
            "end_tc": tc(step.end_ms),
            "speaker": line.speaker,
            "fs_tag": fs_tag,
            "text": line.text.upper() if params.get("uppercase") else line.text,
            "words": [
                _word_view(word, params, span(i), active=active_index)
                for i, word in enumerate(words)
            ],
        })
    return {
        "index": line.index,
        "start_ms": line.start_ms,
        "end_ms": line.end_ms,
        "start_tc": tc(line.start_ms),
        "end_tc": tc(line.end_ms),
        "speaker": line.speaker,
        "fs_tag": fs_tag,
        "text": line.text.upper() if params.get("uppercase") else line.text,
        "words": views,
        "steps": step_views,
    }


#: Seitliche Raender des ASS-Stils. Die Breitenmessung zieht sie ab —
#: deshalb stehen sie hier EINMAL und nicht zweimal im Code.
STYLE_MARGIN_L = 40
STYLE_MARGIN_R = 40


def _styles(preset: Preset, params: Dict[str, Any],
            warnings: List[str]) -> List[Dict[str, Any]]:
    """ASS-Stile aus den Parametern (Farb-Rollen kommen aus dem Preset)."""
    def source(key: str, fallback: str) -> str:
        name = preset.style_map.get(key, fallback)
        if name not in COLOR_PARAMS:
            warnings.append(f"preset_style_source_invalid:{key}={name}")
            return fallback
        return name

    box = bool(params["box"])
    margin_l, margin_r = _style_margins(params)
    return [{
        "name": "Default",
        "fontname": params["font_name"],
        "fontsize": params["font_size"],
        # Karaoke braucht Primär = "gesungen", Sekundär = "noch nicht gesungen".
        "primary": ass_color(params[source("primary", "text_color")]),
        "secondary": ass_color(params[source("secondary", "accent_color")]),
        "outline": ass_color(params["outline_color"]),
        "back": ass_color(params["outline_color"], alpha=128 if box else 0),
        "bold": -1 if params["bold"] else 0,
        "italic": 0,
        "underline": 0,
        "strikeout": 0,
        "scale_x": 100,
        "scale_y": 100,
        "spacing": 0,
        "angle": 0,
        "border_style": 3 if box else 1,
        "outline_px": params["outline_width"],
        "shadow": params["shadow"],
        "alignment": POSITION_ALIGNMENT[params["position"]],
        "margin_l": margin_l,
        "margin_r": margin_r,
        "margin_v": params["margin_v"],
        "encoding": 1,
    }]


def _uniform_timing(words: Sequence[Word]) -> bool:
    """Gleichverteilungs-Signatur (Fallback-Artefakt, siehe Timing-Editor).

    Bei mechanisch verteilten Wortzeiten gibt es nur ein oder zwei
    verschiedene Wortabstände — echte Alignment-Daten streuen.
    """
    if len(words) < 5:
        return False
    deltas = {round((words[i + 1].start_ms - words[i].start_ms) / 100.0, 2)
              for i in range(len(words) - 1)}
    return len(deltas) <= 2


def textfit_extra_px(params: Dict[str, Any]) -> float:
    """Kontur-/Schatten-Zuschlag (eine Quelle: ``textfit``)."""
    return textfit.extra_px(params)


def _style_margins(params: Dict[str, Any]) -> Tuple[int, int]:
    """Seitliche Ränder des ASS-Stils aus ``safe_margin_pct`` (Change 202).

    ``safe_margin_pct`` ist der Sicherheitsrand in Prozent **je Seite**. Die
    Ränder waren vor Change 202 fest 40 px; ``max(40, …)`` hält diesen Stand
    bei ``safe_margin_pct=0`` exakt fest, damit sich am Bestand nichts
    verschiebt.
    """
    pct = float(params.get("safe_margin_pct", 0) or 0)
    play_res_x = float(params.get("play_res_x", 1920) or 1920)
    rand = int(round(play_res_x * max(0.0, pct) / 100.0))
    return max(STYLE_MARGIN_L, rand), max(STYLE_MARGIN_R, rand)


def _available_width(params: Dict[str, Any]) -> float:
    """Breite, die eine Zeile belegen darf — mit den Rändern des ASS-Stils."""
    margin_l, margin_r = _style_margins(params)
    return textfit.available_width({**params,
                                    "margin_l": margin_l,
                                    "margin_r": margin_r})


def _available_height(params: Dict[str, Any]) -> float:
    """Höhe, die die Tinte einer einzelnen Zeile belegen darf (Change 202).

    Von unten begrenzt der Abstand ``margin_v`` (dort sitzt die Grundlinie),
    von oben der Sicherheitsrand. Die Tinte wächst beim Vergrößern nach oben —
    ohne diese Grenze liefe ein einzelnes kurzes Wort aus dem Bild.
    """
    play_res_y = float(params.get("play_res_y", 1080) or 1080)
    pct = float(params.get("safe_margin_pct", 0) or 0)
    oben = play_res_y * max(0.0, pct) / 100.0
    frei = play_res_y - float(params.get("margin_v", 0) or 0) - oben
    frei -= textfit_extra_px(params)
    return max(1.0, frei)


def _measure(params: Dict[str, Any],
             warnings: List[str]) -> Optional[Tuple[Callable[[str], float],
                                                    Callable[[str], float]]]:
    """Messfunktionen ``(breite, hoehe)`` in PlayRes-Pixeln — oder ``None``.

    Gemessen wird nur, wenn ein Modus mit Schriftanpassung gewählt ist. Kann
    nicht gemessen werden (Pillow oder fontconfig fehlt), wird das GEMELDET
    (``fit_unavailable``) und es bleibt bei der festen Größe — statt still auf
    eine geratene Zahl auszuweichen.

    Die **Höhe** (Change 202) ist die Grenze nach oben im Modus ``per_line``.
    Eine feste Zahl ginge nicht: gemessen bei 200 px Schriftgröße reicht die
    Tinte von 127 px („WEG") bis 192 px („ÄÖÜgjpqy").
    """
    if str(params.get("fit_mode", "off")) not in ("balanced", "per_line"):
        return None

    fehlt: List[str] = []
    if not textfit.available(fehlt):
        warnings.append("fit_unavailable:" + ",".join(fehlt))
        return None

    font_name = str(params.get("font_name", ""))
    bold = bool(params.get("bold"))
    upper = bool(params.get("uppercase"))
    if textfit.text_width("M", font_name=font_name, bold=bold) is None:
        warnings.append("fit_unavailable:font")
        return None

    def prepare(text: str) -> str:
        return text.upper() if upper else text

    #: Höhe der Zeilenbox — sie ist die Grenze, nicht die Tinte: libass
    #: reserviert Auf- + Abstieg (Liberation Sans ≈ 1,14 em). Mit der Tinte
    #: („ist" = 0,78 em) als Grenze wurde die Zeile oben abgeschnitten.
    box = textfit.line_box_height(font_name=font_name, bold=bold) or 0.0

    def breite(text: str) -> float:
        return float(textfit.text_width(prepare(text), font_name=font_name,
                                       bold=bold) or 0.0)

    def hoehe(text: str) -> float:
        tinte = float(textfit.text_height(prepare(text), font_name=font_name,
                                         bold=bold) or 0.0)
        return max(tinte, box)

    return breite, hoehe


def _width_measure(params: Dict[str, Any],
                   warnings: List[str]) -> Optional[Callable[[str], float]]:
    """Nur die Breitenmessung (Change 201) — ``None``, wenn nicht messbar."""
    messung = _measure(params, warnings)
    return messung[0] if messung else None


def _fit_font_size(lines: Sequence[Line], params: Dict[str, Any],
                   measure: Callable[[str], float],
                   warnings: List[str]) -> Dict[str, Any]:
    """Berechnet die Schriftgröße, die die Bildschirmbreite ausfüllt.

    Eine Größe für den ganzen Export: die breiteste Zeile füllt die verfügbare
    Breite, begrenzt auf 0,5×…3× der eingestellten Größe. Passt eine Zeile
    selbst dann nicht, wird das gemeldet (``fit_overflow:<n>``) — sie wird
    nicht stillschweigend über den Rand geschrieben.
    """
    leer = measure(" ")
    breiten: List[float] = []
    for line in lines:
        if not line.words:
            continue
        breite = sum(measure(word.text) for word in line.words) + leer * (len(line.words) - 1)
        breiten.append(breite)

    verfuegbar = _available_width(params)
    groesse, ueberlauf = fitwidth.font_size_for(verfuegbar, breiten, params["font_size"])
    if ueberlauf:
        warnings.append(f"fit_overflow:{ueberlauf}")
    # Die wirksame Größe tritt an die Stelle der eingestellten: so zeigen
    # ASS-Kopf, Stil und Antwort dieselbe Zahl (keine zwei Wahrheiten).
    return {**params, "font_size": groesse}


def _per_line_font_sizes(lines: Sequence[Line], params: Dict[str, Any],
                         messung: Tuple[Callable[[str], float],
                                        Callable[[str], float]],
                         warnings: List[str]) -> Dict[int, int]:
    """Schriftgröße **je Zeile** (Change 202) — Zeilen-Index → Größe.

    Anders als bei ``balanced`` bleibt die Zeilenbildung bei der eingestellten
    Wortzahl; nur die Größe unterscheidet sich von Zeile zu Zeile. Die
    eingestellte ``font_size`` bleibt im Stil stehen (Untergrenze/Richtung),
    jede Zeile bekommt ihren eigenen ``{\\fs…}``-Tag in den Event-Text.
    """
    breite, hoehe = messung
    breiten: List[float] = []
    hoehen: List[float] = []
    for line in lines:
        text = line.text
        breiten.append(max(0.0, breite(text)))
        hoehen.append(max(0.0, hoehe(text)))

    groessen, ueberlauf = fitwidth.per_line_sizes(
        _available_width(params), _available_height(params),
        breiten, hoehen, params["font_size"])
    if ueberlauf:
        warnings.append(f"fit_overflow:{ueberlauf}")
    return {line.index: groesse for line, groesse in zip(lines, groessen)}


def font_size_tag(groesse: int) -> str:
    """``{\\fs108}`` für den Anfang eines Event-Textes; leer, wenn keine Größe.

    Der Tag steht im Text und nicht im Stil: der Stil gilt für alle Events,
    die Größe soll sich aber von Zeile zu Zeile unterscheiden.
    """
    return f"{{\\fs{int(groesse)}}}" if groesse else ""


def generate_ass(recording: Any, preset_name: str = "highlight",
                 overrides: Optional[Dict[str, Any]] = None) -> AssResult:
    """Erzeugt eine ``.ass``-Datei für *recording*.

    *recording* ist duck-typed: gebraucht werden ``segments`` und optional
    ``original_name`` (Dateiname/Titel). Wirft :class:`NoWordTimestamps`,
    :class:`PresetNotFound`, :class:`ParamError` oder :class:`AssTemplateError`.
    """
    preset = load_preset(preset_name)
    params = preset.resolve(overrides)

    segments = getattr(recording, "segments", None) or []
    words, stats = extract_words(segments)
    if not words:
        raise NoWordTimestamps("recording has no usable word timings")

    warnings: List[str] = []

    # Schriftgröße an die Bildschirmbreite anpassen? Change 201 ("balanced":
    # Zeilen nach Breite ausbalanciert, EINE Größe aus der breitesten Zeile)
    # bzw. Change 202 ("per_line": Zeilen bleiben bei der eingestellten
    # Wortzahl, Größe JE ZEILE aus Breite und Höhe — die Größe springt).
    fit_mode = str(params.get("fit_mode", "off"))
    messung = _measure(params, warnings)
    if messung is None:
        fit_mode = "off"  # ohne Messung bleibt es bei der festen Größe
    verfuegbare_breite = _available_width(params) if messung is not None else 0.0
    breite_messen = messung[0] if messung is not None else None
    lines = build_lines(words, params["words_per_line"],
                        params["sentence_breaks"],
                        measure=breite_messen if fit_mode == "balanced" else None,
                        available=verfuegbare_breite)
    line_sizes: Dict[int, int] = {}
    if fit_mode == "balanced" and messung is not None:
        params = _fit_font_size(lines, params, messung[0], warnings)
    elif fit_mode == "per_line" and messung is not None:
        line_sizes = _per_line_font_sizes(lines, params, messung, warnings)
    duration_ms = apply_timing(lines, params["lead_ms"], params["tail_ms"])
    if stats["distributed"]:
        warnings.append("fallback_timing_words")
    if stats["skipped_segments"]:
        warnings.append(f"skipped_segments:{stats['skipped_segments']}")
    if _uniform_timing(words):
        warnings.append("uniform_timing")
    timing = "mixed" if stats["distributed"] else "real"

    title = _clean_text(str(getattr(recording, "original_name", "") or ""))
    title = title.rsplit(".", 1)[0] or "captions"

    line_context = [_line_context(line, params, line_sizes.get(line.index, 0))
                    for line in lines]

    context = {
        "meta": {
            "title": title,
            "generator": GENERATOR,
            "preset": preset.name,
            "preset_title": preset.title,
            "play_res_x": params["play_res_x"],
            "play_res_y": params["play_res_y"],
            "duration_ms": duration_ms,
            "timing": timing,
        },
        "params": params,
        "styles": _styles(preset, params, warnings),
        "lines": line_context,
        "steps": [step for lc in line_context for step in lc["steps"]],
        "counts": {
            "words": len(words),
            "lines": len(lines),
            "steps": sum(len(line.steps) for line in lines),
        },
    }
    content = render_preset_file(preset.template_file, context)
    if line_sizes:
        # Ausgabe prüfen, nicht die Absicht: eine Vorlage ohne den Platzhalter
        # `line.fs_tag`/`st.fs_tag` würde die berechnete Größe stillschweigend
        # fallen lassen. \fs<zahl> suchen — "\fscx" ist eine Skalierung und
        # darf nicht als Schriftgröße durchgehen.
        events = [ln for ln in content.splitlines() if ln.startswith("Dialogue:")]
        ohne = [ln for ln in events if not _FS_TAG_RE.search(ln)]
        if ohne:
            warnings.append(f"fit_tag_missing:{preset.name}")
    return AssResult(
        content=content,
        filename=f"{title}.ass",
        preset=preset.name,
        params=params,
        timing=timing,
        words=len(words),
        lines=len(lines),
        steps=context["counts"]["steps"],
        duration_ms=duration_ms,
        warnings=warnings,
    )
