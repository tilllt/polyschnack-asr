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
  entry("ps-pk-onnx", true), // Default — immer erreichbar
  entry("crispr-pk-cpp", true),
  entry("crispr-qwen3", false), // gestoppt / nie angelegt
  entry("crispr-ark", null), // Proxy down → unbekannt
];

describe("filterAvailableBackends", () => {
  it("zeigt Anon-Usern nur laufende Backends", () => {
    const result = filterAvailableBackends(matrix, false);
    expect(result).toEqual(["ps-pk-onnx", "crispr-pk-cpp"]);
    expect(result).not.toContain("crispr-qwen3");
    expect(result).not.toContain("crispr-ark");
  });

  it("zeigt Admins alle aktiven Backends", () => {
    const result = filterAvailableBackends(matrix, true);
    expect(result).toEqual(["ps-pk-onnx", "crispr-pk-cpp", "crispr-qwen3", "crispr-ark"]);
  });

  it("fallback auf Default wenn nur unbekannte Backends da sind", () => {
    const onlyUnknown = [entry("ps-pk-onnx", true), entry("crispr-ark", null), entry("crispr-qwen3", null)];
    const result = filterAvailableBackends(onlyUnknown, false);
    expect(result).toEqual(["ps-pk-onnx"]);
  });
});
