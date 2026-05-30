import CodeMirror from '@uiw/react-codemirror'
import { cpp } from '@codemirror/lang-cpp'
import { EditorView } from '@codemirror/view'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags } from '@lezer/highlight'

interface CodeMirrorEditorProps {
  value: string
  onChange?: (value: string) => void
  readOnly?: boolean
}

// Background that matches the top/bottom panel: #16161b
const BG = '#16161b'

const quietTheme = EditorView.theme(
  {
    '&': {
      backgroundColor: BG,
      color: '#9da5b3',
    },
    '.cm-content': {
      caretColor: '#9da5b3',
      padding: '12px 0',
    },
    '.cm-gutters': {
      backgroundColor: BG,
      borderRight: '1px solid #23232a',
      color: '#3e3e52',
    },
    '.cm-activeLineGutter': {
      backgroundColor: BG,
      color: '#5a5a7a',
    },
    '.cm-activeLine': {
      backgroundColor: '#1d1d23',
    },
    '.cm-line': {
      padding: '0 20px',
    },
    '.cm-cursor': {
      borderLeftColor: '#9da5b3',
    },
    '.cm-selectionBackground': {
      backgroundColor: '#2a3040 !important',
    },
    '&.cm-focused .cm-selectionBackground': {
      backgroundColor: '#2a3040',
    },
    '.cm-matchingBracket': {
      backgroundColor: '#2a3040',
      outline: 'none',
    },
    '.cm-scroller': {
      fontFamily: "'SF Mono', 'JetBrains Mono', 'Fira Mono', Consolas, monospace",
      lineHeight: '1.65',
    },

  },
  { dark: true },
)

// Calm, muted syntax colors — no eye-searing primaries
const quietHighlightStyle = HighlightStyle.define([
  { tag: tags.keyword,               color: '#7e9ec0' },               // blue-grey
  { tag: tags.controlKeyword,        color: '#7e9ec0' },
  { tag: tags.definitionKeyword,     color: '#7e9ec0' },
  { tag: tags.modifier,              color: '#7e9ec0' },
  { tag: tags.operatorKeyword,       color: '#7e9ec0' },
  { tag: tags.comment,               color: '#4a5060', fontStyle: 'italic' },
  { tag: tags.string,                color: '#89a87a' },               // muted green
  { tag: tags.special(tags.string),  color: '#89a87a' },
  { tag: tags.character,             color: '#89a87a' },
  { tag: tags.number,                color: '#b8a06a' },               // muted gold
  { tag: tags.bool,                  color: '#7e9ec0' },
  { tag: tags.null,                  color: '#7e9ec0' },
  { tag: tags.typeName,              color: '#8fb0a0' },               // muted teal
  { tag: tags.standard(tags.typeName), color: '#8fb0a0' },
  { tag: tags.propertyName,          color: '#9da5b3' },
  { tag: tags.function(tags.variableName), color: '#9da5b3' },
  { tag: tags.function(tags.propertyName), color: '#9da5b3' },
  { tag: tags.variableName,          color: '#9da5b3' },
  { tag: tags.namespace,             color: '#8fb0a0' },
  { tag: tags.operator,              color: '#7a8090' },
  { tag: tags.punctuation,           color: '#585e6e' },
  { tag: tags.bracket,               color: '#585e6e' },
  { tag: tags.processingInstruction, color: '#7e9ec0' },               // #include / #define
  { tag: tags.meta,                  color: '#5a6272' },
  { tag: tags.special(tags.name),    color: '#9da5b3' },
  { tag: tags.escape,                color: '#b8a06a' },
  { tag: tags.invalid,               color: '#7a4040' },
  { tag: tags.labelName,             color: '#8fb0a0' },
])

const theme = [quietTheme, syntaxHighlighting(quietHighlightStyle)]

export default function CodeMirrorEditor({ value, onChange, readOnly = false }: CodeMirrorEditorProps) {
  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      theme={theme}
      extensions={[cpp()]}
      height="100%"
      style={{ height: '100%', fontSize: '13px' }}
      basicSetup={{
        lineNumbers: true,
        highlightActiveLine: true,
        bracketMatching: true,
        history: !readOnly,
      }}
    />
  )
}
