"""Change 228 — KI-Formatierung: eingebaute Vorgaben der zweiten LLM-Stufe.

Die Formatierung formt den (ggf. schon geglätteten) Text um — etwa in ein
stichwortartiges Protokoll. Sie ist bewusst eine eigene Stufe: der Wortlaut
stimmt danach nicht mehr mit dem Audio überein. Deshalb steht das Ergebnis in
einem eigenen Textbereich unter dem Transkript und trägt eine Herkunftsangabe
(``Recording.formatted_source``).

Jede Vorgabe trägt dieselbe Schranke: nur umformen, nichts hinzuerfinden.
Ohne diesen Zusatz neigen Modelle dazu, Namen, Zahlen oder Beschlüsse zu
ergänzen, die im Transkript nicht vorkommen — das wäre erfunden.
"""
from __future__ import annotations

from typing import Any, Optional

#: Schranke am Ende jedes Prompts (Provenienz: nichts erfinden).
GUARD = (
    "Regeln: Erfinde nichts. Ergänze keine Fakten, Namen, Zahlen oder "
    "Beschlüsse, die nicht im Text stehen. Behalte die Sprache des Textes bei. "
    "Antworte ausschließlich mit dem Ergebnis — ohne Einleitung, ohne Hinweis "
    "auf diese Anweisung und ohne Rückfrage."
)

#: Eingebaute Vorgaben. Reihenfolge = Reihenfolge in der Auswahl.
PRESETS: list[dict[str, Any]] = [
    {
        "key": "protocol",
        "label": {"de": "Stichwort-Protokoll", "en": "Bullet-point minutes",
                  "pt": "Ata em tópicos"},
        "note": {
            "de": "Gliedert den Text in Abschnitte mit knappen Überschriften und "
                  "Stichpunkten. Aussagen, Reihenfolge und Wortwahl der Inhalte "
                  "bleiben erhalten — es wird nur umgeformt.",
            "en": "Turns the text into sections with short headings and bullets. "
                  "Statements, order and wording stay — nothing is invented.",
            "pt": "Divide o texto em secções com títulos curtos e tópicos. As "
                  "afirmações e a ordem mantêm-se — nada é inventado.",
        },
        "prompt": (
            "Forme den folgenden Text in ein stichwortartiges Protokoll um. "
            "Gliedere ihn in Abschnitte mit kurzen Überschriften und Stichpunkten. "
            "Behalte Reihenfolge und Aussagen bei; kürze nur, was für das "
            "Verständnis entbehrlich ist. "
        ),
    },
    {
        "key": "summary",
        "label": {"de": "Zusammenfassung", "en": "Summary", "pt": "Resumo"},
        "note": {
            "de": "Fasst die Kernaussagen in wenigen Absätzen zusammen. "
                  "Nebensächliches fällt weg — Details gehen damit verloren.",
            "en": "Condenses the key statements into a few paragraphs. Details are "
                  "dropped in the process.",
            "pt": "Resume as afirmações centrais em poucos parágrafos. Os detalhes "
                  "perdem-se no processo.",
        },
        "prompt": (
            "Fasse den folgenden Text in wenigen Absätzen zusammen. Gib die "
            "Kernaussagen wieder und lass Nebensächliches weg. Nenne die "
            "wichtigsten Namen, Zahlen und Ergebnisse, sofern sie im Text stehen. "
        ),
    },
    {
        "key": "tasks",
        "label": {"de": "Aufgaben und Beschlüsse", "en": "Tasks and decisions",
                  "pt": "Tarefas e decisões"},
        "note": {
            "de": "Stellt nur Aufgaben, Beschlüsse und offene Punkte zusammen — "
                  "je Punkt knapp, mit der genannten Person, sofern sie im Text "
                  "vorkommt. Zuständigkeiten werden nicht erfunden.",
            "en": "Collects only tasks, decisions and open points — short, with the "
                  "person named in the text, if any. Nothing is invented.",
            "pt": "Reúne apenas tarefas, decisões e pontos em aberto — curtos, com a "
                  "pessoa mencionada no texto, se existir. Nada é inventado.",
        },
        "prompt": (
            "Arbeite aus dem folgenden Text die Aufgaben, Beschlüsse und offenen "
            "Punkte heraus. Gib sie als knappe Liste wieder und nenne die im Text "
            "genannte Person oder Stelle, sofern sie vorkommt. Wenn zu einem Punkt "
            "niemand genannt ist, schreibe nichts dazu. "
        ),
    },
]

#: Vorgabe, wenn der Nutzer keine eigene Vorlage wählt.
DEFAULT_PRESET = "protocol"


def preset(key: Optional[str]) -> dict[str, Any]:
    """Vorgabe zur Kennung — unbekannte Kennung fällt auf die Vorgabe zurück."""
    for p in PRESETS:
        if p["key"] == key:
            return p
    return next(p for p in PRESETS if p["key"] == DEFAULT_PRESET)


def build_prompt(preset_key: Optional[str] = None,
                 template_prompt: Optional[str] = None) -> str:
    """Prompt der Formatierungsstufe.

    Eine eigene Vorlage des Nutzers schlägt die eingebaute Vorgabe; die
    Schranke (``GUARD``) hängt in beiden Fällen an, damit auch eigene Vorlagen
    nichts hinzuerfinden.
    """
    if template_prompt and template_prompt.strip():
        return f"{template_prompt.strip()}\n\n{GUARD}"
    return f"{preset(preset_key)['prompt']}{GUARD}"


def preset_list() -> list[dict[str, Any]]:
    """Vorgaben für die Oberfläche (ohne Prompt-Fließtext)."""
    return [{"key": p["key"], "label": p["label"], "note": p["note"]}
            for p in PRESETS]
