import { useCallback, useEffect, useState } from 'react'
import {
  ActionTooltip,
  Button,
  Dialog,
  Icon,
  Label,
  Select,
  Spin,
  Text,
  TextInput,
} from '@gravity-ui/uikit'
import { Layers } from '@gravity-ui/icons'
import { useShadows, deleteShadow, type ShadowMeta } from './draftStore'
import { ShadowLabel } from './ShadowLabel'

export interface VersionsState {
  versions: string[]
  default: string | null
  installing: string[]
  suggestions: string[]
  shadows?: ShadowMeta[]
}

interface Props {
  /** Currently selected version (undefined = backend default) */
  value: string | undefined
  onChange: (version: string) => void
  /** which versioned formatter this controls (default: clang-format) */
  formatterId?: string
}

const VERSION_RE = /^\d+\.\d+\.\d+$/

export default function ClangVersionControl({
  value,
  onChange,
  formatterId = 'clang-format',
}: Props) {
  const versionsApi = `/api/formatters/${formatterId}/versions`
  const [state, setState] = useState<VersionsState | null>(null)
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch(versionsApi)
      const data: VersionsState = await res.json()
      setState(data)
      // Adopt the backend default once, so the Select shows something sensible.
      if (value === undefined && data.default) onChange(data.default)
    } catch {
      /* ignore — header just won't show versions */
    }
  }, [value, onChange])

  useEffect(() => {
    load()
    // load once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const addVersion = useCallback(
    async (version: string) => {
      setError(null)
      if (!VERSION_RE.test(version.trim())) {
        setError('Version must be exactly three numbers, e.g. 22.1.5')
        return
      }
      setAdding(true)
      try {
        const res = await fetch(versionsApi, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version: version.trim() }),
        })
        const data = await res.json()
        if (!res.ok) {
          setError(data.error ?? 'Failed to add version')
          return
        }
        setState(data as VersionsState)
        setInput('')
        onChange(version.trim())
      } catch (e) {
        setError(String(e))
      } finally {
        setAdding(false)
      }
    },
    [onChange],
  )

  const removeVersion = useCallback(
    async (version: string) => {
      setError(null)
      try {
        const res = await fetch(`${versionsApi}/${version}`, { method: 'DELETE' })
        const data = await res.json()
        if (!res.ok) {
          setError(data.error ?? 'Failed to remove version')
          return
        }
        setState(data as VersionsState)
        if (value === version && data.default) onChange(data.default)
      } catch (e) {
        setError(String(e))
      }
    },
    [value, onChange],
  )

  const versions = state?.versions ?? []
  const shadows = useShadows(state?.shadows ?? [])
  const selected = value ?? state?.default ?? undefined

  // a real version renders as its number; a shadow as the ghost icon + name
  const renderVersion = (v: string) => {
    const sh = shadows.find((s) => s.id === v)
    return sh ? <ShadowLabel>{`${sh.name} (${sh.base})`}</ShadowLabel> : v
  }

  return (
    <div className="clang-version-control">
      <Select
        value={selected ? [selected] : []}
        onUpdate={(v) => onChange(v[0])}
        size="s"
        width={160}
        disabled={versions.length === 0}
        placeholder="version"
        title="clang-format version to format with"
        renderSelectedOption={(opt) => <span>{renderVersion(String(opt.value))}</span>}
      >
        {[...versions, ...shadows.map((s) => s.id)].map((v) => (
          <Select.Option key={v} value={v}>
            {renderVersion(v)}
          </Select.Option>
        ))}
      </Select>

      <ActionTooltip
        title="clang-format versions"
        description="Install another X.Y.Z to format and compare across versions in the matrix, and manage shadow configs (quasi-versions). The selected version is what the playground / tests format with."
      >
        <Button
          view="outlined"
          size="s"
          onClick={() => {
            setError(null)
            setOpen(true)
          }}
          aria-label="Manage clang-format versions"
        >
          <Icon data={Layers} size={16} />
        </Button>
      </ActionTooltip>

      <Dialog open={open} onClose={() => setOpen(false)} size="s">
        <Dialog.Header caption="clang-format versions" />
        <Dialog.Body>
          <div className="version-add-row">
            <TextInput
              value={input}
              onUpdate={setInput}
              placeholder="e.g. 22.1.5"
              size="m"
              disabled={adding}
              onKeyDown={(e) => {
                if (e.key === 'Enter') addVersion(input)
              }}
            />
            <Button
              view="action"
              size="m"
              onClick={() => addVersion(input)}
              disabled={adding}
            >
              {adding ? (
                <span className="btn-spin">
                  <Spin size="xs" />
                  Trying
                </span>
              ) : (
                'Try add'
              )}
            </Button>
          </div>

          {error && (
            <Text color="danger" className="version-error">
              {error}
            </Text>
          )}

          {(state?.suggestions?.length ?? 0) > 0 && (
            <div className="version-suggestions">
              <Text color="secondary" variant="caption-2">
                Quick add:
              </Text>
              <div className="version-chips">
                {state!.suggestions.map((v) => (
                  <Label
                    key={v}
                    type="default"
                    interactive
                    onClick={() => !adding && addVersion(v)}
                  >
                    {v}
                  </Label>
                ))}
              </div>
            </div>
          )}

          <div className="version-list">
            <Text color="secondary" variant="caption-2">
              Installed:
            </Text>
            {versions.map((v) => (
              <div key={v} className="version-list-item">
                <Text>{v}</Text>
                {v !== state?.default && (
                  <Button
                    view="flat-danger"
                    size="xs"
                    onClick={() => removeVersion(v)}
                  >
                    Remove
                  </Button>
                )}
              </div>
            ))}
          </div>

          {shadows.length > 0 && (
            <div className="version-list">
              <Text color="secondary" variant="caption-2">
                Shadow configs (remove publishes with your draft):
              </Text>
              {shadows.map((s) => (
                <div key={s.id} className="version-list-item">
                  <Text>
                    <ShadowLabel>{s.name}</ShadowLabel>{' '}
                    <Text color="secondary" variant="caption-2">
                      ({s.base})
                    </Text>
                  </Text>
                  <Button
                    view="flat-danger"
                    size="xs"
                    onClick={() => {
                      deleteShadow(s.id)
                      if (value === s.id && state?.default) onChange(state.default)
                    }}
                  >
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          )}
        </Dialog.Body>
        <Dialog.Footer
          onClickButtonCancel={() => setOpen(false)}
          textButtonCancel="Close"
        />
      </Dialog>
    </div>
  )
}
