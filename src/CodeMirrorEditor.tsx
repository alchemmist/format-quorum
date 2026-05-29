import { useEffect, useRef } from 'react'
import {
  EditorView,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
} from '@codemirror/view'
import { EditorState, Compartment } from '@codemirror/state'
import { cpp } from '@codemirror/lang-cpp'
import { syntaxHighlighting, bracketMatching } from '@codemirror/language'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { oneDarkHighlightStyle } from '@codemirror/theme-one-dark'

interface CodeMirrorEditorProps {
  value: string
  onChange?: (value: string) => void
  readOnly?: boolean
}

// dark: true tells CodeMirror this is a dark theme — critical for syntax highlighting
const gravityTheme = EditorView.theme(
  {
    '&': {
      height: '100%',
      fontSize: '13px',
      fontFamily: "'SF Mono', 'Fira Mono', 'Cascadia Code', 'JetBrains Mono', Consolas, monospace",
      backgroundColor: '#1a1a1f',
      color: '#abb2bf',
    },
    '.cm-scroller': {
      overflow: 'auto',
      lineHeight: '1.65',
      fontFamily: 'inherit',
    },
    '.cm-content': {
      padding: '12px 0',
      caretColor: '#cdd6f4',
    },
    '.cm-gutters': {
      backgroundColor: '#16161b',
      borderRight: '1px solid #2d2d35',
      color: '#3e3e52',
    },
    '.cm-lineNumbers .cm-gutterElement': {
      padding: '0 14px 0 8px',
      minWidth: '40px',
      textAlign: 'right',
      fontSize: '12px',
      userSelect: 'none',
    },
    '.cm-activeLineGutter': {
      backgroundColor: '#1e1e28',
      color: '#6e6e8e',
    },
    '.cm-activeLine': {
      backgroundColor: '#1e1e28',
    },
    '.cm-line': {
      padding: '0 20px',
    },
    '.cm-cursor, .cm-dropCursor': {
      borderLeftColor: '#cdd6f4',
    },
    '.cm-selectionBackground': {
      backgroundColor: '#2a3f6a !important',
    },
    '&.cm-focused .cm-selectionBackground': {
      backgroundColor: '#2a3f6a',
    },
    '.cm-matchingBracket': {
      backgroundColor: '#3a3d5c',
      outline: '1px solid #5a5e8a',
      borderRadius: '2px',
    },
    '.cm-scroller::-webkit-scrollbar': {
      width: '8px',
      height: '8px',
    },
    '.cm-scroller::-webkit-scrollbar-track': {
      background: 'transparent',
    },
    '.cm-scroller::-webkit-scrollbar-thumb': {
      background: '#2d2d3a',
      borderRadius: '4px',
    },
    '.cm-scroller::-webkit-scrollbar-thumb:hover': {
      background: '#3d3d4a',
    },
  },
  { dark: true },
)

export default function CodeMirrorEditor({ value, onChange, readOnly = false }: CodeMirrorEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const readOnlyCompartment = useRef(new Compartment())

  useEffect(() => {
    if (!containerRef.current) return

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.docChanged && onChangeRef.current) {
        onChangeRef.current(update.state.doc.toString())
      }
    })

    const extensions = [
      gravityTheme,
      syntaxHighlighting(oneDarkHighlightStyle),
      cpp(),
      lineNumbers(),
      highlightActiveLine(),
      highlightActiveLineGutter(),
      bracketMatching(),
      readOnlyCompartment.current.of(EditorState.readOnly.of(readOnly)),
      updateListener,
      EditorView.lineWrapping,
      ...(readOnly
        ? []
        : [history(), keymap.of([...defaultKeymap, ...historyKeymap])]),
    ]

    const state = EditorState.create({ doc: value, extensions })
    const view = new EditorView({ state, parent: containerRef.current })
    viewRef.current = view

    return () => {
      view.destroy()
      viewRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly])

  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const current = view.state.doc.toString()
    if (current === value) return
    view.dispatch({
      changes: { from: 0, to: current.length, insert: value },
      scrollIntoView: false,
    })
  }, [value])

  return <div ref={containerRef} style={{ height: '100%', overflow: 'hidden' }} />
}
