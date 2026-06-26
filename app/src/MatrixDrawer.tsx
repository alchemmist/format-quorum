import { useCallback, useEffect, useState } from 'react'
import { Button, Icon, Spin, Text } from '@gravity-ui/uikit'
import { ArrowRotateLeft, Check, Minus, StarFill, Xmark } from '@gravity-ui/icons'

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

interface Matrix {
  versions: string[]
  tests: Row[]
}

interface Props {
  open: boolean
  onClose: () => void
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

export default function MatrixDrawer({ open, onClose }: Props) {
  const [data, setData] = useState<Matrix | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/tests/matrix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: 'cpp' }),
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
  }, [])

  // build the matrix the first time the drawer is opened
  useEffect(() => {
    if (open && !data && !loading) run()
  }, [open, data, loading, run])

  const surprises = data ? data.tests.filter((t) => t.muted_passes_somewhere) : []

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
                Running every test on every installed clang-format version…
              </Text>
            </div>
          ) : data ? (
            data.versions.length === 0 ? (
              <Text color="secondary">No clang-format versions installed.</Text>
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
                        <th className="matrix-th-name" />
                        {data.versions.map((v) => (
                          <th key={v} className="matrix-th-ver" title={v}>
                            <span>{v}</span>
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
                            <span className="matrix-name-text">{t.name}</span>
                          </td>
                          {data.versions.map((v) => (
                            <td key={v} className="matrix-cell">
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
    </>
  )
}
