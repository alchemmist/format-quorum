import { StateEffect, StateField } from '@codemirror/state'
import type { Text } from '@codemirror/state'
import { Decoration, EditorView } from '@codemirror/view'
import type { DecorationSet } from '@codemirror/view'
import type { Extension } from '@codemirror/state'

export interface DiffRange {
  lineIdx: number   // 0-based line index in output (b)
  from: number      // char offset from line start
  to: number        // char offset from line start
}

// ── Diff computation ──────────────────────────────────────────────────────────

function lcsPairs(a: string[], b: string[]): Array<[number, number]> {
  const m = a.length
  const n = b.length
  if (m === 0 || n === 0) return []
  const dp = new Uint16Array((m + 1) * (n + 1))
  const W = n + 1
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i * W + j] = a[i] === b[j]
        ? dp[(i + 1) * W + (j + 1)] + 1
        : Math.max(dp[(i + 1) * W + j], dp[i * W + (j + 1)])
    }
  }
  const pairs: Array<[number, number]> = []
  let i = 0, j = 0
  while (i < m && j < n) {
    if (a[i] === b[j]) { pairs.push([i, j]); i++; j++ }
    else if (dp[(i + 1) * W + j] >= dp[i * W + (j + 1)]) i++
    else j++
  }
  return pairs
}

const MAX_LINES = 2000

export function computeDiff(a: string, b: string): DiffRange[] {
  if (a === b) return []
  const aLines = a.split('\n')
  const bLines = b.split('\n')
  if (aLines.length > MAX_LINES || bLines.length > MAX_LINES) {
    return bLines.map((line, i) => ({ lineIdx: i, from: 0, to: line.length }))
  }
  const matched = new Set(lcsPairs(aLines, bLines).map(([, bj]) => bj))
  const result: DiffRange[] = []
  bLines.forEach((line, bj) => {
    if (!matched.has(bj)) result.push({ lineIdx: bj, from: 0, to: line.length })
  })
  return result
}

// ── CodeMirror extension ──────────────────────────────────────────────────────

/**
 * Dispatching this effect on an EditorView updates diff highlighting.
 * The effect is shared (StateEffect instances are just descriptors, safe to share).
 */
export const setDiffEffect = StateEffect.define<{ ranges: DiffRange[]; show: boolean }>()

const lineMark = Decoration.line({ class: 'cm-diff-changed-line' })

function buildDecoSet(ranges: DiffRange[], doc: Text): DecorationSet {
  const marks: ReturnType<typeof lineMark.range>[] = []
  for (const r of ranges) {
    const lineNo = r.lineIdx + 1
    if (lineNo > doc.lines) continue
    marks.push(lineMark.range(doc.line(lineNo).from))
  }
  marks.sort((a, b) => a.from - b.from)
  return marks.length > 0 ? Decoration.set(marks) : Decoration.none
}

/**
 * Creates a fresh StateField per call — call once per editor instance so that
 * multiple editors don't share the same field identity.
 */
function makeDiffField() {
  return StateField.define<DecorationSet>({
    create: () => Decoration.none,
    update(deco, tr) {
      for (const effect of tr.effects) {
        if (effect.is(setDiffEffect)) {
          return effect.value.show
            ? buildDecoSet(effect.value.ranges, tr.newDoc)
            : Decoration.none
        }
      }
      return deco.map(tr.changes)
    },
    provide: f => EditorView.decorations.from(f),
  })
}

/**
 * Call once per editor instance (e.g. in a useRef initializer).
 * Returns the Extension to add to that editor's `extensions` array.
 * Control highlighting by dispatching setDiffEffect on the EditorView.
 */
export function createDiffExtension(): Extension {
  return makeDiffField()
}
