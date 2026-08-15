import { useEffect, useState } from "react";
import { useT } from "../useLocale";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/** PWA-Install-Banner — erscheint oben unter dem Header.
 *
 * - Android/Chrome/Edge: fängt beforeinstallprompt ab → eigenes Banner
 *   mit „Installieren"-Button (native Aufforderung wird erst beim Klick
 *   gezeigt, damit sie nicht vom Browser unterdrückt wird).
 * - iOS (Safari): kein beforeinstallprompt — stattdessen Hinweis auf
 *   „Zum Home-Bildschirm" (Teilen-Button → Zu Home hinzufügen).
 * - Einmal abgelehnt → in localStorage gemerkt (kann über den Header
 *   nicht mehr aufpoppen, bis der User die App installiert hat).
 */
export function InstallBanner() {
  const { t } = useT();
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [isIOS, setIsIOS] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const KEY = "ps_pwa_install_dismissed";
    if (localStorage.getItem(KEY)) {
      setDismissed(true);
      return;
    }
    // iOS-Erkennung (kein beforeinstallprompt, aber PWA installierbar)
    const ua = navigator.userAgent;
    const iOS = /iPad|iPhone|iPod/.test(ua) && !(window as unknown as { MSStream?: unknown }).MSStream;
    setIsIOS(iOS);

    const onPrompt = (e: Event) => {
      e.preventDefault(); // eigenes Banner statt Browser-Banner
      setDeferred(e as BeforeInstallPromptEvent);
    };
    const onInstalled = () => {
      setDeferred(null);
      setDismissed(true);
      localStorage.setItem(KEY, "1");
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  // Bereits installiert (standalone-Modus) → nie anzeigen
  const isStandalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as unknown as { standalone?: boolean }).standalone === true;
  if (isStandalone || dismissed) return null;

  const showBanner = deferred !== null || isIOS;

  if (!showBanner) return null;

  const dismiss = () => {
    setDismissed(true);
    localStorage.setItem("ps_pwa_install_dismissed", "1");
  };

  const install = async () => {
    if (!deferred) return;
    await deferred.prompt();
    const choice = await deferred.userChoice;
    if (choice.outcome === "accepted") {
      setDismissed(true);
      localStorage.setItem("ps_pwa_install_dismissed", "1");
    }
    setDeferred(null);
  };

  return (
    <div className="w-full bg-[rgba(91,140,255,.12)] border-b border-accent/25 px-3 sm:px-6 py-2 flex items-center gap-2">
      <span className="text-[13px]">📱</span>
      <span className="text-[12px] text-txt flex-1">
        {isIOS ? t("pwa_install_ios") : t("pwa_install_hint")}
      </span>
      {deferred && (
        <button
          onClick={() => void install()}
          className="bg-accent text-white text-[11px] px-3 py-1 rounded-sm font-semibold hover:opacity-90 whitespace-nowrap"
        >
          {t("pwa_install_btn")}
        </button>
      )}
      <button
        onClick={dismiss}
        className="text-muted2 hover:text-txt text-[14px] leading-none px-1"
        title={t("pwa_install_dismiss")}
      >
        ✕
      </button>
    </div>
  );
}
