import { useCallback, useRef, useState } from 'react'
import {
  ActionTooltip,
  Button,
  Dialog,
  Icon,
  Text,
  TextArea,
  TextInput,
} from '@gravity-ui/uikit'
import { Plus } from '@gravity-ui/icons'
import {
  loadFormatters,
  uploadsEnabled,
  formattersForLanguage,
  type FormatterInfo,
} from './formatters'

// mirrors the backend MAX_UPLOAD_BYTES — reject oversized files before reading.
const MAX_UPLOAD_BYTES = 200 * 1024 * 1024

/** Read a File as raw base64 (strips the data: URL prefix). */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '')
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

interface Props {
  /** the language the new formatter is for (its code language) */
  language: string
  /** select this formatter after it's created */
  onCreated: (formatterId: string) => void
}

/**
 * Create a **custom formatter** for a language by uploading your own binary. It
 * becomes its own formatter for that language (alongside clang-format etc.), with
 * its own version axis and config. Only shown when the backend allows uploads.
 */
export default function AddCustomFormatter({ language, onCreated }: Props) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [version, setVersion] = useState('')
  const [config, setConfig] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const mine: FormatterInfo[] = formattersForLanguage(language).filter((f) => f.custom)

  const reset = () => {
    setName(''); setVersion(''); setConfig(''); setError(null)
  }

  const submit = useCallback(
    async (file: File) => {
      setError(null)
      if (!name.trim()) { setError('Give the formatter a name'); return }
      if (file.size > MAX_UPLOAD_BYTES) {
        setError(`File is too large (max ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB)`)
        return
      }
      setBusy(true)
      try {
        const content_b64 = await fileToBase64(file)
        const res = await fetch('/api/custom-formatters', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            language,
            name: name.trim(),
            version: version.trim() || undefined,
            config: config.trim() ? config : undefined,
            content_b64,
            filename: file.name,
          }),
        })
        const data = await res.json()
        if (!res.ok) { setError(data.error ?? 'Upload failed'); return }
        await loadFormatters() // pull in the new formatter so the picker shows it
        if (data.formatter?.id) onCreated(data.formatter.id)
        reset()
        setOpen(false)
      } catch (e) {
        setError(String(e))
      } finally {
        setBusy(false)
      }
    },
    [language, name, version, config, onCreated],
  )

  const removeFormatter = useCallback(async (id: string) => {
    setError(null)
    try {
      const res = await fetch(`/api/custom-formatters/${id}`, { method: 'DELETE' })
      if (!res.ok) { setError('Failed to remove'); return }
      await loadFormatters()
    } catch (e) {
      setError(String(e))
    }
  }, [])

  if (!uploadsEnabled()) return null

  return (
    <>
      <ActionTooltip
        title="Add a custom formatter"
        description="Upload your own formatter binary for this language — it becomes its own formatter with its own versions and config."
      >
        <Button
          view="outlined"
          size="s"
          onClick={() => { reset(); setOpen(true) }}
          aria-label="Add a custom formatter"
        >
          <Icon data={Plus} size={16} />
        </Button>
      </ActionTooltip>

      <Dialog open={open} onClose={() => setOpen(false)} size="s">
        <Dialog.Header caption={`Custom formatter for ${language}`} />
        <Dialog.Body>
          <div className="cf-field">
            <Text variant="caption-2" color="secondary">Name</Text>
            <TextInput value={name} onUpdate={setName} placeholder="e.g. my-clang" size="m" disabled={busy} />
          </div>
          <div className="cf-field">
            <Text variant="caption-2" color="secondary">Version (optional)</Text>
            <TextInput value={version} onUpdate={setVersion} placeholder="e.g. 1.0 or patched-2" size="m" disabled={busy} />
          </div>
          <div className="cf-field">
            <Text variant="caption-2" color="secondary">Config (optional)</Text>
            <TextArea value={config} onUpdate={setConfig} placeholder="config text for this formatter" minRows={3} disabled={busy} />
          </div>

          <input
            ref={fileRef}
            type="file"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) submit(f)
              e.target.value = ''
            }}
          />
          <Button view="action" size="m" onClick={() => fileRef.current?.click()} disabled={busy}>
            {busy ? 'Uploading…' : 'Choose binary & create'}
          </Button>

          {error && <Text color="danger" className="version-error">{error}</Text>}

          {mine.length > 0 && (
            <div className="version-list">
              <Text color="secondary" variant="caption-2">Custom formatters for {language}:</Text>
              {mine.map((f) => (
                <div key={f.id} className="version-list-item">
                  <Text>{f.label}</Text>
                  <Button view="flat-danger" size="xs" onClick={() => removeFormatter(f.id)}>
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          )}
        </Dialog.Body>
        <Dialog.Footer onClickButtonCancel={() => setOpen(false)} textButtonCancel="Close" />
      </Dialog>
    </>
  )
}
