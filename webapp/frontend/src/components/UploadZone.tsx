import { useRef, useState } from "react";
import { Mic } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { uploadRecording } from "../api";
import { useToast } from "./Toasts";

export function UploadZone() {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();
  const qc = useQueryClient();

  async function handleFiles(files: FileList | File[]) {
    const items = Array.from(files);
    if (!items.length) return;

    setIsUploading(true);
    const batchId = crypto.randomUUID();

    const results = await Promise.allSettled(
      items.map((f) => uploadRecording(f, batchId))
    );

    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const errors = results
      .map((r, i) =>
        r.status === "rejected"
          ? `${items[i]?.name ?? "file"}: ${(r.reason as Error).message}`
          : null
      )
      .filter((e): e is string => e !== null);

    if (succeeded > 0) {
      toast(
        `${succeeded} arquivo${succeeded !== 1 ? "s" : ""} enviado${succeeded !== 1 ? "s" : ""}`,
        "ok"
      );
    }
    errors.forEach((msg) => toast(msg, "err"));

    await qc.invalidateQueries({ queryKey: ["recordings"] });
    await qc.invalidateQueries({ queryKey: ["stats"] });

    setIsUploading(false);
  }

  function handleClick() {
    if (isUploading) return;
    fileRef.current?.click();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") fileRef.current?.click();
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length) void handleFiles(e.dataTransfer.files);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.length) {
      void handleFiles(e.target.files);
      e.target.value = "";
    }
  }

  const active = isDragging || isUploading;

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Área de upload de áudio"
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`
        border-2 border-dashed rounded-card
        px-6 py-9 text-center cursor-pointer
        select-none transition-all duration-200
        bg-panel
        ${
          active
            ? "border-accent bg-[rgba(91,140,255,0.06)] text-txt"
            : "border-border2 text-muted hover:border-accent hover:bg-[rgba(91,140,255,0.06)] hover:text-txt"
        }
      `}
    >
      <div className="text-[32px] mb-2 leading-none">
        {isUploading ? "⏳" : <Mic size={32} className="mx-auto text-muted" />}
      </div>
      <div className="font-semibold text-[15px] text-txt">
        {isUploading
          ? "Enviando arquivos…"
          : "Arraste arquivos aqui ou clique para escolher"}
      </div>
      <div className="text-[12.5px] mt-1 text-muted">
        Múltiplos arquivos aceitos — todos enviados em paralelo
      </div>
      <div className="mt-[10px] text-[11px] text-muted2 tracking-[.03em]">
        MP3 · WAV · OGG / OPUS · M4A · FLAC · WEBM
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="audio/*"
        multiple
        className="hidden"
        onChange={handleInputChange}
      />
    </div>
  );
}
