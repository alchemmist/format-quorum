import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import { Pencil, TrashBin } from '@gravity-ui/icons'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import { getQueryParam, setQueryParam, testShareUrl } from './url'
import { computeDiff } from './useDiff'

export interface TestCase {
  id: string
  name: string
  language: Language
  input: string
  expected: string
  muted: boolean
  note?: string
}

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
}: Props) {
  const initialFilter = getQueryParam('filter')
  const [tests, setTests] = useState<TestCase[]>([])
  const [results, setResults] = useState<Record<string, RunResult>>({})
  const [running, setRunning] = useState(false)
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

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState(emptyForm(playgroundLanguage))
  const [saving, setSaving] = useState(false)

  const loadTests = useCallback(async () => {
    const res = await fetch('/api/tests')
    setTests(await res.json())
  }, [])

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

  const runAll = useCallback(async () => {
    setRunning(true)
    setError(null)
    try {
      const res = await fetch('/api/tests/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          language: filter === 'all' ? undefined : filter,
          clang_version: runVersion,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? 'Run failed')
        return
      }
      const byId: Record<string, RunResult> = {}
      for (const r of data.results) byId[r.id] = r
      setResults((prev) => ({ ...prev, ...byId }))
    } catch (e) {
      setError(String(e))
    } finally {
      setRunning(false)
    }
  }, [filter, runVersion])

  const toggleMute = useCallback(async (test: TestCase) => {
    const res = await fetch(`/api/tests/${test.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ muted: !test.muted }),
    })
    const updated = await res.json()
    setTests((prev) => prev.map((t) => (t.id === test.id ? updated : t)))
  }, [])

  const removeTest = useCallback(async (id: string) => {
    await fetch(`/api/tests/${id}`, { method: 'DELETE' })
    setTests((prev) => prev.filter((t) => t.id !== id))
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

  const save = useCallback(async () => {
    setSaving(true)
    setError(null)
    try {
      const editing = editingId !== null
      const res = await fetch(
        editing ? `/api/tests/${editingId}` : '/api/tests',
        {
          method: editing ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
        },
      )
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? 'Failed to save test')
        return
      }
      setTests((prev) =>
        editing ? prev.map((t) => (t.id === editingId ? data : t)) : [...prev, data],
      )
      // a saved test may now format differently; drop its stale result
      if (editing) {
        setResults((prev) => {
          const next = { ...prev }
          delete next[editingId!]
          return next
        })
      }
      setDialogOpen(false)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }, [editingId, form])

  const deleteFromDialog = useCallback(async () => {
    if (editingId === null) return
    await removeTest(editingId)
    setDialogOpen(false)
  }, [editingId, removeTest])

  return (
    <div className="tests-view">
      <div className="tests-toolbar">
        <Button view="action" size="m" onClick={runAll} disabled={running}>
          {running ? (
            <span className="btn-spin">
              <Spin size="xs" />
              Running
            </span>
          ) : (
            'Run all'
          )}
        </Button>

        <Select
          value={[filter]}
          onUpdate={(v) => setFilter(v[0] as 'all' | Language)}
          size="m"
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
            size="m"
            width={200}
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

        <Button view="normal" size="m" className="tests-add-btn" onClick={openCreate}>
          + Add test
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
          textButtonApply={saving ? 'Saving…' : editingId ? 'Save changes' : 'Save test'}
          propsButtonApply={{ disabled: saving || !form.name.trim() }}
        />
      </Dialog>
    </div>
  )
}

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
  const diffRanges = useMemo(
    () => (diffAgainst !== undefined ? computeDiff(diffAgainst, code) : undefined),
    [diffAgainst, code],
  )
  return (
    <div className="test-pane">
      <Text color="secondary" variant="caption-2" className="test-pane-title">
        {title}
      </Text>
      <div className="test-pane-editor">
        <CodeMirrorEditor
          value={code}
          language={language}
          readOnly
          diffRanges={diffRanges}
          showDiff={diffRanges !== undefined}
        />
      </div>
    </div>
  )
}
