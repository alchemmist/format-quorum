import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { ThemeProvider, Button, Spin, Select, Checkbox, Icon } from '@gravity-ui/uikit'
import { ArrowRotateLeft, Sparkles } from '@gravity-ui/icons'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import ClangVersionControl from './ClangVersionControl'
import FormatterControl from './FormatterControl'
import AddCustomFormatter from './AddCustomFormatter'
import AppHeader, { type View } from './AppHeader'
import TestsView from './TestsView'
import ConfigDrawer from './ConfigDrawer'
import MatrixDrawer from './MatrixDrawer'
import { computeDiff } from './useDiff'
import { getQueryParam, languageFromPath, setLanguagePath, setQueryParam } from './url'
import { useDraftCount, publishDraft, discardAll, formatOverrides } from './draftStore'
import { bundledLanguages, languageDemo, languageLabel } from './languages'
import {
  loadFormatters,
  availableLanguages,
  useFormatters,
  publishingEnabled,
  defaultFormatter,
  formatterById,
} from './formatters'

type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'done' }

function langFromPath(): Language {
  return languageFromPath(window.location.pathname, bundledLanguages())
}

export default function App() {
  // load the backend formatter registry once; pickers below re-render when ready
  const formatters = useFormatters()
  const canPublish = publishingEnabled()
  useEffect(() => {
    loadFormatters()
  }, [])

  const [language, setLanguage]   = useState<Language>(langFromPath)
  // which formatter the playground uses for the current language (only matters
  // when a language has more than one). Kept valid as language/registry change.
  const [formatter, setFormatter] = useState<string>('')
  // seed the formatter from ?formatter= once (so a shared link opens on the right
  // one, incl. a custom/patched formatter), then keep it valid as language changes
  const formatterSeeded = useRef(false)
  useEffect(() => {
    if (formatters.length === 0) return // wait for the registry
    const cur = formatterById(formatter)
    if (cur && cur.language === language) return // current pick is valid, keep it
    let next: string | undefined
    if (!formatterSeeded.current) {
      formatterSeeded.current = true
      const fromUrl = getQueryParam('formatter')
      const f = fromUrl ? formatterById(fromUrl) : undefined
      if (f && f.language === language) next = f.id
    }
    if (!next) next = defaultFormatter(language)?.id
    if (next) setFormatter(next)
  }, [language, formatters, formatter])

  // mirror the chosen formatter to the URL — only when it isn't the language's
  // default, so plain links stay clean but a non-default/custom one is shareable.
  // Guarded until seeding ran, else the first render (formatter still "") would
  // wipe a shared ?formatter= before the seed effect above can read it.
  useEffect(() => {
    if (!formatterSeeded.current) return
    const f = formatterById(formatter)
    setQueryParam('formatter', f && !f.default ? f.id : null)
  }, [formatter, formatters])
  const [inputCode, setInputCode] = useState<string>(() => languageDemo(langFromPath()))
  const [outputCode, setOutputCode] = useState<string>('')
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [showDiff, setShowDiff] = useState<boolean>(true)
  // the selected version *per formatter* — each versioned formatter (clang-format,
  // ruff, black) has its own set of installed versions, so a single shared value
  // would send e.g. a clang-format version to ruff. Shared across tabs (it's App
  // state, passed to both); the active formatter's version is mirrored to the URL.
  const [versionByFmt, setVersionByFmt] = useState<Record<string, string | undefined>>({})
  const setVersionFor = useCallback(
    (fid: string, v: string | undefined) =>
      setVersionByFmt((m) => ({ ...m, [fid]: v })),
    [],
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

  // the active (playground) formatter's selected version
  const version = formatter ? versionByFmt[formatter] : undefined

  // seed the active formatter's version from ?version= once the formatter is known
  const versionSeeded = useRef(false)
  useEffect(() => {
    if (versionSeeded.current || !formatter) return
    versionSeeded.current = true
    const v = getQueryParam('version')
    if (v) setVersionFor(formatter, v)
  }, [formatter, setVersionFor])

  // mirror the active formatter's version to the URL so a link is shareable.
  // Guarded until the version seed ran (same reason as ?formatter= above).
  useEffect(() => {
    if (!versionSeeded.current) return
    setQueryParam('version', version ?? null)
  }, [version])

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
      setLanguagePath(language)
    }
  }, [language])

  useEffect(() => {
    const onPop = () => {
      const lang = langFromPath()
      setLanguage(lang)
      setInputCode(languageDemo(lang))
      setOutputCode('')
      setStatus({ kind: 'idle' })
      setView(getQueryParam('view') === 'tests' ? 'tests' : 'playground')
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const handleLanguageChange = useCallback((lang: string) => {
    setLanguage(lang as Language)
    setInputCode(languageDemo(lang))
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
          // formatter + version + any local draft config (incl. shadow configs);
          // the server applies the selected version's published config otherwise
          ...formatOverrides(formatter || language, version),
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
  }, [inputCode, language, formatter, version])

  // jump from the matrix to a specific test in the Tests view
  const pickTest = useCallback((id: string) => {
    setView('tests')
    setFocusTest(id)
    setFocusSeq((s) => s + 1)
    setMatrixOpen(false)
  }, [])

  const handleReset = useCallback(() => {
    setInputCode(languageDemo(language))
    setOutputCode('')
    setStatus({ kind: 'idle' })
  }, [language])

  const handlePublish = useCallback(async () => {
    if (!publishingEnabled()) return
    setPublishing(true)
    try {
      const { ok, errors } = await publishDraft()
      setRefreshKey((k) => k + 1)
      if (!ok) {
        setStatus({ kind: 'error', message: `Publish failed: ${errors.join('; ')}` })
        return
      }
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
          publishingEnabled={canPublish}
          onPublish={handlePublish}
          onDiscard={discardAll}
          center={
            <>
              <Select
                value={[language]}
                onUpdate={(val) => handleLanguageChange(val[0])}
                size="s"
                width={120}
              >
                {availableLanguages().map((l) => (
                  <Select.Option key={l} value={l}>
                    {languageLabel(l)}
                  </Select.Option>
                ))}
              </Select>
              <FormatterControl language={language} value={formatter} onChange={setFormatter} />
              <AddCustomFormatter language={language} onCreated={setFormatter} />
              {formatterById(formatter)?.versioned && (
                <ClangVersionControl
                  key={formatter}
                  formatterId={formatter}
                  value={version}
                  onChange={(v) => setVersionFor(formatter, v)}
                />
              )}
            </>
          }
          actions={view === 'playground' ? (
            <>
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
            </>
          ) : undefined}
        />

        {view === 'tests' ? (
          <TestsView
            language={language}
            formatter={formatter}
            playgroundInput={inputCode}
            playgroundOutput={outputCode}
            versionByFmt={versionByFmt}
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
          initialFormatter={formatter || language}
          initialVersion={version}
          onClose={() => setConfigOpen(false)}
          onSaved={() => {
            // reflect the new config in the playground right away, like a
            // test run refreshes its "Actual" column
            if (outputCode) handleFormat()
          }}
        />

        <MatrixDrawer
          open={matrixOpen}
          language={language}
          formatter={formatter}
          onClose={() => setMatrixOpen(false)}
          onPickTest={pickTest}
        />
      </div>
    </ThemeProvider>
  )
}
