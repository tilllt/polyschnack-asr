/**
 * Change 054 — Tags einer Aufnahme anzeigen/bearbeiten.
 *
 * - Anzeige: Chips (#tag), × zum Entfernen (nur mit Schreibrecht).
 * - Hinzufügen: Eingabefeld + Enter (dedup case-insensitiv, wie Backend).
 * - Persistenz: PATCH /api/recordings/{uid}/tags → Query-Invalidate
 *   (Liste + Sortierung + Tag-Filter-Chips aktualisieren sich).
 * - Fehler sind sichtbar (Toast) — keine stillen Failures.
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Plus, Loader2 } from "lucide-react";
import { fetchAllTags, updateRecordingTags } from "../api";
import { useT } from "../useLocale";
import { useToast } from "./Toasts";

interface Props {
  uid: string;
  tags?: string[];
  canEdit: boolean;
}

export function TagEditor({ uid, tags = [], canEdit }: Props) {
  const { t } = useT();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  // Change 092: Vorschlagsliste existierender Tags beim Fokus/Eintippen.
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0); // Highlight-Index (Pfeiltasten)
  const { data: allTags = [] } = useQuery({
    queryKey: ["all-tags"],
    queryFn: fetchAllTags,
    staleTime: 60_000,
    enabled: canEdit,
  });
  // Existierende Tags, die noch NICHT auf dieser Aufnahme liegen (und zum
  // Tippfilter passen) — case-insensitiv wie Backend-Dedup.
  const known = allTags.filter(
    (x) =>
      !tags.some((y) => y.toLowerCase() === x.toLowerCase()) &&
      x.toLowerCase().includes(draft.trim().toLowerCase()),
  );

  if (!tags.length && !canEdit) return null;

  async function save(next: string[]) {
    setSaving(true);
    try {
      await updateRecordingTags(uid, next);
      await qc.invalidateQueries({ queryKey: ["recordings"] });
    } catch (e) {
      toast(`${t("tag_save_error")}: ${(e as Error).message}`, "err");
    } finally {
      setSaving(false);
    }
  }

  function add() {
    const v = draft.trim();
    if (!v) return;
    if (tags.some((x) => x.toLowerCase() === v.toLowerCase())) {
      setDraft(""); // Duplikat (case-insensitiv) → still ignorieren
      return;
    }
    save([...tags, v]);
    setDraft("");
    setOpen(false);
  }

  function pick(x: string) {
    // Change 092: Vorschlag aus der Liste übernehmen.
    if (tags.some((y) => y.toLowerCase() === x.toLowerCase())) return;
    save([...tags, x]);
    setDraft("");
    setOpen(false);
    setHi(0);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHi((h) => (known.length ? Math.min(h + 1, known.length - 1) : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHi((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      if (open && known[hi]) pick(known[hi]);
      else add();
    } else if (e.key === "Escape") {
      setDraft("");
      setOpen(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1 mt-[5px]" data-testid="tag-editor">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-0.5 text-[11px] px-1.5 py-[1px] rounded-sm bg-panel2 border border-border2 text-muted leading-[1.5]"
          title={`#${tag}`}
        >
          #{tag}
          {canEdit && !saving && (
            <button
              onClick={() => save(tags.filter((x) => x !== tag))}
              className="text-muted2 hover:text-err transition-colors"
              aria-label={`${t("tag_remove")} #${tag}`}
              title={t("tag_remove")}
            >
              <X size={10} />
            </button>
          )}
        </span>
      ))}
      {canEdit && (
        <span className="inline-flex items-center gap-0.5">
          <div className="relative">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              onFocus={() => {
                setOpen(true);
                setHi(0);
              }}
              onBlur={() => setOpen(false)}
              disabled={saving}
              placeholder={t("tag_placeholder")}
              aria-label={t("tag_add")}
              className="w-[90px] text-[11px] px-1.5 py-[1px] rounded-sm bg-panel2 border border-border2 text-txt outline-none focus:border-accent placeholder:text-muted2 disabled:opacity-50"
            />
            {open && known.length > 0 && (
              <ul
                data-testid="tag-suggestions"
                className="absolute left-0 top-full z-20 mt-[2px] max-h-[140px] overflow-y-auto rounded-sm bg-panel border border-border2 shadow-lg"
              >
                {known.map((x, i) => (
                  <li key={x}>
                    <button
                      type="button"
                      onMouseDown={(e) => e.preventDefault() /* Fokus behalten → kein Blur vor dem Klick */}
                      onClick={() => pick(x)}
                      className={`block w-full text-left text-[11px] px-2 py-[3px] ${
                        i === hi
                          ? "bg-accent/20 text-txt"
                          : "text-muted hover:bg-panel2"
                      }`}
                    >
                      #{x}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button
            onClick={add}
            disabled={saving}
            className="text-muted2 hover:text-accent transition-colors disabled:opacity-50"
            title={t("tag_add")}
            aria-label={t("tag_add")}
          >
            {saving ? <Loader2 size={11} className="animate-spin" /> : <Plus size={12} />}
          </button>
        </span>
      )}
    </div>
  );
}
