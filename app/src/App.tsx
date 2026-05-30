import { useState, useCallback, useMemo } from 'react'
import { ThemeProvider, Button, Spin, Select, Checkbox } from '@gravity-ui/uikit'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import { computeDiff } from './useDiff'

// @ts-ignore — Vite raw import
import demoCpp from './demo.cpp?raw'
// @ts-ignore — Vite raw import
import demoPy from './demo.py?raw'

const demos: Record<Language, string> = {
  cpp:    demoCpp as string,
  python: demoPy as string,
}

type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'done' }

export default function App() {
  const [language, setLanguage]   = useState<Language>('cpp')
  const [inputCode, setInputCode] = useState<string>(demos.cpp)
  const [outputCode, setOutputCode] = useState<string>('')
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [showDiff, setShowDiff] = useState<boolean>(true)

  const diffRanges = useMemo(
    () => outputCode ? computeDiff(inputCode, outputCode) : [],
    [inputCode, outputCode],
  )

  const handleLanguageChange = useCallback((lang: string) => {
    setLanguage(lang as Language)
    setInputCode(demos[lang as Language])
    setOutputCode('')
    setStatus({ kind: 'idle' })
  }, [])

  const handleFormat = useCallback(async () => {
    setStatus({ kind: 'loading' })
    try {
      const res = await fetch('/api/format', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: inputCode, language }),
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
  }, [inputCode, language])

  const handleReset = useCallback(() => {
    setInputCode(demos[language])
    setOutputCode('')
    setStatus({ kind: 'idle' })
  }, [language])

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

          <div className="app-header-center">
            <Select
              value={[language]}
              onUpdate={(val) => handleLanguageChange(val[0])}
              size="s"
              width={120}
            >
              <Select.Option value="cpp">C++</Select.Option>
              <Select.Option value="python">Python</Select.Option>
            </Select>
          </div>

          <div className="app-header-actions">
            <label className="diff-toggle">
              <Checkbox
                checked={showDiff}
                onUpdate={setShowDiff}
                size="m"
              />
              <span className="diff-toggle-label">Diff</span>
            </label>
            <Button view="outlined" size="s" onClick={handleReset}>
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
          <div className="editor-pane">
            <div className="editor-pane-header">
              <span className="editor-pane-label">Input</span>
            </div>
            <div className="editor-pane-body">
              <CodeMirrorEditor
                value={inputCode}
                language={language}
                onChange={setInputCode}
                readOnly={false}
              />
            </div>
          </div>

          <div className="editor-pane">
            <div className="editor-pane-header">
              <span className="editor-pane-label output">Output</span>
            </div>
            <div className="editor-pane-body">
              <CodeMirrorEditor
                value={outputCode}
                language={language}
                readOnly={true}
                diffRanges={diffRanges}
                showDiff={showDiff}
              />
            </div>
          </div>
        </div>

        <div className="status-bar">
          <span className={`status-text${status.kind === 'error' ? ' error' : ''}`}>
            {statusText}
          </span>
        </div>

        <a
          className="feedback-fab"
          href={language === 'cpp'
            ? 'https://st.yandex-team.ru/LOGS-4271'
            : 'https://st.yandex-team.ru/DUTYLOGS-3928'}
          target="_blank"
          rel="noopener noreferrer"
          title="Leave your comment/suggestion"
          aria-label="Leave your comment/suggestion"
        >
          😤
        </a>
      </div>
    </ThemeProvider>
  )
}
