import { useState, useCallback, useMemo, useEffect } from 'react'
import { ThemeProvider, Button, Spin, Select, Checkbox, Icon } from '@gravity-ui/uikit'
import {
  ArrowRotateLeft,
  ArrowUpFromLine,
  Code,
  Flask,
  Gear,
  Sparkles,
  TrashBin,
} from '@gravity-ui/icons'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import ClangVersionControl from './ClangVersionControl'
import TestsView from './TestsView'
import ConfigDrawer from './ConfigDrawer'
import MatrixDrawer from './MatrixDrawer'
import { computeDiff } from './useDiff'
import { getQueryParam, setQueryParam } from './url'
import { useDraftCount, publishDraft, discardAll, draftConfig, configKey } from './draftStore'

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

  const [configOpen, setConfigOpen] = useState(false)
  const [matrixOpen, setMatrixOpen] = useState(false)
  // a test picked from the matrix to jump to (id + a nonce so re-picking the
  // same test re-triggers the focus in TestsView)
  const [focusTest, setFocusTest] = useState<string | null>(null)
  const [focusSeq, setFocusSeq] = useState(0)
  const draftCount = useDraftCount()
  const [publishing, setPublishing] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

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
          // format against the local draft config for this (lang, version) if any;
          // otherwise the server applies that version's published config
          ...(draftConfig(configKey(language, clangVersion)) !== undefined
            ? { config: draftConfig(configKey(language, clangVersion)) }
            : {}),
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

  // jump from the matrix to a specific test in the Tests view
  const pickTest = useCallback((id: string) => {
    setView('tests')
    setFocusTest(id)
    setFocusSeq((s) => s + 1)
    setMatrixOpen(false)
  }, [])

  const handleReset = useCallback(() => {
    setInputCode(demos[language])
    setOutputCode('')
    setStatus({ kind: 'idle' })
  }, [language])

  const handlePublish = useCallback(async () => {
    setPublishing(true)
    try {
      const { ok, errors } = await publishDraft()
      if (!ok) {
        setStatus({ kind: 'error', message: `Publish failed: ${errors.join('; ')}` })
        return
      }
      setRefreshKey((k) => k + 1) // reload server tests in TestsView
      if (outputCode) handleFormat() // playground now reflects the published config
    } finally {
      setPublishing(false)
    }
  }, [outputCode, handleFormat])

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
          <div className="app-header-left">
          <h1 className="app-title">Format Quorum</h1>

          <div className="view-toggle">
            <Button
              view={view === 'playground' ? 'action' : 'flat'}
              size="s"
              onClick={() => setView('playground')}
            >
              <Icon data={Code} size={15} />
              Playground
            </Button>
            <Button
              view={view === 'tests' ? 'action' : 'flat'}
              size="s"
              onClick={() => setView('tests')}
            >
              <Icon data={Flask} size={15} />
              Tests
            </Button>
          </div>

          <Button
            view="outlined"
            size="s"
            className="config-open-btn"
            onClick={() => setConfigOpen(true)}
          >
            <Icon data={Gear} size={15} />
            Config
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

          {/* Tests view fills this with its own language/version pickers (via a
              portal) so they sit in the same centered spot as on the playground */}
          {view === 'tests' && <div className="app-header-center" id="tests-header-slot" />}

          <div className="app-header-right">
            {draftCount > 0 && (
              <div className="draft-bar" title="Local unsaved changes (config + tests)">
                <span className="draft-count">{draftCount} unsaved</span>
                <Button view="action" size="s" onClick={handlePublish} disabled={publishing}>
                  {publishing ? (
                    <span className="btn-spin">
                      <Spin size="xs" />
                      Publishing
                    </span>
                  ) : (
                    <>
                      <Icon data={ArrowUpFromLine} size={14} />
                      Publish
                    </>
                  )}
                </Button>
                <Button view="flat" size="s" onClick={discardAll} disabled={publishing}>
                  <Icon data={TrashBin} size={14} />
                  Discard
                </Button>
              </div>
            )}
            {view === 'playground' && (
              <div className="app-header-actions">
                <label className="diff-toggle">
                  <Checkbox checked={showDiff} onUpdate={setShowDiff} size="m" />
                  <span className="diff-toggle-label">Diff</span>
                </label>
                <Button view="outlined" size="s" onClick={handleReset}>
                  <Icon data={ArrowRotateLeft} size={14} />
                  Reset
                </Button>
                <Button
                  view="action"
                  size="s"
                  onClick={handleFormat}
                  disabled={status.kind === 'loading'}
                >
                  {status.kind === 'loading' ? (
                    <span className="btn-spin">
                      <Spin size="xs" />
                      Formatting
                    </span>
                  ) : (
                    <>
                      <Icon data={Sparkles} size={14} />
                      Format
                    </>
                  )}
                </Button>
              </div>
            )}
          </div>
        </header>

        {view === 'tests' ? (
          <TestsView
            playgroundInput={inputCode}
            playgroundOutput={outputCode}
            playgroundLanguage={language}
            refreshKey={refreshKey}
            onOpenMatrix={() => setMatrixOpen(true)}
            focusTest={focusTest}
            focusSeq={focusSeq}
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
          href="https://st.yandex-team.ru/LOGS-5799"
          target="_blank"
          rel="noopener noreferrer"
          title="Leave your comment/suggestion"
          aria-label="Leave your comment/suggestion"
        >
          😤
        </a>

        <ConfigDrawer
          open={configOpen}
          initialLang={language}
          initialVersion={clangVersion}
          onClose={() => setConfigOpen(false)}
          onSaved={() => {
            // reflect the new config in the playground right away, like a
            // test run refreshes its "Actual" column
            if (outputCode) handleFormat()
          }}
        />

        <MatrixDrawer
          open={matrixOpen}
          onClose={() => setMatrixOpen(false)}
          onPickTest={pickTest}
        />
      </div>
    </ThemeProvider>
  )
}
