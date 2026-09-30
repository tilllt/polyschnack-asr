/**
 * Change 237 — Sprache am <html> verankern und merken.
 *
 * Befund 30.09.2026: index.html stand fest auf `lang="pt-br"` (Portugiesisch
 * als Hauptsprache, obwohl Deutsch die Hauptsprache ist), und die Wahl im
 * Sprachmenü war nach jedem Neuladen weg — die Anwendung startete immer auf
 * Englisch (`useState("en")`), ohne den Browserspeicher oder die
 * Browsersprache zu beachten.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render } from "@testing-library/react";
import { createElement } from "react";

import { LANG_STORAGE_KEY, LocaleProvider, detectInitialLang, useT } from "./useLocale";

function Umschalter() {
  const { lang, setLang } = useT();
  return createElement("button", { onClick: () => setLang("pt-BR") }, lang);
}

const originalLanguage = Object.getOwnPropertyDescriptor(window.navigator, "language");
const originalStorage = Object.getOwnPropertyDescriptor(window, "localStorage");

function setBrowserLanguage(value: string) {
  Object.defineProperty(window.navigator, "language", { value, configurable: true });
}

/**
 * Diese Testumgebung liefert kein `window.localStorage` (vitest ohne
 * `--localstorage-file`). Der Produktivpfad behandelt das bereits (try/catch +
 * optionale Verkettung) — für die Prüfung der Merkfunktion wird ein
 * Speicher-Ersatz gesetzt.
 */
function stubStorage(): Map<string, string> {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => (store.has(k) ? String(store.get(k)) : null),
      setItem: (k: string, v: string) => {
        store.set(k, String(v));
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
      clear: () => store.clear(),
    },
  });
  return store;
}

beforeEach(() => {
  stubStorage().clear();
  document.documentElement.lang = "de";
  setBrowserLanguage("en-US");
});

afterEach(() => {
  if (originalLanguage) Object.defineProperty(window.navigator, "language", originalLanguage);
  if (originalStorage) {
    Object.defineProperty(window, "localStorage", originalStorage);
  }
});

describe("detectInitialLang", () => {
  it("nimmt die gespeicherte Wahl", () => {
    window.localStorage.setItem(LANG_STORAGE_KEY, "pt-BR");
    expect(detectInitialLang()).toBe("pt-BR");
  });

  it("folgt der Browsersprache, wenn nichts gespeichert ist", () => {
    setBrowserLanguage("de-DE");
    expect(detectInitialLang()).toBe("de");
    setBrowserLanguage("pt-BR");
    expect(detectInitialLang()).toBe("pt-BR");
  });

  it("fällt auf Deutsch zurück, wenn die Browsersprache unbekannt ist", () => {
    setBrowserLanguage("fr-FR");
    expect(detectInitialLang()).toBe("de");
  });
});

describe("LocaleProvider", () => {
  it("schreibt die gewählte Sprache ins <html>", () => {
    window.localStorage.setItem(LANG_STORAGE_KEY, "pt-BR");
    render(createElement(LocaleProvider, null, createElement(Umschalter)));
    expect(document.documentElement.lang).toBe("pt-BR");
  });

  it("merkt die Wahl im Sprachmenü und zieht <html> nach", () => {
    render(createElement(LocaleProvider, null, createElement(Umschalter)));
    expect(document.documentElement.lang).toBe("en"); // jsdom: en-US

    const button = document.querySelector("button");
    expect(button).not.toBeNull();
    fireEvent.click(button as HTMLButtonElement);

    expect(document.documentElement.lang).toBe("pt-BR");
    expect(window.localStorage.getItem(LANG_STORAGE_KEY)).toBe("pt-BR");
  });
});
