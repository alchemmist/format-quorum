import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  Button,
  Checkbox,
  Dialog,
  Icon,
  Label,
  Select,
  Spin,
  Text,
  TextInput,
} from '@gravity-ui/uikit'
import { LayoutCells, Magnifier, Pencil, PlayFill, Plus, TrashBin } from '@gravity-ui/icons'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import { getQueryParam, setQueryParam, testShareUrl } from './url'
import { computeDiff } from './useDiff'
import type { TestCase } from './types'
import {
  useDraft,
  effectiveTests,
  addDraftTest,
  patchTest,
  removeTest as draftRemoveTest,
  newDraftId,
  draftConfig,
  configKey,
} from './draftStore'

export type { TestCase } from './types'

// match the backend's comparison: CRLF→LF, strip trailing newlines
const norm = (s: string) => s.replace(/\r\n/g, '\n').replace(/\n+$/, '')

interface RunResult {
  id: string
  passed: boolean
  actual: string
  error: string | null
}

type Display = 'pass' | 'fail' | 'muted' | 'unknown'

interface Props {
  playgroundInput: string
  playgroundOutput: string
  playgroundLanguage: Language
  /** bumped after a Publish so the server tests reload */
  refreshKey?: number
  /** open the tests×versions matrix drawer */
  onOpenMatrix?: () => void
  /** a test id to focus + scroll to (picked from the matrix) */
  focusTest?: string | null
  /** nonce: bumping it re-triggers the focus even for the same test id */
  focusSeq?: number
}

function displayStatus(test: TestCase, result?: RunResult): Display {
  if (test.muted) return 'muted'
  if (!result) return 'unknown'
  return result.passed ? 'pass' : 'fail'
}

const STATUS_THEME: Record<Display, 'success' | 'danger' | 'warning' | 'unknown'> = {
  pass: 'success',
  fail: 'danger',
  muted: 'warning',
  unknown: 'unknown',
}

const STATUS_LABEL: Record<Display, string> = {
  pass: 'pass',
  fail: 'fail',
  muted: 'muted',
  unknown: 'not run',
}

const emptyForm = (lang: Language): Omit<TestCase, 'id'> => ({
  name: '',
  language: lang,
  input: '',
  expected: '',
  muted: false,
  note: '',
})

export default function TestsView({
  playgroundInput,
  playgroundOutput,
  playgroundLanguage,
  refreshKey,
  onOpenMatrix,
  focusTest,
  focusSeq,
}: Props) {
  const initialFilter = getQueryParam('filter')
  const [serverTests, setServerTests] = useState<TestCase[]>([])
  const draft = useDraft()
  // what the UI shows: server tests with the local draft overlaid
  const tests = useMemo(() => effectiveTests(serverTests), [serverTests, draft])
  const [results, setResults] = useState<Record<string, RunResult>>({})
  const [running, setRunning] = useState(false)
  const [runningId, setRunningId] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | Language>(
    initialFilter === 'cpp' || initialFilter === 'python' ? initialFilter : 'all',
  )
  const initialStatus = getQueryParam('status')
  const [statusFilter, setStatusFilter] = useState<'all' | Display>(
    initialStatus === 'pass' || initialStatus === 'fail' || initialStatus === 'muted'
      ? initialStatus
      : 'all',
  )
  const [versions, setVersions] = useState<string[]>([])
  const [runVersion, setRunVersion] = useState<string | undefined>(
    () => getQueryParam('version') ?? undefined,
  )
  const [focusedId, setFocusedId] = useState<string | null>(() => getQueryParam('test'))
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(getQueryParam('test') ? [getQueryParam('test') as string] : []),
  )
  const [error, setError] = useState<string | null>(null)
  const didScrollRef = useRef(false)
  // header slot (rendered by App) where the language/version pickers go, so they
  // sit in the same centered spot as the playground's pickers
  const [headerSlot, setHeaderSlot] = useState<HTMLElement | null>(null)
  useEffect(() => {
    setHeaderSlot(document.getElementById('tests-header-slot'))
  }, [])

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState(emptyForm(playgroundLanguage))

  const loadTests = useCallback(async () => {
    const res = await fetch('/api/tests')
    setServerTests(await res.json())
  }, [])

  // reload server tests after a Publish (refreshKey bump); drop stale results
  useEffect(() => {
    if (refreshKey === undefined) return
    loadTests()
    setResults({})
  }, [refreshKey, loadTests])

  useEffect(() => {
    loadTests()
    fetch('/api/clang-versions')
      .then((r) => r.json())
      .then((d) => {
        setVersions(d.versions ?? [])
        // don't override a version that came from the URL
        setRunVersion((prev) => prev ?? d.default ?? undefined)
      })
      .catch(() => {})
  }, [loadTests])

  // keep the run parameters in the URL so the link is shareable
  useEffect(() => {
    setQueryParam('filter', filter === 'all' ? null : filter)
  }, [filter])
  useEffect(() => {
    setQueryParam('version', runVersion ?? null)
  }, [runVersion])
  useEffect(() => {
    setQueryParam('status', statusFilter === 'all' ? null : statusFilter)
  }, [statusFilter])

  // once the tests are loaded, scroll to the test linked via ?test=<id>
  useEffect(() => {
    if (didScrollRef.current || !focusedId || tests.length === 0) return
    const el = document.getElementById(`test-${focusedId}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      didScrollRef.current = true
    }
  }, [tests, focusedId])

  // focus + scroll to a test picked from the version matrix; clear filters that
  // could hide it, expand it, and update the shareable ?test= URL
  useEffect(() => {
    if (!focusSeq || !focusTest) return
    setFilter('all')
    setStatusFilter('all')
    setFocusedId(focusTest)
    setQueryParam('test', focusTest)
    setExpanded((prev) => new Set(prev).add(focusTest))
    const t = window.setTimeout(() => {
      document
        .getElementById(`test-${focusTest}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 80)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusSeq])

  // tests after the language filter — summary counts are computed over these
  const langTests = useMemo(
    () => tests.filter((t) => filter === 'all' || t.language === filter),
    [tests, filter],
  )

  const summary = useMemo(() => {
    let pass = 0
    let fail = 0
    let muted = 0
    for (const t of langTests) {
      const s = displayStatus(t, results[t.id])
      if (s === 'pass') pass++
      else if (s === 'fail') fail++
      else if (s === 'muted') muted++
    }
    return { pass, fail, muted, total: langTests.length }
  }, [langTests, results])

  // the status chips additionally narrow the list (counts stay full)
  const visibleTests = useMemo(
    () =>
      statusFilter === 'all'
        ? langTests
        : langTests.filter((t) => displayStatus(t, results[t.id]) === statusFilter),
    [langTests, statusFilter, results],
  )

  // run a test client-side: format its input against the effective config
  // (local draft if any, else the server's) and compare to the expected output.
  const formatAndCompare = useCallback(
    async (test: TestCase): Promise<RunResult> => {
      try {
        // run against the local draft config for this (lang, run-version) if any;
        // otherwise the server uses that version's published config
        const cfg = draftConfig(configKey(test.language, runVersion))
        const res = await fetch('/api/format', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            code: test.input,
            language: test.language,
            ...(test.language === 'cpp' && runVersion ? { clang_version: runVersion } : {}),
            ...(cfg !== undefined ? { config: cfg } : {}),
          }),
        })
        const data = await res.json()
        if (!res.ok) {
          return { id: test.id, passed: false, actual: '', error: data.error ?? 'Format failed' }
        }
        return {
          id: test.id,
          passed: norm(data.formatted) === norm(test.expected),
          actual: data.formatted,
          error: null,
        }
      } catch (e) {
        return { id: test.id, passed: false, actual: '', error: String(e) }
      }
    },
    [runVersion],
  )

  const runAll = useCallback(async () => {
    setRunning(true)
    setError(null)
    try {
      const rs = await Promise.all(langTests.map(formatAndCompare))
      setResults((prev) => {
        const next = { ...prev }
        for (const r of rs) next[r.id] = r
        return next
      })
    } finally {
      setRunning(false)
    }
  }, [langTests, formatAndCompare])

  // run a single test against the selected version + effective config
  const runOne = useCallback(
    async (test: TestCase) => {
      setRunningId(test.id)
      setError(null)
      const r = await formatAndCompare(test)
      setResults((prev) => ({ ...prev, [test.id]: r }))
      setExpanded((prev) => new Set(prev).add(test.id))
      setRunningId(null)
    },
    [formatAndCompare],
  )

  const toggleMute = useCallback((test: TestCase) => {
    patchTest(test.id, { muted: !test.muted })
  }, [])

  const removeTest = useCallback((id: string) => {
    draftRemoveTest(id)
    setResults((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
  }, [])

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  // copy a shareable deep link to one test and focus it
  const shareTest = useCallback((id: string) => {
    navigator.clipboard?.writeText(testShareUrl(id)).catch(() => {})
    setFocusedId(id)
    setQueryParam('test', id)
    setExpanded((prev) => new Set(prev).add(id))
    setCopiedId(id)
    window.setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 1500)
  }, [])

  const openCreate = useCallback(() => {
    setEditingId(null)
    setForm(emptyForm(filter === 'all' ? playgroundLanguage : filter))
    setError(null)
    setDialogOpen(true)
  }, [filter, playgroundLanguage])

  const openEdit = useCallback((test: TestCase) => {
    setEditingId(test.id)
    setForm({
      name: test.name,
      language: test.language,
      input: test.input,
      expected: test.expected,
      muted: test.muted,
      note: test.note ?? '',
    })
    setError(null)
    setDialogOpen(true)
  }, [])

  const save = useCallback(() => {
    setError(null)
    if (!form.name.trim()) {
      setError('Name is required')
      return
    }
    if (editingId !== null) {
      patchTest(editingId, form)
      // a changed test may now format differently; drop its stale result
      setResults((prev) => {
        const next = { ...prev }
        delete next[editingId]
        return next
      })
    } else {
      addDraftTest({ id: newDraftId(), ...form })
    }
    setDialogOpen(false)
  }, [editingId, form])

  const deleteFromDialog = useCallback(() => {
    if (editingId === null) return
    removeTest(editingId)
    setDialogOpen(false)
  }, [editingId, removeTest])

  return (
    <div className="tests-view">
      {/* language + clang-format pickers live in the header (same spot as the
          playground), portaled into the slot App renders for the tests view */}
      {headerSlot &&
        createPortal(
          <>
            <Select
              value={[filter]}
              onUpdate={(v) => setFilter(v[0] as 'all' | Language)}
              size="s"
              width={120}
            >
              <Select.Option value="all">All</Select.Option>
              <Select.Option value="cpp">C++</Select.Option>
              <Select.Option value="python">Python</Select.Option>
            </Select>
            {versions.length > 0 && (
              <Select
                value={runVersion ? [runVersion] : []}
                onUpdate={(v) => setRunVersion(v[0])}
                size="s"
                width={190}
                label="clang-format"
                title="clang-format version for the run"
              >
                {versions.map((v) => (
                  <Select.Option key={v} value={v}>
                    {v}
                  </Select.Option>
                ))}
              </Select>
            )}
          </>,
          headerSlot,
        )}

      <div className="tests-toolbar">
        <Button view="action" size="m" onClick={runAll} disabled={running}>
          {running ? (
            <span className="btn-spin">
              <Spin size="xs" />
              Running
            </span>
          ) : (
            <>
              <Icon data={PlayFill} size={16} />
              Run all
            </>
          )}
        </Button>

        <div className="tests-summary">
          {(['pass', 'fail', 'muted'] as const).map((s) => (
            <Label
              key={s}
              theme={STATUS_THEME[s] as 'success' | 'danger' | 'warning'}
              interactive
              className={`status-chip${statusFilter === s ? ' active' : ''}`}
              onClick={() =>
                setStatusFilter((cur) => (cur === s ? 'all' : s))
              }
            >
              {summary[s]} {s}
            </Label>
          ))}
          <Text color="secondary">/ {summary.total}</Text>
        </div>

        <Button
          view="outlined"
          size="m"
          className="tests-matrix-btn"
          onClick={onOpenMatrix}
          title="Run all tests on every installed clang-format version"
        >
          <Icon data={LayoutCells} size={16} />
          Matrix
        </Button>

        <Button view="normal" size="m" className="tests-add-btn" onClick={openCreate}>
          <Icon data={Plus} size={16} />
          Add test
        </Button>
      </div>

      {error && (
        <Text color="danger" className="tests-error">
          {error}
        </Text>
      )}

      <div className="tests-list">
        {visibleTests.length === 0 && (
          <Text color="secondary" className="tests-empty">
            No tests yet. Add a BEFORE → AFTER case to get started.
          </Text>
        )}
        {visibleTests.map((test) => {
          const result = results[test.id]
          const status = displayStatus(test, result)
          const isOpen = expanded.has(test.id)
          return (
            <div
              key={test.id}
              id={`test-${test.id}`}
              className={`test-row status-${status}${
                test.id === focusedId ? ' focused' : ''
              }`}
            >
              <div className="test-row-head" onClick={() => toggleExpand(test.id)}>
                <span className={`status-dot status-${status}`} />
                <span className="test-name">{test.name}</span>
                <span
                  className="test-id"
                  title="Copy a shareable link to this test"
                  onClick={(e) => {
                    e.stopPropagation()
                    shareTest(test.id)
                  }}
                >
                  {copiedId === test.id ? 'link copied ✓' : `#${test.id}`}
                </span>
                <Label theme="unknown" size="xs">
                  {test.language === 'cpp' ? 'C++' : 'Python'}
                </Label>
                <Label theme={STATUS_THEME[status]} size="xs">
                  {STATUS_LABEL[status]}
                </Label>
                <span className="test-row-spacer" />
                <span onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={test.muted}
                    onUpdate={() => toggleMute(test)}
                    size="m"
                  >
                    mute
                  </Checkbox>
                </span>
                <Button
                  view="flat"
                  size="s"
                  title="Run this test"
                  disabled={runningId === test.id}
                  onClick={(e) => {
                    e.stopPropagation()
                    runOne(test)
                  }}
                >
                  {runningId === test.id ? (
                    <Spin size="xs" />
                  ) : (
                    <Icon data={PlayFill} size={16} />
                  )}
                </Button>
                <Button
                  view="flat"
                  size="s"
                  title="Edit test"
                  onClick={(e) => {
                    e.stopPropagation()
                    openEdit(test)
                  }}
                >
                  <Icon data={Pencil} size={16} />
                </Button>
              </div>

              {isOpen && (
                <div className="test-row-body">
                  {result?.error && (
                    <Text color="danger" className="test-run-error">
                      {result.error}
                    </Text>
                  )}
                  <div className="test-panes">
                    <TestPane title="Before (input)" code={test.input} language={test.language} />
                    <TestPane
                      title="Desired (expected)"
                      code={test.expected}
                      language={test.language}
                    />
                    <TestPane
                      title="Actual (current config)"
                      code={result ? result.actual : '— run to see —'}
                      language={test.language}
                      diffAgainst={result ? test.expected : undefined}
                    />
                  </div>
                  {test.note && (
                    <Text color="secondary" className="test-note">
                      {test.note}
                    </Text>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} size="l">
        <Dialog.Header caption={editingId ? 'Edit test' : 'Add test'} />
        <Dialog.Body>
          <div className="add-form-top">
            <TextInput
              value={form.name}
              onUpdate={(name) => setForm((f) => ({ ...f, name }))}
              placeholder="Test name"
              size="m"
            />
            <Select
              value={[form.language]}
              onUpdate={(v) => setForm((f) => ({ ...f, language: v[0] as Language }))}
              size="m"
              width={120}
            >
              <Select.Option value="cpp">C++</Select.Option>
              <Select.Option value="python">Python</Select.Option>
            </Select>
            <Checkbox
              checked={form.muted}
              onUpdate={(muted) => setForm((f) => ({ ...f, muted }))}
              size="m"
            >
              muted
            </Checkbox>
            <Button
              view="outlined"
              size="m"
              onClick={() =>
                setForm((f) => ({
                  ...f,
                  language: playgroundLanguage,
                  input: playgroundInput,
                  expected: playgroundOutput || f.expected,
                }))
              }
            >
              Grab from playground
            </Button>
            {editingId && (
              <Button
                view="flat-danger"
                size="m"
                title="Delete test"
                onClick={deleteFromDialog}
              >
                <Icon data={TrashBin} size={16} />
              </Button>
            )}
          </div>

          <div className="add-form-panes">
            <div className="add-form-pane">
              <Text color="secondary" variant="caption-2">
                Before (input)
              </Text>
              <div className="add-form-editor">
                <CodeMirrorEditor
                  value={form.input}
                  language={form.language}
                  onChange={(input) => setForm((f) => ({ ...f, input }))}
                />
              </div>
            </div>
            <div className="add-form-pane">
              <Text color="secondary" variant="caption-2">
                Desired (expected)
              </Text>
              <div className="add-form-editor">
                <CodeMirrorEditor
                  value={form.expected}
                  language={form.language}
                  onChange={(expected) => setForm((f) => ({ ...f, expected }))}
                />
              </div>
            </div>
          </div>

          <TextInput
            value={form.note ?? ''}
            onUpdate={(note) => setForm((f) => ({ ...f, note }))}
            placeholder="Note (optional) — e.g. why muted, ticket link"
            size="m"
          />
        </Dialog.Body>
        <Dialog.Footer
          onClickButtonCancel={() => setDialogOpen(false)}
          textButtonCancel="Cancel"
          onClickButtonApply={save}
          textButtonApply={editingId ? 'Save changes' : 'Add test'}
          propsButtonApply={{ disabled: !form.name.trim() }}
        />
      </Dialog>
    </div>
  )
}

// hold this key while hovering a pane to peek at it enlarged; release to close.
// Ctrl is a free modifier on macOS (Mod = Cmd there) and doesn't hijack
// CodeMirror's drag-select the way Alt (rectangular selection) would, so you can
// still select/copy text inside the enlarged view while holding it.
const PEEK_KEY = 'Control'
const PEEK_HINT = 'Ctrl'

function TestPane({
  title,
  code,
  language,
  diffAgainst,
}: {
  title: string
  code: string
  language: Language
  diffAgainst?: string
}) {
  const [zoom, setZoom] = useState(false)
  const [shown, setShown] = useState(false)
  const hoverRef = useRef(false)
  // true when the enlarged view was opened by holding the key (so releasing it
  // closes it); a click-opened view stays until backdrop/Escape
  const heldRef = useRef(false)
  const diffRanges = useMemo(
    () => (diffAgainst !== undefined ? computeDiff(diffAgainst, code) : undefined),
    [diffAgainst, code],
  )

  const openZoom = useCallback((held = false) => {
    heldRef.current = held
    setZoom(true)
    requestAnimationFrame(() => setShown(true))
  }, [])
  const closeZoom = useCallback(() => {
    heldRef.current = false
    setShown(false)
    window.setTimeout(() => setZoom(false), 160)
  }, [])

  // hold PEEK_KEY while hovering this pane → open; release → close
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== PEEK_KEY || e.repeat) return
      if (zoom || !hoverRef.current) return
      openZoom(true)
    }
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === PEEK_KEY && heldRef.current) closeZoom()
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [zoom, openZoom, closeZoom])

  // close the enlarged view on Escape, or if the window loses focus (so a
  // held-open peek can't get stuck when the keyup is swallowed)
  useEffect(() => {
    if (!zoom) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeZoom()
    }
    const onBlur = () => closeZoom()
    window.addEventListener('keydown', onKey)
    window.addEventListener('blur', onBlur)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('blur', onBlur)
    }
  }, [zoom, closeZoom])
  return (
    <div
      className="test-pane"
      onMouseEnter={() => {
        hoverRef.current = true
      }}
      onMouseLeave={() => {
        hoverRef.current = false
      }}
    >
      <div className="test-pane-titlebar">
        <Text color="secondary" variant="caption-2" className="test-pane-title">
          {title}
        </Text>
        <button
          type="button"
          className="test-pane-zoom"
          title={`Enlarge — or hover and hold ${PEEK_HINT}`}
          aria-label="Enlarge this code"
          onClick={() => openZoom()}
        >
          <Icon data={Magnifier} size={14} />
        </button>
      </div>
      <div className="test-pane-editor">
        <CodeMirrorEditor
          value={code}
          language={language}
          readOnly
          diffRanges={diffRanges}
          showDiff={diffRanges !== undefined}
        />
      </div>

      {zoom && (
        <div className={`zoom-overlay${shown ? ' shown' : ''}`} onClick={closeZoom}>
          <div className="zoom-code" onClick={(e) => e.stopPropagation()}>
            <CodeMirrorEditor
              value={code}
              language={language}
              readOnly
              diffRanges={diffRanges}
              showDiff={diffRanges !== undefined}
            />
          </div>
        </div>
      )}
    </div>
  )
}
