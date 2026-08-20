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
import { useQueryClient } from "@tanstack/react-query";
import { X, Plus, Loader2 } from "lucide-react";
import { updateRecordingTags } from "../api";
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
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") add();
              if (e.key === "Escape") setDraft("");
            }}
            disabled={saving}
            placeholder={t("tag_placeholder")}
            aria-label={t("tag_add")}
            className="w-[90px] text-[11px] px-1.5 py-[1px] rounded-sm bg-panel2 border border-border2 text-txt outline-none focus:border-accent placeholder:text-muted2 disabled:opacity-50"
          />
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
