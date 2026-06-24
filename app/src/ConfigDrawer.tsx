import { useCallback, useEffect, useState } from 'react'
import { Button, Spin, Text } from '@gravity-ui/uikit'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import { draftConfig, setConfigDraft } from './draftStore'

interface Props {
  open: boolean
  /** which config to show first when opened */
  initialLang: Language
  onClose: () => void
  /** called after a successful save (config files changed) */
  onSaved?: () => void
}

const TITLE: Record<Language, string> = {
  cpp: '.clang-format',
  python: 'ruff.toml',
}

export default function ConfigDrawer({ open, initialLang, onClose, onSaved }: Props) {
  const [lang, setLang] = useState<Language>(initialLang)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  // adopt the playground language each time the drawer is opened
  useEffect(() => {
    if (open) setLang(initialLang)
  }, [open, initialLang])

  const load = useCallback(async (which: Language) => {
    setLoading(true)
    setError(null)
    setSaved(false)
    try {
      // show the local draft if there is one, otherwise the live server config
      const drafted = draftConfig(which)
      if (drafted !== undefined) {
        setContent(drafted)
        return
      }
      const res = await fetch(`/api/config/${which}`)
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? 'Failed to load config')
        return
      }
      setContent(data.content)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) load(lang)
  }, [open, lang, load])

  const save = useCallback(() => {
    setError(null)
    // save to the local draft, not the server — Publish flushes it later
    setConfigDraft(lang, content)
    setSaved(true)
    onSaved?.()
    window.setTimeout(() => setSaved(false), 2000)
  }, [lang, content, onSaved])

  return (
    <>
      {open && <div className="drawer-overlay" onClick={onClose} />}
      <div className={`config-drawer${open ? ' open' : ''}`}>
        <div className="config-drawer-header">
          <span className="config-drawer-title">Edit config</span>
          <div className="config-lang-toggle">
            <Button
              view={lang === 'cpp' ? 'action' : 'flat'}
              size="s"
              onClick={() => setLang('cpp')}
            >
              .clang-format
            </Button>
            <Button
              view={lang === 'python' ? 'action' : 'flat'}
              size="s"
              onClick={() => setLang('python')}
            >
              ruff.toml
            </Button>
          </div>
          <span className="config-drawer-spacer" />
          {saved && <Text color="positive">draft saved ✓</Text>}
          <Button view="action" size="s" onClick={save} disabled={loading}>
            Save draft
          </Button>
          <Button view="flat" size="s" onClick={onClose}>
            ✕
          </Button>
        </div>

        {error && (
          <Text color="danger" className="config-drawer-error">
            {error}
          </Text>
        )}

        <div className="config-drawer-body">
          {loading ? (
            <div className="config-drawer-loading">
              <Spin size="m" />
            </div>
          ) : (
            <CodeMirrorEditor
              key={lang}
              value={content}
              language={lang}
              plainText
              onChange={setContent}
            />
          )}
        </div>

        <div className="config-drawer-foot">
          <Text color="secondary" variant="caption-2">
            Editing {TITLE[lang]} — Save keeps it in your local draft and applies
            to the next format / test run. Publish pushes it to the server.
          </Text>
        </div>
      </div>
    </>
  )
}
