import { useEffect, useRef } from 'react'
import { EditorView, lineNumbers, highlightActiveLine, highlightActiveLineGutter, keymap } from '@codemirror/view'
import { EditorState, Compartment } from '@codemirror/state'
import { cpp } from '@codemirror/lang-cpp'
import { defaultHighlightStyle, syntaxHighlighting, bracketMatching } from '@codemirror/language'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { oneDark } from '@codemirror/theme-one-dark'

interface CodeMirrorEditorProps {
  value: string
  onChange?: (value: string) => void
  readOnly?: boolean
}

// Custom theme to blend with Gravity UI dark
const gravityTheme = EditorView.theme({
  '&': {
    height: '100%',
    fontSize: '13px',
    fontFamily: "'SF Mono', 'Fira Mono', 'Cascadia Code', 'JetBrains Mono', Consolas, monospace",
    backgroundColor: '#1a1a1f',
  },
  '.cm-scroller': {
    overflow: 'auto',
    lineHeight: '1.65',
    fontFamily: 'inherit',
  },
  '.cm-content': {
    padding: '12px 0',
    caretColor: '#e2e2e2',
  },
  '.cm-gutters': {
    backgroundColor: '#1a1a1f',
    borderRight: '1px solid #2d2d35',
    color: '#4a4a5a',
    minWidth: '48px',
  },
  '.cm-lineNumbers .cm-gutterElement': {
    padding: '0 12px 0 8px',
    minWidth: '36px',
    textAlign: 'right',
    fontSize: '12px',
  },
  '.cm-activeLineGutter': {
    backgroundColor: '#22222a',
    color: '#7a7a9a',
  },
  '.cm-activeLine': {
    backgroundColor: '#22222a',
  },
  '.cm-line': {
    padding: '0 16px',
  },
  '.cm-cursor': {
    borderLeftColor: '#e2e2e2',
  },
  '.cm-selectionBackground': {
    backgroundColor: '#2c4a7c !important',
  },
  '&.cm-focused .cm-selectionBackground': {
    backgroundColor: '#2c4a7c',
  },
  '.cm-matchingBracket': {
    backgroundColor: '#3a3a4a',
    outline: '1px solid #5a5a7a',
  },
  // Scrollbar styling
  '.cm-scroller::-webkit-scrollbar': {
    width: '8px',
    height: '8px',
  },
  '.cm-scroller::-webkit-scrollbar-track': {
    background: 'transparent',
  },
  '.cm-scroller::-webkit-scrollbar-thumb': {
    background: '#3a3a4a',
    borderRadius: '4px',
  },
  '.cm-scroller::-webkit-scrollbar-thumb:hover': {
    background: '#4a4a5a',
  },
})

const editableCompartment = new Compartment()

export default function CodeMirrorEditor({ value, onChange, readOnly = false }: CodeMirrorEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useEffect(() => {
    if (!containerRef.current) return

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.docChanged && onChangeRef.current) {
        onChangeRef.current(update.state.doc.toString())
      }
    })

    const extensions = [
      oneDark,
      gravityTheme,
      lineNumbers(),
      highlightActiveLine(),
      highlightActiveLineGutter(),
      bracketMatching(),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      cpp(),
      editableCompartment.of(EditorState.readOnly.of(readOnly)),
      updateListener,
      EditorView.lineWrapping,
      ...(readOnly ? [] : [
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
      ]),
    ]

    const state = EditorState.create({
      doc: value,
      extensions,
    })

    const view = new EditorView({
      state,
      parent: containerRef.current,
    })

    viewRef.current = view

    return () => {
      view.destroy()
      viewRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly])

  // Sync external value changes into the editor
  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const current = view.state.doc.toString()
    if (current === value) return
    view.dispatch({
      changes: { from: 0, to: current.length, insert: value },
    })
  }, [value])

  return <div ref={containerRef} style={{ height: '100%', overflow: 'hidden' }} />
}
