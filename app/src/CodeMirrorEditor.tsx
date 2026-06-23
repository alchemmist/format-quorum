import { useEffect, useRef, useMemo } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import type { ReactCodeMirrorRef } from '@uiw/react-codemirror'
import { cpp } from '@codemirror/lang-cpp'
import { python } from '@codemirror/lang-python'
import { EditorView } from '@codemirror/view'
import { HighlightStyle, syntaxHighlighting, indentUnit } from '@codemirror/language'
import { tags } from '@lezer/highlight'
import type { Extension } from '@codemirror/state'
import { createDiffExtension, setDiffEffect, type DiffRange } from './useDiff'

export type Language = 'cpp' | 'python'

interface CodeMirrorEditorProps {
  value: string
  language: Language
  onChange?: (value: string) => void
  readOnly?: boolean
  /** Pass diffRanges to enable diff highlighting on this editor instance */
  diffRanges?: DiffRange[]
  showDiff?: boolean
  /** Skip the language extension (e.g. for config files) */
  plainText?: boolean
}

const BG = '#16161b'

const quietTheme = EditorView.theme(
  {
    '&': { backgroundColor: BG, color: '#9da5b3' },
    '.cm-content': { caretColor: '#9da5b3', padding: '12px 0' },
    '.cm-gutters': {
      backgroundColor: BG,
      borderRight: 'none',
      color: '#3e3e52',
    },
    '.cm-activeLineGutter': { backgroundColor: BG, color: '#5a5a7a' },
    '.cm-activeLine': { backgroundColor: '#1d1d23' },
    '.cm-line': { padding: '0 20px' },
    '.cm-cursor': { borderLeftColor: '#9da5b3' },
    '.cm-selectionBackground': { backgroundColor: '#2a3040 !important' },
    '&.cm-focused .cm-selectionBackground': { backgroundColor: '#2a3040' },
    '.cm-matchingBracket': { backgroundColor: '#2a3040', outline: 'none' },
    '.cm-scroller': {
      fontFamily: "'SF Mono', 'JetBrains Mono', 'Fira Mono', Consolas, monospace",
      lineHeight: '1.65',
    },
  },
  { dark: true },
)

const quietHighlightStyle = HighlightStyle.define([
  { tag: tags.keyword,                     color: '#7e9ec0' },
  { tag: tags.controlKeyword,              color: '#7e9ec0' },
  { tag: tags.definitionKeyword,           color: '#7e9ec0' },
  { tag: tags.modifier,                    color: '#7e9ec0' },
  { tag: tags.operatorKeyword,             color: '#7e9ec0' },
  { tag: tags.comment,                     color: '#4a5060', fontStyle: 'italic' },
  { tag: tags.string,                      color: '#89a87a' },
  { tag: tags.special(tags.string),        color: '#89a87a' },
  { tag: tags.character,                   color: '#89a87a' },
  { tag: tags.number,                      color: '#b8a06a' },
  { tag: tags.bool,                        color: '#7e9ec0' },
  { tag: tags.null,                        color: '#7e9ec0' },
  { tag: tags.typeName,                    color: '#8fb0a0' },
  { tag: tags.standard(tags.typeName),     color: '#8fb0a0' },
  { tag: tags.propertyName,               color: '#9da5b3' },
  { tag: tags.function(tags.variableName), color: '#9da5b3' },
  { tag: tags.function(tags.propertyName), color: '#9da5b3' },
  { tag: tags.variableName,               color: '#9da5b3' },
  { tag: tags.namespace,                  color: '#8fb0a0' },
  { tag: tags.operator,                   color: '#7a8090' },
  { tag: tags.punctuation,               color: '#585e6e' },
  { tag: tags.bracket,                   color: '#585e6e' },
  { tag: tags.processingInstruction,     color: '#7e9ec0' },
  { tag: tags.meta,                      color: '#5a6272' },
  { tag: tags.special(tags.name),        color: '#9da5b3' },
  { tag: tags.escape,                    color: '#b8a06a' },
  { tag: tags.invalid,                   color: '#7a4040' },
  { tag: tags.labelName,                 color: '#8fb0a0' },
  { tag: tags.self,                      color: '#7e9ec0' },
  { tag: tags.atom,                      color: '#7e9ec0' },
  { tag: tags.derefOperator,             color: '#7a8090' },
])

const baseTheme: Extension = [
  quietTheme,
  syntaxHighlighting(quietHighlightStyle),
  // indent with 4 spaces (not a tab) — for both auto-indent and the Tab key
  indentUnit.of('    '),
]

const langExtension: Record<Language, Extension> = {
  cpp:    cpp(),
  python: python(),
}

export default function CodeMirrorEditor({
  value,
  language,
  onChange,
  readOnly = false,
  diffRanges,
  showDiff = false,
  plainText = false,
}: CodeMirrorEditorProps) {
  const cmRef = useRef<ReactCodeMirrorRef>(null)
  const hasDiff = diffRanges !== undefined

  // Create one diff field per editor instance (stable across re-renders)
  const diffExtRef = useRef<Extension | null>(null)
  if (hasDiff && diffExtRef.current === null) {
    diffExtRef.current = createDiffExtension()
  }

  // Stable extensions array — only rebuilds when language changes
  const extensions = useMemo<Extension[]>(() => {
    const exts: Extension[] = plainText ? [] : [langExtension[language]]
    if (hasDiff && diffExtRef.current !== null) {
      exts.push(diffExtRef.current)
    }
    return exts
    // diffExtRef.current is stable; hasDiff and language are the real deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language, hasDiff, plainText])

  // Keep a ref to latest ranges/show so we can dispatch from onCreateEditor
  const diffStateRef = useRef({ ranges: diffRanges ?? [], show: showDiff })
  diffStateRef.current = { ranges: diffRanges ?? [], show: showDiff }

  const dispatchDiff = (view: EditorView) => {
    view.dispatch({
      effects: setDiffEffect.of(diffStateRef.current),
    })
  }

  // Dispatch effect whenever ranges or showDiff flag change
  useEffect(() => {
    if (!hasDiff) return
    const view = cmRef.current?.view
    if (!view) return
    dispatchDiff(view)
  }, [diffRanges, showDiff, hasDiff]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <CodeMirror
      ref={cmRef}
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      theme={baseTheme}
      extensions={extensions}
      height="100%"
      style={{ height: '100%', fontSize: '13px' }}
      basicSetup={{
        lineNumbers: true,
        highlightActiveLine: true,
        bracketMatching: true,
        history: !readOnly,
        foldGutter: false,
      }}
      onCreateEditor={(view) => {
        if (hasDiff) dispatchDiff(view)
      }}
    />
  )
}
