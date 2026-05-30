import { useState, useCallback } from 'react'
import { ThemeProvider, Button, Spin } from '@gravity-ui/uikit'
import CodeMirrorEditor from './CodeMirrorEditor'
import demoCode from './demo-code'

type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'done' }

export default function App() {
  const [inputCode, setInputCode] = useState<string>(demoCode)
  const [outputCode, setOutputCode] = useState<string>('')
  const [status, setStatus] = useState<Status>({ kind: 'idle' })

  const handleFormat = useCallback(async () => {
    setStatus({ kind: 'loading' })
    try {
      const res = await fetch('/api/format', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: inputCode }),
      })
      const data = await res.json()
      if (!res.ok) {
        setStatus({ kind: 'error', message: data.error ?? 'Unknown error' })
        return
      }
      setOutputCode(data.formatted)
      setStatus({ kind: 'done' })
    } catch (e) {
      setStatus({ kind: 'error', message: String(e) })
    }
  }, [inputCode])

  const handleReset = useCallback(() => {
    setInputCode(demoCode)
    setOutputCode('')
    setStatus({ kind: 'idle' })
  }, [])

  const statusText =
    status.kind === 'loading'
      ? 'Formatting...'
      : status.kind === 'error'
        ? `Error: ${status.message}`
        : status.kind === 'done'
          ? 'Done'
          : ''

  return (
    <ThemeProvider theme="dark">
      <div className="app-layout">
        <header className="app-header">
          <h1 className="app-title">Format Quorum</h1>
          <div className="app-header-actions">
            <Button
              view="outlined"
              size="s"
              onClick={handleReset}
              title="Reset to demo.cpp"
            >
              Reset
            </Button>
            <Button
              view="action"
              size="s"
              onClick={handleFormat}
              disabled={status.kind === 'loading'}
            >
              {status.kind === 'loading' ? (
                <>
                  <Spin size="xs" />
                  &nbsp;Formatting
                </>
              ) : (
                'Format'
              )}
            </Button>
          </div>
        </header>

        <div className="editors-container">
          {/* Left pane — editable input */}
          <div className="editor-pane">
            <div className="editor-pane-header">
              <span className="editor-pane-label">Input</span>
            </div>
            <div className="editor-pane-body">
              <CodeMirrorEditor
                value={inputCode}
                onChange={setInputCode}
                readOnly={false}
              />
            </div>
          </div>

          {/* Right pane — read-only output */}
          <div className="editor-pane">
            <div className="editor-pane-header">
              <span className="editor-pane-label output">Output</span>
            </div>
            <div className="editor-pane-body">
              <CodeMirrorEditor
                value={outputCode}
                readOnly={true}
              />
            </div>
          </div>
        </div>

        <div className="status-bar">
          <span className={`status-text${status.kind === 'error' ? ' error' : ''}`}>
            {statusText}
          </span>
        </div>
      </div>
    </ThemeProvider>
  )
}
