import { useCallback, useEffect, useState } from 'react'
import { Button, Icon, Spin, Text } from '@gravity-ui/uikit'
import { ArrowRotateLeft, Check, Minus, StarFill, Xmark } from '@gravity-ui/icons'
import { draftCreatedShadows } from './draftStore'
import { ShadowLabel } from './ShadowLabel'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import { formatterById } from './formatters'
import { computeDiff } from './useDiff'

interface Cell {
  status: 'pass' | 'fail' | 'muted'
  passed: boolean
}

interface Row {
  id: string
  name: string
  muted: boolean
  cells: Record<string, Cell | null>
  muted_passes_somewhere: boolean
}

interface ShadowMeta {
  id: string
  base: string
  name: string
}

interface Matrix {
  versions: string[]
  tests: Row[]
  shadows?: ShadowMeta[]
}

interface Props {
  open: boolean
  /** language whose tests fill the rows */
  language: string
  /** formatter whose installed versions are the columns */
  formatter: string
  onClose: () => void
  /** jump to a test in the Tests view */
  onPickTest?: (id: string) => void
}

function cellContent(cell: Cell | null, muted: boolean) {
  if (!cell) return <span className="matrix-na">·</span>
  if (muted) {
    return cell.passed ? (
      <span className="matrix-ic surprise" title="muted — but passes on this version">
        <Icon data={Check} size={13} />
      </span>
    ) : (
      <span className="matrix-ic muted" title="muted">
        <Icon data={Minus} size={13} />
      </span>
    )
  }
  return cell.passed ? (
    <span className="matrix-ic pass" title="pass">
      <Icon data={Check} size={13} />
    </span>
  ) : (
    <span className="matrix-ic fail" title="fail">
      <Icon data={Xmark} size={13} />
    </span>
  )
}

interface CellView {
  name: string
  col: string
  desired: string
  actual: string
  error: string | null
}

export default function MatrixDrawer({ open, language, formatter, onClose, onPickTest }: Props) {
  const [data, setData] = useState<Matrix | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // test inputs/expected, fetched so a cell click can recompute & diff the output
  const [testMap, setTestMap] = useState<Record<string, { input: string; expected: string }>>({})
  const [cell, setCell] = useState<CellView | null>(null)
  const [cellLoading, setCellLoading] = useState(false)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // send locally-created (unpublished) shadows so they get matrix columns too;
      // tag them with the current formatter (the matrix is built for it)
      const shadows = draftCreatedShadows().map((s) => ({
        id: s.id,
        base: s.base,
        name: s.name,
        content: s.content,
        formatter,
      }))
      const res = await fetch('/api/tests/matrix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language, formatter, shadows }),
      })
      const d = await res.json()
      if (!res.ok) {
        setError(d.error ?? 'Failed to build the matrix')
        return
      }
      setData(d)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [language, formatter])

  // (re)build the matrix when opened, or when the language/formatter changes
  useEffect(() => {
    if (open) run()
    else setData(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, language, formatter])

  // test inputs/expected for the cell-diff popup
  useEffect(() => {
    if (!open) return
    fetch('/api/tests')
      .then((r) => r.json())
      .then((rows: { id: string; input: string; expected: string }[]) => {
        const m: Record<string, { input: string; expected: string }> = {}
        for (const t of rows) m[t.id] = { input: t.input, expected: t.expected }
        setTestMap(m)
      })
      .catch(() => {})
  }, [open])

  // click a cell → recompute that test on that column's config and show the diff
  const openCell = useCallback(
    async (row: Row, col: string) => {
      const t = testMap[row.id]
      if (!t) return
      setCell({ name: row.name, col, desired: t.expected, actual: '', error: null })
      setCellLoading(true)
      try {
        const sh = draftCreatedShadows().find((s) => s.id === col)
        // match the matrix run exactly: a draft shadow runs its base binary with
        // its draft config; a real version / published shadow is resolved by id
        const body = sh
          ? { code: t.input, language, formatter, version: sh.base, config: sh.content }
          : { code: t.input, language, formatter, version: col }
        const res = await fetch('/api/format', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        const d = await res.json()
        if (!res.ok) setCell((c) => (c ? { ...c, error: d.error ?? 'format failed' } : c))
        else setCell((c) => (c ? { ...c, actual: d.formatted } : c))
      } catch (e) {
        setCell((c) => (c ? { ...c, error: String(e) } : c))
      } finally {
        setCellLoading(false)
      }
    },
    [testMap, language, formatter],
  )

  // Escape closes the cell-diff popup
  useEffect(() => {
    if (!cell) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCell(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cell])

  const surprises = data ? data.tests.filter((t) => t.muted_passes_somewhere) : []
  // a column id → its display label + tooltip (shadow configs show a ghost icon)
  const shadowById = new Map((data?.shadows ?? []).map((s) => [s.id, s]))
  const colLabel = (v: string) => {
    const sh = shadowById.get(v)
    return sh ? <ShadowLabel>{`${sh.name} (${sh.base})`}</ShadowLabel> : v
  }
  const fmtLabel = formatterById(formatter)?.label ?? formatter
  const colTitle = (v: string) => {
    const sh = shadowById.get(v)
    return sh ? `shadow config "${sh.name}" · ${fmtLabel} ${sh.base}` : v
  }

  return (
    <>
      {open && <div className="drawer-overlay" onClick={onClose} />}
      <div className={`matrix-drawer${open ? ' open' : ''}`}>
        <div className="matrix-drawer-header">
          <span className="matrix-drawer-title">Version matrix</span>
          <span className="config-drawer-spacer" />
          <Button view="flat" size="s" onClick={run} disabled={loading} title="Re-run on all versions">
            <Icon data={ArrowRotateLeft} size={16} />
          </Button>
          <Button view="flat" size="s" onClick={onClose} title="Close">
            ✕
          </Button>
        </div>

        {error && (
          <Text color="danger" className="matrix-error">
            {error}
          </Text>
        )}

        <div className="matrix-body">
          {loading ? (
            <div className="matrix-loading">
              <Spin size="m" />
              <Text color="secondary" variant="caption-2">
                Running every test on every installed {fmtLabel} version…
              </Text>
            </div>
          ) : data ? (
            data.versions.length === 0 ? (
              <Text color="secondary">No {fmtLabel} versions installed.</Text>
            ) : (
              <>
                {surprises.length > 0 && (
                  <div className="matrix-surprise-banner">
                    <Icon data={StarFill} size={14} />
                    <Text variant="caption-2">
                      {surprises.length} muted test{surprises.length > 1 ? 's' : ''}{' '}
                      pass{surprises.length === 1 ? 'es' : ''} on some version —{' '}
                      candidate{surprises.length > 1 ? 's' : ''} to un-mute
                    </Text>
                  </div>
                )}
                <div className="matrix-scroll">
                  <table className="matrix-table">
                    <thead>
                      <tr>
                        <th className="matrix-th-name">Test</th>
                        {data.versions.map((v) => (
                          <th key={v} className="matrix-th-ver" title={colTitle(v)}>
                            <span>{colLabel(v)}</span>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.tests.map((t) => (
                        <tr
                          key={t.id}
                          className={t.muted_passes_somewhere ? 'matrix-row surprise' : 'matrix-row'}
                        >
                          <td className="matrix-td-name" title={t.name}>
                            {t.muted_passes_somewhere && (
                              <Icon data={StarFill} size={11} className="matrix-row-star" />
                            )}
                            <button
                              type="button"
                              className="matrix-name-text matrix-name-link"
                              onClick={() => onPickTest?.(t.id)}
                              title="Go to this test"
                            >
                              {t.name}
                            </button>
                          </td>
                          {data.versions.map((v) => (
                            <td
                              key={v}
                              className={`matrix-cell${t.cells[v] ? ' clickable' : ''}`}
                              onClick={() => t.cells[v] && openCell(t, v)}
                              title={t.cells[v] ? 'Show Desired vs Actual' : undefined}
                            >
                              {cellContent(t.cells[v], t.muted)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="matrix-legend">
                  <span>
                    <Icon data={Check} size={12} className="ic-pass" /> pass
                  </span>
                  <span>
                    <Icon data={Xmark} size={12} className="ic-fail" /> fail
                  </span>
                  <span>
                    <Icon data={Minus} size={12} className="ic-muted" /> muted
                  </span>
                  <span>
                    <Icon data={Check} size={12} className="ic-surprise" /> muted but passes
                  </span>
                </div>
              </>
            )
          ) : null}
        </div>
      </div>

      {cell && (
        <div className="zoom-overlay shown cell-overlay" onClick={() => setCell(null)}>
          <div className="cell-diff" onClick={(e) => e.stopPropagation()}>
            <div className="cell-diff-title">
              <span className="cell-diff-name">{cell.name}</span>
              <span className="cell-diff-col">{colLabel(cell.col)}</span>
            </div>
            {cell.error ? (
              <Text color="danger">{cell.error}</Text>
            ) : cellLoading ? (
              <div className="matrix-loading">
                <Spin size="m" />
              </div>
            ) : (
              <div className="cell-diff-panes">
                <div className="cell-diff-pane">
                  <Text color="secondary" variant="caption-2">
                    Desired
                  </Text>
                  <div className="cell-diff-editor">
                    <CodeMirrorEditor value={cell.desired} language={language as Language} readOnly />
                  </div>
                </div>
                <div className="cell-diff-pane">
                  <Text color="secondary" variant="caption-2">
                    Actual
                  </Text>
                  <div className="cell-diff-editor">
                    <CodeMirrorEditor
                      value={cell.actual}
                      language={language as Language}
                      readOnly
                      diffRanges={computeDiff(cell.desired, cell.actual)}
                      showDiff
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
