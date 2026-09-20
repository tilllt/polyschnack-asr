/// <reference types="vite/client" />

// Der Zonen-Test (Change 215) liest index.css als Textdatei, um die drei
// Breakpoint-Stufen der Zonen zu prüfen (Vitest ersetzt CSS-Importe durch
// leere Module, `?raw` hilft dort nicht). @types/node ist im Frontend nicht
// eingebunden — hier steht deshalb nur die eine benötigte Signatur.
declare module "node:fs" {
  export function readFileSync(path: string | URL, encoding: "utf8"): string;
}
declare module "node:url" {
  export function fileURLToPath(url: string | URL): string;
}
