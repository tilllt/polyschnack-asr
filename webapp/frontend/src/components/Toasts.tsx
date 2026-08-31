import React, {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";

/* ============================================================
   TYPES
   ============================================================ */

export type ToastType = "ok" | "err" | "info";

interface ToastItem {
  id: number;
  msg: string;
  type: ToastType;
}

interface ToastContextValue {
  toast: (msg: string, type?: ToastType) => void;
}

/* ============================================================
   CONTEXT
   ============================================================ */

const ToastContext = createContext<ToastContextValue | null>(null);

let _nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const toast = useCallback((msg: string, type: ToastType = "ok") => {
    const id = _nextId++;
    setToasts((prev) => [...prev, { id, msg, type }]);

    // Fehler-Toasts brauchen Lesezeit (lange Meldungen, z. B. 409 mit
    // Live-Modus-Hinweis) — 10 s statt 3,1 s; Erfolge kurz.
    const duration = type === "err" ? 10_000 : 3_100;
    const timer = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
      timers.current.delete(id);
    }, duration);

    timers.current.set(id, timer);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <ToastContainer toasts={toasts} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

/* ============================================================
   TOAST CONTAINER + ITEM
   ============================================================ */

function ToastContainer({ toasts }: { toasts: ToastItem[] }) {
  return (
    <div className="fixed bottom-6 right-6 flex flex-col gap-2 z-[9999] pointer-events-none">
      {toasts.map((t) => (
        <ToastEl key={t.id} item={t} />
      ))}
    </div>
  );
}

function ToastEl({ item }: { item: ToastItem }) {
  const borderColor =
    item.type === "ok" ? "border-l-ok"
    : item.type === "err" ? "border-l-err"
    : "border-border2"; // info: neutral

  return (
    <div
      className={`
        bg-panel3 border border-border2 rounded-sm px-4 py-[10px]
        text-[13px] text-txt max-w-xs
        shadow-[0_8px_24px_rgba(0,0,0,.4)]
        border-l-[3px] ${borderColor}
        animate-toast-in
      `}
      style={{ animationFillMode: "both" }}
    >
      {item.msg}
    </div>
  );
}
