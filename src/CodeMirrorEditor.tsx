import CodeMirror from '@uiw/react-codemirror'
import { cpp } from '@codemirror/lang-cpp'
import { oneDark } from '@codemirror/theme-one-dark'

interface CodeMirrorEditorProps {
  value: string
  onChange?: (value: string) => void
  readOnly?: boolean
}

export default function CodeMirrorEditor({ value, onChange, readOnly = false }: CodeMirrorEditorProps) {
  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      theme={oneDark}
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
