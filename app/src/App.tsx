import { useState, useCallback, useMemo, useEffect } from 'react'
import { ThemeProvider, Button, Spin, Select, Checkbox, Icon } from '@gravity-ui/uikit'
import { ArrowRotateLeft, Sparkles } from '@gravity-ui/icons'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import ClangVersionControl from './ClangVersionControl'
import AppHeader, { type View } from './AppHeader'
import { HeaderSlot } from './HeaderSlot'
import TestsView from './TestsView'
import ConfigDrawer from './ConfigDrawer'
import MatrixDrawer from './MatrixDrawer'
import { computeDiff } from './useDiff'
import { getQueryParam, setQueryParam } from './url'
import { useDraftCount, publishDraft, discardAll, formatOverrides } from './draftStore'

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
  // the selected clang-format version is shared across tabs (playground + tests)
  // and kept in the URL so a link is shareable
  const [clangVersion, setClangVersion] = useState<string | undefined>(
    () => getQueryParam('version') ?? undefined,
  )
  const [view, setView] = useState<View>(
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

  // keep the shared clang-format version in the URL (both tabs read it)
  useEffect(() => {
    setQueryParam('version', clangVersion ?? null)
  }, [clangVersion])

  // Ctrl/Cmd + , toggles the Config drawer (it opens on the header's version)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === ',') {
        e.preventDefault()
        setConfigOpen((o) => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

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
      setClangVersion(getQueryParam('version') ?? undefined)
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
          // clang_version + any local draft config (incl. shadow configs); the
          // server applies the selected version's published config otherwise
          ...formatOverrides(language, clangVersion),
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
        <AppHeader
          view={view}
          onChangeView={setView}
          onOpenConfig={() => setConfigOpen(true)}
          draftCount={draftCount}
          publishing={publishing}
          onPublish={handlePublish}
          onDiscard={discardAll}
        />

        {/* the playground contributes its own pickers + actions to the shared header */}
        {view === 'playground' && (
          <>
            <HeaderSlot slot="center">
              <Select
                value={[language]}
                onUpdate={(val) => handleLanguageChange(val[0])}
                size="s"
                width={120}
              >
                <Select.Option value="cpp">C++</Select.Option>
                <Select.Option value="python">Python</Select.Option>
              </Select>
              {/* the version selector is shown on every tab; its value is shared
                  (it just doesn't affect ruff/python formatting) */}
              <ClangVersionControl value={clangVersion} onChange={setClangVersion} />
            </HeaderSlot>
            <HeaderSlot slot="right">
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
            </HeaderSlot>
          </>
        )}

        {view === 'tests' ? (
          <TestsView
            playgroundInput={inputCode}
            playgroundOutput={outputCode}
            playgroundLanguage={language}
            clangVersion={clangVersion}
            onClangVersionChange={setClangVersion}
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
