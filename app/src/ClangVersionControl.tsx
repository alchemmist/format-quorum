import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Dialog,
  Label,
  Select,
  Spin,
  Text,
  TextInput,
} from '@gravity-ui/uikit'

export interface VersionsState {
  versions: string[]
  default: string | null
  installing: string[]
  suggestions: string[]
}

interface Props {
  /** Currently selected clang-format version (undefined = backend default) */
  value: string | undefined
  onChange: (version: string) => void
}

const VERSION_RE = /^\d+\.\d+\.\d+$/

export default function ClangVersionControl({ value, onChange }: Props) {
  const [state, setState] = useState<VersionsState | null>(null)
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/clang-versions')
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
        const res = await fetch('/api/clang-versions', {
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
        const res = await fetch(`/api/clang-versions/${version}`, { method: 'DELETE' })
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
  const selected = value ?? state?.default ?? undefined

  return (
    <div className="clang-version-control">
      <Select
        value={selected ? [selected] : []}
        onUpdate={(v) => onChange(v[0])}
        size="s"
        width={250}
        label="clang-format"
        disabled={versions.length === 0}
        placeholder="version"
      >
        {versions.map((v) => (
          <Select.Option key={v} value={v}>
            {v === state?.default ? `${v} (default)` : v}
          </Select.Option>
        ))}
      </Select>

      <Button
        view="outlined"
        size="s"
        onClick={() => {
          setError(null)
          setOpen(true)
        }}
        title="Manage clang-format versions"
      >
        Versions
      </Button>

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
                <Text>{v === state?.default ? `${v} (default)` : v}</Text>
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
        </Dialog.Body>
        <Dialog.Footer
          onClickButtonCancel={() => setOpen(false)}
          textButtonCancel="Close"
        />
      </Dialog>
    </div>
  )
}
