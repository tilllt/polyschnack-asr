import { useCallback, useEffect, useState } from "react";
import { useT } from "../useLocale";
import { createApiKey, deleteApiKey, fetchApiKeys, type ApiKeyCreated, type ApiKeyItem } from "../api";
import { useToast } from "./Toasts";

/** API-Keys-Section für die User-Settings-Seite: programmatische Nutzung
 * von PolySchnack (eigene Skripte, CI). Der Klartext-Key ist NUR direkt
 * nach dem Erstellen sichtbar (Backend gibt ihn einmal zurück) — danach
 * zeigt die Liste nur noch Metadaten.
 */
export function ApiKeysSection() {
  const { t } = useT();
  const { toast } = useToast();
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [err, setErr] = useState("");
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [level, setLevel] = useState<"read" | "write" | "full">("read");
  const [expiry, setExpiry] = useState(""); // "" = Default 1 Jahr
  const [busy, setBusy] = useState(false);
  const [fresh, setFresh] = useState<ApiKeyCreated | null>(null); // nur direkt nach Erstellen

  const reload = useCallback(() => {
    setErr("");
    fetchApiKeys().then(setKeys).catch((e) => setErr(String((e as Error).message)));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function generate() {
    try {
      if (!name.trim()) {
        setErr(t("api_key_name") + "?");
        return;
      }
      setBusy(true);
      setErr("");
      const created = await createApiKey({
        name: name.trim(),
        description: desc.trim() || undefined,
        level,
        expires_at: expiry ? new Date(expiry).toISOString() : null,
      });
      setFresh(created);
      setName("");
      setDesc("");
      setExpiry("");
      await reload();
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function copyToken() {
    if (!fresh) return;
    try {
      await navigator.clipboard.writeText(fresh.token);
      toast(t("api_key_copied"));
    } catch {
      // Fallback für ältere Browser ohne Clipboard-API
      const ta = document.createElement("textarea");
      ta.value = fresh.token;
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        toast(t("api_key_copied"));
      } catch {
        setErr(t("api_key_copied"));
      }
      document.body.removeChild(ta);
    }
  }

  async function revoke(kid: number) {
    if (!window.confirm(t("api_key_delete_confirm"))) return;
    try {
      await deleteApiKey(kid);
      await reload();
    } catch (e) {
      setErr(String((e as Error).message));
    }
  }

  return (
    <div className="space-y-2">
      {err && <div className="text-err text-[12px]">⚠️ {err}</div>}

      {/* Frisch erstellter Key — nur hier sichtbar */}
      {fresh && (
        <div className="bg-accent/10 border border-accent/30 rounded-sm px-2 py-2 space-y-1.5">
          <div className="text-[12px] font-bold text-txt">🔑 {fresh.name}</div>
          <div className="text-[12px] font-bold text-err">{t("api_key_save_warning")}</div>
          <div className="flex items-center gap-1.5">
            <code className="flex-1 bg-panel2 border border-border rounded-sm px-2 py-1 text-[11px] break-all select-all">
              {fresh.token}
            </code>
            <button
              onClick={() => void copyToken()}
              className="bg-accent text-white text-[11px] px-2.5 py-1 rounded-sm font-semibold hover:opacity-90 whitespace-nowrap"
            >
              📋 {t("api_key_copy")}
            </button>
          </div>
        </div>
      )}

      {/* Bestehende Keys (Metadaten, Token nie wieder) */}
      <div className="space-y-1.5">
        {keys.length === 0 && <p className="text-muted2 text-[11px]">{t("api_key_no_keys")}</p>}
        {keys.map((k) => (
          <div key={k.key_id} className="flex items-center gap-2 bg-panel2 border border-border rounded-sm px-2 py-1.5">
            <span className="font-semibold text-txt text-[12px] w-[130px] truncate">{k.name}</span>
            {k.description && (
              <span className="text-muted text-[11px] flex-1 truncate">{k.description}</span>
            )}
            <span className="text-muted2 text-[10px] uppercase tracking-wide">{k.level}</span>
            <span className="text-muted2 text-[10px] whitespace-nowrap">
              {k.expired ? (
                <span className="text-err font-semibold">{t("api_key_expired_badge")}</span>
              ) : (
                <>
                  {t("api_key_created")}: {new Date(k.created_at).toLocaleDateString()}
                  {k.expires_at && <> · bis {new Date(k.expires_at).toLocaleDateString()}</>}
                </>
              )}
            </span>
            <button
              onClick={() => void revoke(k.key_id)}
              className="text-err hover:opacity-80 text-[12px]"
              title={t("api_key_delete")}
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {/* Neuer Key */}
      <div className="flex flex-col gap-1.5 pt-1 border-t border-border">
        <div className="flex gap-1.5">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("api_key_name_ph")}
            className="flex-1 bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
          />
          <input
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder={t("api_key_desc_ph")}
            className="flex-1 bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
          />
        </div>
        <div className="flex items-center gap-1.5">
          <input
            type="date"
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            title={t("api_key_expiry")}
            className="bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
          />
          <span className="text-muted2 text-[11px]">{t("api_key_expiry_default")}</span>
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value as "read" | "write" | "full")}
            title={t("api_key_level")}
            className="bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
          >
            <option value="read">read</option>
            <option value="write">write</option>
            <option value="full">full</option>
          </select>
          <button
            onClick={() => void generate()}
            disabled={busy}
            className="ml-auto bg-accent text-white text-[12px] px-3 py-[4px] rounded-sm font-semibold hover:opacity-90 disabled:opacity-50"
          >
            {busy ? t("api_key_generating") : t("api_key_create")}
          </button>
        </div>
      </div>
    </div>
  );
}
