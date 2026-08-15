/* GitHub-artiger Diff für Versionsvergleich.
 *
 * Backend liefert [{type: same|add|del, text}] (Zeilen-Diff, difflib).
 * Diese Module bauen daraus:
 *   - Zeilennummern (alt/neu) pro Zeile
 *   - Hunks mit Kontext-Kürzung (wie GitHub: nur geänderte Bereiche + Kontext,
 *     lange unveränderte Strecken werden eingeklappt)
 *   - Statistik (+X −Y)
 *   - Inline-Wort-Diff für replace-Paare (del-Zeile ↔ add-Zeile)
 */

export interface DiffLine {
  type: "same" | "add" | "del";
  text: string;
}

export interface DiffWord {
  text: string;
  type: "same" | "add" | "del";
}

export interface DiffRow {
  type: "same" | "add" | "del";
  text: string;
  aLine: number | null; // Zeilennummer in der alten Version
  bLine: number | null; // Zeilennummer in der neuen Version
  /** Inline-Wort-Diff (nur bei replace-Paaren gesetzt) */
  words?: DiffWord[];
  /** Einklapp-Marker: Anzahl der ausgelassenen unveränderten Zeilen */
  skipped?: number;
}

export interface DiffHunk {
  aStart: number; // erste alte Zeilennummer im Hunk
  bStart: number; // erste neue Zeilennummer im Hunk
  rows: DiffRow[];
}

export interface DiffModel {
  hunks: DiffHunk[];
  stats: { add: number; del: number };
  identical: boolean;
}

/** Kontext-Zeilen um Änderungen herum (GitHub zeigt 3). */
const CTX = 3;
/** Ab dieser Länge wird eine unveränderte Strecke eingeklappt. */
const COLLAPSE_AT = CTX * 2 + 1;

function isChange(row: DiffRow): boolean {
  return row.type === "add" || row.type === "del";
}

/** LCS-basierter Wort-Diff: markiert veränderte Wörter inline (GitHub-Stil). */
export function wordDiff(oldText: string, newText: string): DiffWord[] {
  const split = (t: string) => (t.match(/\S+\s*|\s+/g) ?? []).map((w) => w);
  const a = split(oldText);
  const b = split(newText);
  const n = a.length;
  const m = b.length;

  // DP über Wort-Indizes; Transkript-Zeilen sind kurz (klassisches LCS).
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const out: DiffWord[] = [];
  const push = (text: string, type: DiffWord["type"]) => {
    const last = out[out.length - 1];
    if (last && last.type === type) last.text += text;
    else out.push({ text, type });
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      push(a[i], "same");
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      push(a[i], "del");
      i++;
    } else {
      push(b[j], "add");
      j++;
    }
  }
  while (i < n) push(a[i++], "del");
  while (j < m) push(b[j++], "add");
  return out;
}

/** Baut Hunks mit Zeilennummern, Kontext-Kürzung und Statistik. */
export function buildDiffModel(diff: DiffLine[]): DiffModel {
  // 1) Zeilennummern vergeben
  let a = 0;
  let b = 0;
  const rows: DiffRow[] = diff.map((l) => {
    if (l.type === "same") {
      a++;
      b++;
      return { type: "same" as const, text: l.text, aLine: a, bLine: b };
    }
    if (l.type === "del") {
      a++;
      return { type: "del" as const, text: l.text, aLine: a, bLine: null };
    }
    b++;
    return { type: "add" as const, text: l.text, aLine: null, bLine: b };
  });

  // 2) replace-Paare: aufeinanderfolgende del→add-Blöcke gleicher Länge
  //    mit Inline-Wort-Diff versehen
  const merged: DiffRow[] = [];
  let i = 0;
  while (i < rows.length) {
    if (rows[i].type === "del") {
      let j = i;
      while (j < rows.length && rows[j].type === "del") j++;
      let k = j;
      while (k < rows.length && rows[k].type === "add") k++;
      const delRows = rows.slice(i, j);
      const addRows = rows.slice(j, k);
      if (delRows.length === addRows.length && delRows.length > 0) {
        const len = delRows.length;
        for (let idx = 0; idx < len; idx++) {
          const words = wordDiff(delRows[idx].text, addRows[idx].text);
          merged.push({ ...delRows[idx], words });
          merged.push({ ...addRows[idx], words });
        }
      } else {
        merged.push(...delRows, ...addRows);
      }
      i = k;
    } else {
      merged.push(rows[i]);
      i++;
    }
  }

  // 3) Statistik
  let add = 0;
  let del = 0;
  for (const r of merged) {
    if (r.type === "add") add++;
    else if (r.type === "del") del++;
  }

  // 4) Hunks: Änderungsblöcke + Kontext; lange same-Strecken einklappen.
  //    Algorithme: sammle Änderungen; same-Zeilen puffern. Bei > COLLAPSE_AT
  //    unveränderten Zeilen: Puffer kürzen auf [erste CTX | Marker | letzte CTX]
  //    und Hunk nach der 2. Hälfte schließen, sobald die nächste Änderung kommt.
  const hunks: DiffHunk[] = [];
  let hunkRows: DiffRow[] = [];
  let pending: DiffRow[] = []; // gepufferte same-Zeilen
  let collapsed = false;

  const ctxRows = (buf: DiffRow[]): DiffRow[] => {
    if (buf.length <= COLLAPSE_AT) return buf;
    const head = buf.slice(0, CTX);
    const tail = buf.slice(-CTX);
    const skipped = buf.length - head.length - tail.length;
    return [
      ...head,
      { type: "same" as const, text: "", aLine: null, bLine: null, skipped },
      ...tail,
    ];
  };

  const flush = () => {
    if (hunkRows.length === 0) return;
    const first = hunkRows[0];
    const aStart = first.aLine !== null ? first.aLine : first.bLine ?? 1;
    const bStart = first.bLine !== null ? first.bLine : first.aLine ?? 1;
    hunks.push({ aStart, bStart, rows: hunkRows });
    hunkRows = [];
  };

  for (const r of merged) {
    if (isChange(r)) {
      // Änderung: Puffer in den Hunk übernehmen (mit Einklappen)
      if (pending.length > 0) {
        hunkRows.push(...ctxRows(pending));
        pending = [];
        collapsed = false;
      }
      hunkRows.push(r);
    } else {
      pending.push(r);
      if (pending.length > COLLAPSE_AT && !collapsed) {
        collapsed = true;
      }
      if (pending.length > COLLAPSE_AT + CTX) {
        // Puffer wird zu lang: schließe den Hunk mit der Kontext-Vorderkante
        const keep = pending.slice(-CTX);
        hunkRows.push(...ctxRows(pending));
        flush();
        pending = [];
        pending.push(...keep);
        collapsed = false;
      }
    }
  }
  if (pending.length > 0) hunkRows.push(...ctxRows(pending));
  flush();

  return { hunks, stats: { add, del }, identical: add === 0 && del === 0 };
}
