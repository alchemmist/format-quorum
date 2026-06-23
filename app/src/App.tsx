import { useState, useCallback, useMemo, useEffect } from 'react'
import { ThemeProvider, Button, Spin, Select, Checkbox } from '@gravity-ui/uikit'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import ClangVersionControl from './ClangVersionControl'
import TestsView from './TestsView'
import { computeDiff } from './useDiff'
import { getQueryParam, setQueryParam } from './url'

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

function langFromPath(): Language {
  const seg = window.location.pathname.replace(/^\//, '')
  return seg === 'python' ? 'python' : 'cpp'
}

export default function App() {
  const [language, setLanguage]   = useState<Language>(langFromPath)
  const [inputCode, setInputCode] = useState<string>(() => demos[langFromPath()])
  const [outputCode, setOutputCode] = useState<string>('')
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [showDiff, setShowDiff] = useState<boolean>(true)
  const [clangVersion, setClangVersion] = useState<string | undefined>(undefined)
  const [view, setView] = useState<'playground' | 'tests'>(
    () => (getQueryParam('view') === 'tests' ? 'tests' : 'playground'),
  )

  // keep the active view in the URL so a Tests link is shareable
  useEffect(() => {
    setQueryParam('view', view === 'tests' ? 'tests' : null)
  }, [view])

  const diffRanges = useMemo(
    () => outputCode ? computeDiff(inputCode, outputCode) : [],
    [inputCode, outputCode],
  )

  useEffect(() => {
    const path = `/${language}`
    if (window.location.pathname !== path) {
      window.history.pushState(null, '', path)
    }
  }, [language])

  useEffect(() => {
    const onPop = () => {
      const lang = langFromPath()
      setLanguage(lang)
      setInputCode(demos[lang])
      setOutputCode('')
      setStatus({ kind: 'idle' })
      setView(getQueryParam('view') === 'tests' ? 'tests' : 'playground')
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

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
        body: JSON.stringify({
          code: inputCode,
          language,
          ...(language === 'cpp' && clangVersion ? { clang_version: clangVersion } : {}),
        }),
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
  }, [inputCode, language, clangVersion])

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

          <div className="view-toggle">
            <Button
              view={view === 'playground' ? 'action' : 'flat'}
              size="s"
              onClick={() => setView('playground')}
            >
              Playground
            </Button>
            <Button
              view={view === 'tests' ? 'action' : 'flat'}
              size="s"
              onClick={() => setView('tests')}
            >
              Tests
            </Button>
          </div>

          {view === 'playground' && (
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
              {language === 'cpp' && (
                <ClangVersionControl
                  value={clangVersion}
                  onChange={setClangVersion}
                />
              )}
            </div>
          )}

          {view === 'playground' && (
            <div className="app-header-actions">
              <label className="diff-toggle">
                <Checkbox
                  checked={showDiff}
                  onUpdate={setShowDiff}
                  size="m"
                />
                <span className="diff-toggle-label">Diff</span>
              </label>
              <a
                className="config-link-btn"
                href={language === 'cpp' ? '/clang-format' : '/ruff.toml'}
                target="_blank"
                rel="noopener noreferrer"
              >
                Config
              </a>
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
          )}
        </header>

        {view === 'tests' ? (
          <TestsView
            playgroundInput={inputCode}
            playgroundOutput={outputCode}
            playgroundLanguage={language}
          />
        ) : (
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
        )}

        <div className="status-bar">
          <span className={`status-text${status.kind === 'error' ? ' error' : ''}`}>
            {statusText}
          </span>
          <a
            className="github-link"
            href="https://github.com/alchemmist/format-quorum"
            target="_blank"
            rel="noopener noreferrer"
          >
            github
          </a>
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
