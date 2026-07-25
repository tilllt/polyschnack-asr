import { useState } from "react";
import { ChevronDown, Copy, MessageCircle } from "lucide-react";
import type { WhatsappGroupItem } from "../grouping";
import { RecordingCard } from "./RecordingCard";
import { useToast } from "./Toasts";
import { fmtDate, fmtHHMM } from "../format";

interface Props {
  group: WhatsappGroupItem;
}

import { useT } from "../useLocale";

export function WhatsappGroup({ group }: Props) {
  const [expanded, setExpanded] = useState(true);
  const { toast } = useToast();

  const { members } = group;
  const firstMember = members[0];
  const lastMember = members[members.length - 1];

  // Date label from first member
  const dateLabel = fmtDate(firstMember?.created_at);

  // Time range from recorded_at (fallback created_at)
  const firstTime = fmtHHMM(firstMember?.recorded_at ?? firstMember?.created_at);
  const lastTime = fmtHHMM(lastMember?.recorded_at ?? lastMember?.created_at);
  const timeRange =
    firstMember === lastMember
      ? firstTime
      : `${firstTime}–${lastTime}`;

  const { t } = useT();

  async function handleCopyAll() {
    const texts = members
      .map((m) => {
        if (m.text?.trim()) return m.text.trim();
        if (m.segments?.length) return m.segments.map((s) => s.text).join(" ");
        return null;
      })
      .filter(Boolean);

    if (!texts.length) {
      toast(t("no_text_to_copy"), "err");
      return;
    }
    try {
      await navigator.clipboard.writeText(texts.join("\n\n"));
      toast(t("copied"), "ok");
    } catch {
      toast(t("copy_failed"), "err");
    }
  }

  return (
    <div className="bg-panel border border-border rounded-card overflow-hidden border-l-[3px] border-l-[#25d366]">
      {/* ── Group header ── */}
      <div className="px-4 py-3 flex items-center gap-3 flex-wrap">
        {/* Icon + label */}
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <MessageCircle size={16} className="text-[#25d366] flex-shrink-0" />
          <span className="font-semibold text-[14px] text-txt">WhatsApp</span>
          <span className="bg-[rgba(37,211,102,.12)] text-[#25d366] text-[11px] font-semibold px-[7px] py-[1px] rounded-full flex-shrink-0">
            {members.length} {t("recordings")}
          </span>
          <span className="text-muted text-[12px] flex-shrink-0 hidden sm:inline">
            {dateLabel}
          </span>
          {timeRange && (
            <span className="text-muted2 text-[11px] flex-shrink-0 font-mono">
              {timeRange}
            </span>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={handleCopyAll}
            className="btn-ghost-sm flex items-center gap-1"
          >
            <Copy size={12} />
            {t("copy_all")}
          </button>
          <button
            onClick={() => setExpanded((e) => !e)}
            aria-label={expanded ? t("collapse_group") : t("expand_group")}
            className="btn-ghost-sm p-[6px]"
          >
            <ChevronDown
              size={14}
              className={`transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* ── Members ── */}
      {expanded && (
        <div className="px-3 pb-3 flex flex-col gap-3">
          {members.map((m) => (
            <RecordingCard key={m.id} recording={m} compact />
          ))}
        </div>
      )}
    </div>
  );
}
