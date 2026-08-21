/**
 * Change 056 — Annotationen einer Transkription (Thread-Ansicht).
 *
 * - Threads: Top-Level-Kommentare nach Zeit, Antworten eingerückt
 * - Markdown-Rendering via react-markdown (sicher, kein dangerouslySetInnerHTML)
 * - Mentions: `@name` → hervorgehobener Chip-Link; Klick belegt das
 *   Antwort-Formular der zugehörigen Annotation mit `@name `
 * - Zeitfenster-Chip (`0:42–0:47`), Klick springt zur Stelle (Player-Seek)
 * - Edit/Delete nur für den Autor (sub-Vergleich); Backend erzwingt
 *   zusätzlich (403 bei fremdem Autor)
 * - activeId (Playback-Fenster) → Highlight in der Liste
 */
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import { X, Check, Pencil, Trash2, MessageSquarePlus } from "lucide-react";
import {
  replyToAnnotation,
  updateAnnotation,
  deleteAnnotation,
  fetchMe,
  type Annotation,
} from "../api";
import { fmtDate } from "../format";
import { useT } from "../useLocale";
import { useToast } from "./Toasts";

/** 0:42 aus Sekunden. */
function fmtTime(s: number): string {
  const m = Math.floor(Math.max(0, s) / 60);
  const sec = Math.floor(Math.max(0, s) % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

/** @name-Token → Markdown-Link (#mention:name) fürs sichere Rendering. */
function mentionize(body: string): string {
  return body.replace(/@([\w][\w.\-]*)/g, "[@$1](#mention:$1)");
}

interface Props {
  /** Recording-UID (Query-Key-Teil + Invalidate). */
  rid: string;
  /** Geladene Annotationen (flach; Parent lädt via useQuery). */
  annotations: Annotation[];
  isLoading?: boolean;
  /** write-Zugriff → Antwort-Formular/Annotieren sichtbar. */
  canEdit: boolean;
  /** Annotation im aktuellen Playback-Fenster → Highlight. */
  activeId?: number | null;
  /** Klick auf Zeitfenster-Chip → Player springt zur Stelle. */
  onSeek?: (t: number) => void;
}

export function AnnotationThreads({ rid, annotations, isLoading = false, canEdit, activeId = null, onSeek }: Props) {
  const { t } = useT();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [replyDrafts, setReplyDrafts] = useState<Record<number, string>>({});
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const meQuery = useQuery({ queryKey: ["me"] as const, queryFn: fetchMe });
  const mySub = meQuery.data?.sub ?? null;
  const tops = useMemo(() => annotations.filter((a) => a.parent_id === null), [annotations]);
  const repliesByParent = useMemo(() => {
    const m = new Map<number, Annotation[]>();
    for (const a of annotations) {
      if (a.parent_id !== null) {
        const list = m.get(a.parent_id) ?? [];
        list.push(a);
        m.set(a.parent_id, list);
      }
    }
    return m;
  }, [annotations]);

  async function invalidate() {
    await qc.invalidateQueries({ queryKey: ["annotations", rid] });
  }

  async function saveReply(parentId: number) {
    const body = (replyDrafts[parentId] ?? "").trim();
    if (!body) return;
    setBusy(true);
    try {
      await replyToAnnotation(parentId, body);
      setReplyDrafts((d) => ({ ...d, [parentId]: "" }));
      await invalidate();
    } catch (e) {
      toast(`${t("annot_reply_error")}: ${(e as Error).message}`, "err");
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(aid: number) {
    const body = editDraft.trim();
    if (!body) return;
    setBusy(true);
    try {
      await updateAnnotation(aid, body);
      setEditingId(null);
      await invalidate();
    } catch (e) {
      toast(`${t("annot_edit_error")}: ${(e as Error).message}`, "err");
    } finally {
      setBusy(false);
    }
  }

  async function remove(aid: number) {
    setBusy(true);
    try {
      await deleteAnnotation(aid);
      await invalidate();
    } catch (e) {
      toast(`${t("annot_delete_error")}: ${(e as Error).message}`, "err");
    } finally {
      setBusy(false);
    }
  }

  function mentionInto(parentId: number, name: string) {
    setReplyDrafts((d) => ({ ...d, [parentId]: `${d[parentId] ?? ""}@${name} ` }));
  }

  if (isLoading) {
    return <div className="mt-3 text-[12px] text-muted2">{t("annot_loading")}</div>;
  }
  // Change 067-Fix (User-Befund 2026-08-21): KEIN „Noch keine
  // Annotationen"-Hinweis — leere Liste rendert nichts.
  if (!annotations.length) {
    return null;
  }

  const md = (a: Annotation) => (
    <ReactMarkdown
      components={{
        a: ({ href, children }) => {
          if (href?.startsWith("#mention:")) {
            const name = href.slice(9);
            return (
              <button
                onClick={() => mentionInto(a.parent_id ?? a.id, name)}
                className="text-accent hover:underline font-medium"
                title={t("annot_mention_hint")}
              >
                {children}
              </button>
            );
          }
          return (
            <a href={href} target="_blank" rel="noreferrer" className="text-accent hover:underline">
              {children}
            </a>
          );
        },
      }}
    >
      {mentionize(a.body)}
    </ReactMarkdown>
  );

  return (
    <div className="mt-3 flex flex-col gap-2" data-testid="annotation-threads">
      {tops.map((top) => {
        const replies = repliesByParent.get(top.id) ?? [];
        const isActive = activeId === top.id || replies.some((r) => r.id === activeId);
        const isAuthor = mySub !== null && top.user_sub === mySub;
        const canEditThis = canEdit && isAuthor;
        return (
          <div
            key={top.id}
            className={`rounded-sm border p-2 transition-colors ${
              isActive
                ? "border-accent bg-accent/5"
                : "border-border2 bg-panel2"
            }`}
            data-active={isActive ? "1" : "0"}
          >
            {/* Kopf: Autor + Zeitfenster */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[12px] font-semibold text-txt">
                {top.user_name ?? t("annot_anonymous")}
              </span>
              <span className="text-[11px] text-muted2">
                {fmtDate(top.created_at ?? "")}
              </span>
              {onSeek && (
                <button
                  onClick={() => onSeek(top.start_s)}
                  className="text-[11px] px-1.5 py-[1px] rounded-sm border border-border2 text-accent hover:bg-accent/10 transition-colors"
                  title={t("annot_seek_hint")}
                >
                  ▶ {fmtTime(top.start_s)}–{fmtTime(top.end_s)}
                </button>
              )}
              {canEditThis && !busy && (
                <span className="ml-auto flex items-center gap-1">
                  <button
                    onClick={() => {
                      setEditingId(top.id);
                      setEditDraft(top.body);
                    }}
                    aria-label={t("annot_edit")}
                    title={t("annot_edit")}
                    className="text-muted2 hover:text-accent transition-colors"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    onClick={() => remove(top.id)}
                    aria-label={t("annot_delete")}
                    title={t("annot_delete")}
                    className="text-muted2 hover:text-err transition-colors"
                  >
                    <Trash2 size={12} />
                  </button>
                </span>
              )}
            </div>

            {/* Body (Markdown + Mentions) bzw. Edit-Textarea */}
            {editingId === top.id ? (
              <div className="mt-1.5 flex items-start gap-1">
                <textarea
                  value={editDraft}
                  onChange={(e) => setEditDraft(e.target.value)}
                  className="flex-1 min-w-0 bg-panel border border-accent/50 rounded-sm px-1.5 py-1 text-[12px] text-txt outline-none"
                  rows={3}
                />
                <button
                  onClick={() => saveEdit(top.id)}
                  aria-label={t("annot_save")}
                  className="text-accent hover:text-accent/80 mt-0.5"
                >
                  <Check size={14} />
                </button>
                <button
                  onClick={() => setEditingId(null)}
                  aria-label={t("split_segment_cancel")}
                  className="text-muted2 hover:text-txt mt-0.5"
                >
                  <X size={14} />
                </button>
              </div>
            ) : (
              <div className="mt-1 text-[13px] text-txt leading-[1.5] prose-sm [&_p]:my-1 [&_ul]:list-disc [&_ul]:pl-4">
                {md(top)}
              </div>
            )}

            {/* Antworten */}
            {replies.length > 0 && (
              <div className="mt-2 ml-3 border-l-2 border-border2 pl-2 flex flex-col gap-1.5">
                {replies.map((rep) => {
                  const repIsActive = activeId === rep.id;
                  const repIsAuthor = mySub !== null && rep.user_sub === mySub;
                  const canEditRep = canEdit && repIsAuthor;
                  return (
                    <div
                      key={rep.id}
                      className={`rounded-sm border p-1.5 ${
                        repIsActive ? "border-accent bg-accent/5" : "border-border2"
                      }`}
                      data-active={repIsActive ? "1" : "0"}
                    >
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-[11px] font-semibold text-txt">
                          {rep.user_name ?? t("annot_anonymous")}
                        </span>
                        <span className="text-[10px] text-muted2">
                          {fmtDate(rep.created_at ?? "")}
                        </span>
                        {canEditRep && !busy && (
                          <span className="ml-auto flex items-center gap-1">
                            <button
                              onClick={() => {
                                setEditingId(rep.id);
                                setEditDraft(rep.body);
                              }}
                              aria-label={t("annot_edit")}
                              className="text-muted2 hover:text-accent transition-colors"
                            >
                              <Pencil size={11} />
                            </button>
                            <button
                              onClick={() => remove(rep.id)}
                              aria-label={t("annot_delete")}
                              className="text-muted2 hover:text-err transition-colors"
                            >
                              <Trash2 size={11} />
                            </button>
                          </span>
                        )}
                      </div>
                      {editingId === rep.id ? (
                        <div className="mt-1 flex items-start gap-1">
                          <textarea
                            value={editDraft}
                            onChange={(e) => setEditDraft(e.target.value)}
                            className="flex-1 min-w-0 bg-panel border border-accent/50 rounded-sm px-1.5 py-1 text-[12px] text-txt outline-none"
                            rows={2}
                          />
                          <button
                            onClick={() => saveEdit(rep.id)}
                            aria-label={t("annot_save")}
                            className="text-accent hover:text-accent/80 mt-0.5"
                          >
                            <Check size={13} />
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            aria-label={t("split_segment_cancel")}
                            className="text-muted2 hover:text-txt mt-0.5"
                          >
                            <X size={13} />
                          </button>
                        </div>
                      ) : (
                        <div className="mt-0.5 text-[12px] text-txt leading-[1.45]">
                          {md(rep)}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Antwort-Formular (write) */}
            {canEdit && (
              <div className="mt-1.5 flex items-start gap-1">
                <textarea
                  value={replyDrafts[top.id] ?? ""}
                  onChange={(e) =>
                    setReplyDrafts((d) => ({ ...d, [top.id]: e.target.value }))
                  }
                  placeholder={`${t("annot_reply_placeholder")} @name`}
                  className="flex-1 min-w-0 bg-panel border border-border2 rounded-sm px-1.5 py-1 text-[12px] text-txt outline-none focus:border-accent placeholder:text-muted2"
                  rows={2}
                />
                <button
                  onClick={() => saveReply(top.id)}
                  disabled={busy || !(replyDrafts[top.id] ?? "").trim()}
                  className="flex items-center gap-1 text-[12px] text-accent hover:text-accent/80 disabled:opacity-40 transition-colors mt-0.5"
                >
                  <MessageSquarePlus size={13} />
                  {t("annot_reply")}
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
