import { useEffect, useState } from "react";
import { useT } from "../useLocale";
import {
  fetchTemplates,
  fetchTargets,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  createTarget,
  deleteTarget,
  fetchLlmEndpoints,
  createLlmEndpoint,
  deleteLlmEndpoint,
  type PromptTemplate,
  type DeliveryTargetItem,
  type LlmEndpoint,
} from "../api";

/* ============================================================
   Settings-Bereiche (Teil D/E) — Templates, Targets, BYOK-Endpunkte.
   Ehemals PostProcessPanel mit Tabs; jetzt 3 eigenständige Sektionen
   für die User-Settings-Seite. Nur für eingeloggte User (Backend-Gate
   + UI-Guard in UserSettingsPage).
   ============================================================ */

/* ------------------------- Templates ------------------------ */

export function TemplatesSection() {
  const { t } = useT();
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [err, setErr] = useState("");
  const [tplName, setTplName] = useState("");
  const [tplPrompt, setTplPrompt] = useState("");

  async function reload() {
    setErr("");
    fetchTemplates().then(setTemplates).catch((e) => setErr(String((e as Error).message)));
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveTemplate() {
    try {
      if (!tplName.trim() || !tplPrompt.trim()) return;
      await createTemplate(tplName.trim(), tplPrompt.trim());
      setTplName("");
      setTplPrompt("");
      await reload();
    } catch (e) {
      setErr(String((e as Error).message));
    }
  }

  return (
    <div className="space-y-2">
      {err && <div className="text-err text-[12px]">⚠️ {err}</div>}
      <div className="space-y-1.5">
        {templates.length === 0 && <p className="text-muted2 text-[11px]">{t("no_templates")}</p>}
        {templates.map((tp) => (
          <div key={tp.template_id} className="flex items-center gap-2 bg-panel2 border border-border rounded-sm px-2 py-1.5">
            <span className="font-semibold text-txt w-[120px] truncate">{tp.name}</span>
            <span className="text-muted flex-1 truncate">{tp.prompt}</span>
            <button
              onClick={() => { void updateTemplate(tp.template_id, { prompt: `${tp.prompt}\n` }).then(reload); }}
              className="text-muted2 hover:text-txt"
              title="+ newline"
            >
              ⏎
            </button>
            <button
              onClick={() => { void deleteTemplate(tp.template_id).then(reload); }}
              className="text-err hover:opacity-80"
              title={t("delete")}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-1.5 pt-1 border-t border-border">
        <input
          value={tplName}
          onChange={(e) => setTplName(e.target.value)}
          placeholder={t("template_name")}
          className="bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
        />
        <textarea
          value={tplPrompt}
          onChange={(e) => setTplPrompt(e.target.value)}
          placeholder={t("template_prompt")}
          rows={2}
          className="bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt resize-y"
        />
        <button onClick={() => void saveTemplate()} className="self-start bg-accent text-white text-[12px] px-3 py-[4px] rounded-sm font-semibold hover:opacity-90">
          {t("save")}
        </button>
      </div>
    </div>
  );
}

/* -------------------------- Targets ------------------------- */

export function TargetsSection() {
  const { t } = useT();
  const [targets, setTargets] = useState<DeliveryTargetItem[]>([]);
  const [err, setErr] = useState("");
  const [tgName, setTgName] = useState("");
  const [tgKind, setTgKind] = useState<"email" | "webdav">("email");
  const [tgTo, setTgTo] = useState("");
  const [tgUrl, setTgUrl] = useState("");
  const [tgUser, setTgUser] = useState("");
  const [tgPass, setTgPass] = useState("");
  const [tgPath, setTgPath] = useState("");

  async function reload() {
    setErr("");
    fetchTargets().then(setTargets).catch((e) => setErr(String((e as Error).message)));
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveTarget() {
    try {
      const config: Record<string, string> =
        tgKind === "email" ? { to: tgTo.trim() } : { url: tgUrl.trim(), username: tgUser.trim(), password: tgPass, path: tgPath.trim() };
      await createTarget(tgName.trim(), tgKind, config);
      setTgName("");
      setTgTo("");
      setTgUrl("");
      setTgUser("");
      setTgPass("");
      setTgPath("");
      await reload();
    } catch (e) {
      setErr(String((e as Error).message));
    }
  }

  return (
    <div className="space-y-2">
      {err && <div className="text-err text-[12px]">⚠️ {err}</div>}
      <div className="space-y-1.5">
        {targets.length === 0 && <p className="text-muted2 text-[11px]">{t("no_targets")}</p>}
        {targets.map((tg) => (
          <div key={tg.target_id} className="flex items-center gap-2 bg-panel2 border border-border rounded-sm px-2 py-1.5">
            <span className="font-semibold text-txt w-[120px] truncate">{tg.name}</span>
            <span className="text-muted text-[11px] uppercase">{tg.kind}</span>
            <span className="text-muted2 flex-1 truncate">
              {tg.kind === "email" ? tg.config.to : `${tg.config.url}${tg.config.path ? "/" + tg.config.path : ""}`}
            </span>
            <button
              onClick={() => { void deleteTarget(tg.target_id).then(reload); }}
              className="text-err hover:opacity-80"
              title={t("delete")}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-1.5 pt-1 border-t border-border">
        <div className="flex gap-1.5">
          <input
            value={tgName}
            onChange={(e) => setTgName(e.target.value)}
            placeholder={t("target_name")}
            className="flex-1 bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
          />
          <select
            value={tgKind}
            onChange={(e) => setTgKind(e.target.value as "email" | "webdav")}
            className="bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-muted"
          >
            <option value="email">E-Mail</option>
            <option value="webdav">WebDAV</option>
          </select>
        </div>
        {tgKind === "email" ? (
          <input
            value={tgTo}
            onChange={(e) => setTgTo(e.target.value)}
            placeholder={t("target_to")}
            className="bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
          />
        ) : (
          <>
            <input
              value={tgUrl}
              onChange={(e) => setTgUrl(e.target.value)}
              placeholder={t("target_url")}
              className="bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
            />
            <div className="flex gap-1.5">
              <input
                value={tgUser}
                onChange={(e) => setTgUser(e.target.value)}
                placeholder={t("target_username")}
                className="flex-1 bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
              />
              <input
                value={tgPass}
                onChange={(e) => setTgPass(e.target.value)}
                placeholder={t("target_password")}
                type="password"
                className="flex-1 bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
              />
            </div>
            <input
              value={tgPath}
              onChange={(e) => setTgPath(e.target.value)}
              placeholder={t("target_path")}
              className="bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
            />
          </>
        )}
        <button onClick={() => void saveTarget()} className="self-start bg-accent text-white text-[12px] px-3 py-[4px] rounded-sm font-semibold hover:opacity-90">
          {t("save")}
        </button>
      </div>
    </div>
  );
}

/* ------------------------ BYOK-Endpunkte --------------------- */

export function LlmEndpointsSection() {
  const { t } = useT();
  const [endpoints, setEndpoints] = useState<LlmEndpoint[]>([]);
  const [err, setErr] = useState("");
  const [epName, setEpName] = useState("");
  const [epUrl, setEpUrl] = useState("");
  const [epKey, setEpKey] = useState("");
  const [epModel, setEpModel] = useState("");

  async function reload() {
    setErr("");
    fetchLlmEndpoints().then(setEndpoints).catch((e) => setErr(String((e as Error).message)));
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveEndpoint() {
    try {
      if (!epName.trim() || !epUrl.trim() || !epKey.trim()) return;
      await createLlmEndpoint({
        name: epName.trim(),
        base_url: epUrl.trim(),
        api_key: epKey,
        model: epModel.trim() || undefined,
      });
      setEpName("");
      setEpUrl("");
      setEpKey("");
      setEpModel("");
      await reload();
    } catch (e) {
      setErr(String((e as Error).message));
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-muted2 text-[11px]">🔑 {t("endpoint_key_hint")}</p>
      {err && <div className="text-err text-[12px]">⚠️ {err}</div>}
      <div className="space-y-1.5">
        {endpoints.length === 0 && <p className="text-muted2 text-[11px]">{t("no_endpoints")}</p>}
        {endpoints.map((ep) => (
          <div key={ep.endpoint_id} className="flex items-center gap-2 bg-panel2 border border-border rounded-sm px-2 py-1.5">
            <span className="font-semibold text-txt w-[120px] truncate">{ep.name}</span>
            <span className="text-muted flex-1 truncate">{ep.base_url}</span>
            <span className="text-muted2 text-[11px] font-mono truncate">{ep.model}</span>
            <button
              onClick={() => { void deleteLlmEndpoint(ep.endpoint_id).then(reload); }}
              className="text-err hover:opacity-80"
              title={t("delete")}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-1.5 pt-1 border-t border-border">
        <div className="flex gap-1.5">
          <input
            value={epName}
            onChange={(e) => setEpName(e.target.value)}
            placeholder={t("endpoint_name")}
            className="flex-1 bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
          />
          <input
            value={epModel}
            onChange={(e) => setEpModel(e.target.value)}
            placeholder={t("endpoint_model")}
            className="flex-1 bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
          />
        </div>
        <input
          value={epUrl}
          onChange={(e) => setEpUrl(e.target.value)}
          placeholder={t("endpoint_url_placeholder")}
          className="bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
        />
        <input
          value={epKey}
          onChange={(e) => setEpKey(e.target.value)}
          placeholder={t("endpoint_key")}
          type="password"
          className="bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt"
        />
        <button onClick={() => void saveEndpoint()} className="self-start bg-accent text-white text-[12px] px-3 py-[4px] rounded-sm font-semibold hover:opacity-90">
          {t("save")}
        </button>
      </div>
    </div>
  );
}
