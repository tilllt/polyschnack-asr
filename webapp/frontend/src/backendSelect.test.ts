import { describe, expect, it } from "vitest";
import { filterAvailableBackends } from "./backendSelect";
import type { ModelMatrixEntry } from "./api";

function entry(name: string, reachable: boolean | null): ModelMatrixEntry {
  return {
    name,
    backend: name,
    model: "",
    type: "local",
    status: "active",
    reachable,
    concurrency: 1,
    device: ["gpu"],
    languages: ["de", "en"],
    word_timestamps: true,
    streaming: false,
    async_jobs: false,
    noise_reduce: false,
    vad: "no",
    diarization: "no",
    enhance: false,
    requires: {},
  };
}

const matrix = [
  entry("pk-python", true), // Default — immer erreichbar
  entry("pk-cpp", true),
  entry("qwen3-asr", false), // gestoppt / nie angelegt
  entry("ark-asr", null), // Proxy down → unbekannt
];

describe("filterAvailableBackends", () => {
  it("zeigt Anon-Usern nur laufende Backends", () => {
    const result = filterAvailableBackends(matrix, false);
    expect(result).toEqual(["pk-python", "pk-cpp"]);
    expect(result).not.toContain("qwen3-asr");
    expect(result).not.toContain("ark-asr");
  });

  it("zeigt Admins alle aktiven Backends", () => {
    const result = filterAvailableBackends(matrix, true);
    expect(result).toEqual(["pk-python", "pk-cpp", "qwen3-asr", "ark-asr"]);
  });

  it("fallback auf Default wenn nur unbekannte Backends da sind", () => {
    const onlyUnknown = [entry("pk-python", true), entry("ark-asr", null), entry("qwen3-asr", null)];
    const result = filterAvailableBackends(onlyUnknown, false);
    expect(result).toEqual(["pk-python"]);
  });
});
