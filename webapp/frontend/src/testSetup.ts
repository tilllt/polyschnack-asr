/**
 * Change 236 — der Geteiltenspeicher ist absichtlich langlebig (er soll ja
 * mehrere Karten bedienen). Für Prüfungen muss er deshalb vor JEDER Prüfung
 * leer sein: sonst erbte eine Prüfung die Auskunft der vorigen und ein Mock,
 * der erst im zweiten Test gesetzt wird, käme nie zum Zug.
 */
import { beforeEach } from "vitest";
import { forgetSharedConfig } from "./sharedConfig";

beforeEach(() => {
  forgetSharedConfig();
});
