/**
 * Change 084: Kollaborations-Lock — pure Ableitung aus Yjs-Awareness-States.
 *
 * Das Awareness-Feld `editing` trägt seit 084 den Segment-Index (number)
 * des gerade editierten Segments oder `false`. `editorsFromStates`
 * extrahiert daraus (a) die Namen aller fremden aktiven Editoren und
 * (b) den ersten fremden Edit-Lock { index, name } — mit aktivem Lock
 * dürfen keine Strukturoperationen (Grenz-Drag, Insert, Delete, Split)
 * mehr laufen und das betroffene Segment ist nicht editierbar.
 */
export interface EditorState {
  user?: { name?: string };
  /** number = Segment-Index im Edit-Mode; false/undefined = inaktiv. */
  editing?: boolean | number;
}

export interface EditLock {
  index: number;
  name: string;
}

export interface EditorsResult {
  activeEditors: string[];
  editLock: EditLock | null;
}

export function editorsFromStates(
  states: Map<number, unknown> | Record<number, unknown>,
  myId: number,
): EditorsResult {
  const names = new Set<string>();
  let lock: EditLock | null = null;
  const iter =
    states instanceof Map
      ? states.entries()
      : (Object.entries(states) as Iterable<[string, unknown]>);
  for (const [clientIdRaw, raw] of iter) {
    if (Number(clientIdRaw) === myId) continue;
    const s = raw as EditorState | undefined;
    if (!s) continue;
    const editingIdx = typeof s.editing === "number" ? s.editing : false;
    const name =
      typeof s.user?.name === "string" && s.user.name ? s.user.name : "";
    if (editingIdx !== false) {
      if (name) names.add(name);
      if (!lock && name) lock = { index: editingIdx, name };
    }
  }
  return { activeEditors: [...names], editLock: lock };
}
