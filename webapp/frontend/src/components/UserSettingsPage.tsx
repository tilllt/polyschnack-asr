import { useT } from "../useLocale";
import { TemplatesSection, TargetsSection, LlmEndpointsSection } from "./PostProcessPanel";

interface Props {
  user: { authenticated?: boolean } | null;
}

/** User-Settings-Seite: Postprocessing (Templates), Targets, BYOK.
 *
 * Nur für eingeloggte User — das Backend gate (require_authenticated)
 * erzwingt das auch serverseitig; hier zusätzlich UI-Doppelschutz.
 */
export function UserSettingsPage({ user }: Props) {
  const { t } = useT();
  if (!user?.authenticated) return null;
  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-[16px] font-bold">⚙️ {t("settings")}</h2>

      <section className="bg-panel border border-border rounded-card px-3 py-3">
        <h3 className="font-bold text-[13px] mb-2">🧩 {t("postprocess")}</h3>
        <TemplatesSection />
      </section>

      <section className="bg-panel border border-border rounded-card px-3 py-3">
        <h3 className="font-bold text-[13px] mb-2">📦 {t("targets")}</h3>
        <TargetsSection />
      </section>

      <section className="bg-panel border border-border rounded-card px-3 py-3">
        <h3 className="font-bold text-[13px] mb-2">🔑 {t("byok")}</h3>
        <LlmEndpointsSection />
      </section>
    </div>
  );
}
