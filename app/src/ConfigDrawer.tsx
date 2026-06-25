import { useCallback, useEffect, useState } from 'react'
import { Button, Spin, Text } from '@gravity-ui/uikit'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import { draftConfig, setConfigDraft } from './draftStore'
import type { TestCase } from './types'

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

interface Impact {
  nowPass: string[] // were failing on the live config, pass on this draft
  nowFail: string[] // were passing on the live config, fail on this draft
  mutedWouldPass: string[] // muted tests that would pass on this draft (could un-mute)
}

const norm = (s: string) => s.replace(/\r\n/g, '\n').replace(/\n+$/, '')

export default function ConfigDrawer({ open, initialLang, onClose, onSaved }: Props) {
  const [lang, setLang] = useState<Language>(initialLang)
  const [content, setContent] = useState('')
  const [serverContent, setServerContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [impact, setImpact] = useState<Impact | null>(null)
  const [checking, setChecking] = useState(false)

  // adopt the playground language each time the drawer is opened
  useEffect(() => {
    if (open) setLang(initialLang)
  }, [open, initialLang])

  const load = useCallback(async (which: Language) => {
    setLoading(true)
    setError(null)
    setSaved(false)
    setImpact(null)
    try {
      const res = await fetch(`/api/config/${which}`)
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? 'Failed to load config')
        return
      }
      setServerContent(data.content)
      // show the local draft if there is one, otherwise the live server config
      const drafted = draftConfig(which)
      setContent(drafted !== undefined ? drafted : data.content)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) load(lang)
  }, [open, lang, load])

  const onChange = useCallback((next: string) => {
    setContent(next)
    setImpact(null) // any edit invalidates a previous impact check
  }, [])

  const save = useCallback(() => {
    setError(null)
    // save to the local draft, not the server — Publish flushes it later
    setConfigDraft(lang, content)
    setSaved(true)
    onSaved?.()
    window.setTimeout(() => setSaved(false), 2000)
  }, [lang, content, onSaved])

  const changed = content !== serverContent

  // run every test of this language against the live config and against this
  // draft config, and report which tests flip pass/fail.
  const checkImpact = useCallback(async () => {
    setChecking(true)
    setError(null)
    const fmt = async (code: string, config?: string): Promise<string | null> => {
      const res = await fetch('/api/format', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language: lang, ...(config !== undefined ? { config } : {}) }),
      })
      const d = await res.json()
      return res.ok ? (d.formatted as string) : null
    }
    try {
      const all: TestCase[] = await (await fetch('/api/tests')).json()
      const mine = all.filter((t) => t.language === lang)
      const nowPass: string[] = []
      const nowFail: string[] = []
      const mutedWouldPass: string[] = []
      await Promise.all(
        mine.map(async (t) => {
          const [live, drafted] = await Promise.all([fmt(t.input), fmt(t.input, content)])
          if (live === null || drafted === null) return
          const passLive = norm(live) === norm(t.expected)
          const passDraft = norm(drafted) === norm(t.expected)
          if (t.muted) {
            // muted tests stay yellow, but a draft that makes one pass means the
            // mute (an accepted compromise) could be lifted — surface that
            if (passDraft && !passLive) mutedWouldPass.push(t.name)
            return
          }
          if (!passLive && passDraft) nowPass.push(t.name)
          else if (passLive && !passDraft) nowFail.push(t.name)
        }),
      )
      setImpact({ nowPass, nowFail, mutedWouldPass })
    } catch (e) {
      setError(String(e))
    } finally {
      setChecking(false)
    }
  }, [lang, content])

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
              onChange={onChange}
            />
          )}
        </div>

        <div className="config-drawer-foot">
          <div className="config-impact-row">
            <Button
              view="outlined"
              size="s"
              onClick={checkImpact}
              disabled={checking || !changed}
              title="Run all tests against the live config and this draft to see what flips"
            >
              {checking ? (
                <span className="btn-spin">
                  <Spin size="xs" />
                  Checking
                </span>
              ) : (
                'Check impact'
              )}
            </Button>
            {!changed ? (
              <Text color="secondary" variant="caption-2">
                No changes vs the live config.
              </Text>
            ) : (
              impact && (
                <Text variant="caption-2">
                  <span className="impact-pos">+{impact.nowPass.length} fixed</span>
                  {' · '}
                  <span className="impact-neg">−{impact.nowFail.length} broken</span>
                  {impact.mutedWouldPass.length > 0 && (
                    <span className="impact-muted">
                      {' · '}
                      {impact.mutedWouldPass.length} muted would pass
                    </span>
                  )}
                </Text>
              )
            )}
          </div>

          {impact &&
            (impact.nowFail.length > 0 ||
              impact.nowPass.length > 0 ||
              impact.mutedWouldPass.length > 0) && (
              <div className="config-impact-lists">
                {impact.nowFail.length > 0 && (
                  <Text color="secondary" variant="caption-2">
                    <span className="impact-neg">breaks:</span> {impact.nowFail.join(', ')}
                  </Text>
                )}
                {impact.nowPass.length > 0 && (
                  <Text color="secondary" variant="caption-2">
                    <span className="impact-pos">fixes:</span> {impact.nowPass.join(', ')}
                  </Text>
                )}
                {impact.mutedWouldPass.length > 0 && (
                  <Text color="secondary" variant="caption-2">
                    <span className="impact-muted">muted would pass:</span>{' '}
                    {impact.mutedWouldPass.join(', ')}
                  </Text>
                )}
              </div>
            )}

          <Text color="secondary" variant="caption-2">
            Editing {TITLE[lang]} — Save keeps it in your local draft and applies
            to the next format / test run. Publish pushes it to the server.
          </Text>
        </div>
      </div>
    </>
  )
}
