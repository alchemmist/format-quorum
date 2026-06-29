import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ActionTooltip, Button, Icon, Select, Spin, Text, TextInput } from '@gravity-ui/uikit'
import { Ghost } from '@gravity-ui/icons'
import CodeMirrorEditor, { type Language } from './CodeMirrorEditor'
import { ShadowLabel } from './ShadowLabel'
import { useFormatters, formatterById, resolveFormatter } from './formatters'
import { languageLabel } from './languages'
import {
  draftConfig,
  setConfigDraft,
  configKey,
  addDraftShadow,
  newShadowId,
  draftShadow,
  useShadows,
  type ShadowMeta,
} from './draftStore'
import type { TestCase } from './types'

interface Props {
  open: boolean
  /** which formatter's config to show first (a formatter id or legacy language) */
  initialFormatter: string
  /** which version to show first (versioned formatters only) */
  initialVersion?: string
  onClose: () => void
  /** called after a successful save (config files changed) */
  onSaved?: () => void
}

// per-formatter-id helpers from the registry
const filenameFor = (fid: string) => formatterById(fid)?.config?.filename ?? ''
const isVersioned = (fid: string) => !!formatterById(fid)?.versioned
const langOf = (fid: string): Language => formatterById(fid)?.language ?? 'cpp'

interface Impact {
  nowPass: string[] // were failing on the live config, pass on this draft
  nowFail: string[] // were passing on the live config, fail on this draft
  mutedWouldPass: string[] // muted tests that would pass on this draft (could un-mute)
}

interface HistoryEntry {
  seq: number
  ts: string | null
  author: string
  message: string
  patch: string
}

// colorize a unified diff for the history panel
function PatchView({ patch }: { patch: string }) {
  return (
    <pre className="config-patch">
      {patch.split('\n').map((line, i) => {
        const cls =
          line.startsWith('+') && !line.startsWith('+++')
            ? 'add'
            : line.startsWith('-') && !line.startsWith('---')
              ? 'del'
              : line.startsWith('@@')
                ? 'hunk'
                : ''
        return (
          <div key={i} className={`patch-line ${cls}`}>
            {line || ' '}
          </div>
        )
      })}
    </pre>
  )
}

const norm = (s: string) => s.replace(/\r\n/g, '\n').replace(/\n+$/, '')

export default function ConfigDrawer({
  open,
  initialFormatter,
  initialVersion,
  onClose,
  onSaved,
}: Props) {
  // the selected formatter id (initialFormatter may be a legacy language)
  const [formatterId, setFormatterId] = useState<string>(
    () => resolveFormatter(initialFormatter)?.id ?? initialFormatter,
  )
  // clang-format version (or shadow id) whose config we're editing (cpp only)
  const [versions, setVersions] = useState<string[]>([])
  const [serverShadows, setServerShadows] = useState<ShadowMeta[]>([])
  const shadows = useShadows(serverShadows)
  // every formatter that has a config is selectable in the formatter dropdown,
  // grouped by language (a flat tab strip wouldn't fit dozens of languages)
  const configTabs = useFormatters().filter((f) => f.config)
  const formatterGroups = useMemo(() => {
    const by: Record<string, typeof configTabs> = {}
    for (const f of configTabs) (by[f.language] ??= []).push(f)
    return Object.entries(by)
  }, [configTabs])
  const [version, setVersion] = useState<string | undefined>(initialVersion)
  const [content, setContent] = useState('')
  const [serverContent, setServerContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [impact, setImpact] = useState<Impact | null>(null)
  const [checking, setChecking] = useState(false)
  // "Save as shadow config" name-entry popup
  const shadowBtnRef = useRef<HTMLDivElement>(null)
  const [shadowFormOpen, setShadowFormOpen] = useState(false)
  const [shadowName, setShadowName] = useState('')
  const [shadowSaved, setShadowSaved] = useState(false)
  // version history panel
  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [historyHead, setHistoryHead] = useState(0)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [expandedSeq, setExpandedSeq] = useState<number | null>(null)

  // the real clang-format version a selection runs on (a shadow → its base)
  const baseOf = (ver: string | undefined) =>
    shadows.find((s) => s.id === ver)?.base ?? ver
  // a real version renders as its number; a shadow as the ghost icon + name
  const renderVersion = (v: string) => {
    const sh = shadows.find((s) => s.id === v)
    return sh ? <ShadowLabel>{`${sh.name} (${sh.base})`}</ShadowLabel> : v
  }

  // tracks the last formatter so a *manual* formatter switch can drop its version
  const prevFmtRef = useRef(formatterId)

  // each time the drawer opens, sync to the header: edit the config for the
  // formatter AND the version currently selected in the playground/tests header.
  // prevFmtRef is advanced in step so the formatter-change effect below doesn't
  // then clobber the version back to the formatter's default.
  useEffect(() => {
    if (open) {
      const fid = resolveFormatter(initialFormatter)?.id ?? initialFormatter
      setFormatterId(fid)
      prevFmtRef.current = fid
      setVersion(initialVersion)
      setShowHistory(false) // always reopen on the editor, not the history panel
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialFormatter, initialVersion])

  // normalize the selected formatter to a real id (initialFormatter may be a
  // legacy language, and the registry may load after first render)
  useEffect(() => {
    if (!formatterById(formatterId)) {
      const r = resolveFormatter(formatterId) ?? resolveFormatter(initialFormatter)
      if (r) setFormatterId(r.id)
    }
  }, [configTabs, formatterId, initialFormatter])

  // switching the formatter tab drops the previous formatter's version, so the
  // fetch below re-selects the new formatter's own default (a clang-format
  // version must never linger when the ruff/black tab is opened)
  useEffect(() => {
    if (prevFmtRef.current !== formatterId) {
      prevFmtRef.current = formatterId
      setVersion(undefined)
    }
  }, [formatterId])

  // installed versions of the selected formatter for the picker; default-select one
  useEffect(() => {
    if (!open || !isVersioned(formatterId)) {
      setVersions([])
      setServerShadows([])
      return
    }
    fetch(`/api/formatters/${formatterId}/versions`)
      .then((r) => r.json())
      .then((d) => {
        setVersions(d.versions ?? [])
        setServerShadows(d.shadows ?? [])
        setVersion((prev) => prev ?? d.default ?? (d.versions ?? [])[0])
      })
      .catch(() => {})
  }, [open, formatterId])

  // the cpp config is per-version, so loading depends on the selected version
  const load = useCallback(
    async (which: string, ver: string | undefined) => {
      setLoading(true)
      setError(null)
      setSaved(false)
      setImpact(null)
      try {
        // a *draft* (unpublished) shadow isn't on the server — show its base
        // version's config as the baseline, its draft text as the content
        const sh = isVersioned(which) ? draftShadow(ver) : undefined
        const fetchVer = sh ? sh.base : ver
        const q = isVersioned(which) && fetchVer ? `?version=${encodeURIComponent(fetchVer)}` : ''
        const res = await fetch(`/api/config/${which}${q}`)
        const data = await res.json()
        if (!res.ok) {
          setError(data.error ?? 'Failed to load config')
          return
        }
        setServerContent(data.content)
        // show the local draft for this (lang, version) if there is one
        const drafted = draftConfig(configKey(which, ver))
        setContent(drafted !== undefined ? drafted : data.content)
      } catch (e) {
        setError(String(e))
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    // wait for a concrete version before loading a versioned formatter's config
    if (open && !(isVersioned(formatterId) && version === undefined)) load(formatterId, version)
  }, [open, formatterId, version, load])

  const onChange = useCallback((next: string) => {
    setContent(next)
    setImpact(null) // any edit invalidates a previous impact check
  }, [])

  const save = useCallback(() => {
    setError(null)
    // save to the local draft, not the server — Publish flushes it later
    const key = configKey(formatterId, version)
    if (key === undefined) {
      setError('Pick a version first')
      return
    }
    setConfigDraft(key, content)
    setSaved(true)
    onSaved?.()
    window.setTimeout(() => setSaved(false), 2000)
  }, [formatterId, version, content, onSaved])

  // store the current edits as a new shadow config (local draft) and switch to it
  const saveShadow = useCallback(() => {
    const name = shadowName.trim()
    const base = baseOf(version)
    if (!name || !base) return
    const id = newShadowId()
    addDraftShadow({ id, base, name }, content)
    setShadowFormOpen(false)
    setShadowName('')
    setVersion(id) // edit the new shadow from here on
    setShadowSaved(true)
    window.setTimeout(() => setShadowSaved(false), 2000)
    onSaved?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shadowName, version, content, shadows, onSaved])

  const changed = content !== serverContent

  // Escape closes the drawer, saving the current edits to the draft first (only
  // if there are any, so an unchanged close doesn't create a phantom draft). If
  // the "save as shadow" name popup is open, Escape just dismisses that.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (shadowFormOpen) {
        setShadowFormOpen(false)
        return
      }
      // run before CodeMirror's own Esc handler (which would otherwise eat the
      // first press to clear the cursor) so one Esc always acts
      e.preventDefault()
      e.stopPropagation()
      if (showHistory) {
        setShowHistory(false) // Esc out of the history panel back to the editor
        return
      }
      if (changed) save()
      onClose()
    }
    // capture phase: handle Esc ahead of the focused editor
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open, shadowFormOpen, showHistory, changed, save, onClose])

  // ── version history ───────────────────────────────────────────────────────
  const cfgQuery =
    isVersioned(formatterId) && version ? `?version=${encodeURIComponent(version)}` : ''
  const isDraftShadow = !!draftShadow(version)

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const res = await fetch(`/api/config/${formatterId}/history${cfgQuery}`)
      const data = await res.json()
      // newest first
      setHistory([...(data.versions ?? [])].reverse())
      setHistoryHead(data.head ?? 0)
    } catch {
      /* ignore — panel just shows empty */
    } finally {
      setHistoryLoading(false)
    }
  }, [formatterId, cfgQuery])

  useEffect(() => {
    if (open && showHistory) loadHistory()
  }, [open, showHistory, loadHistory])

  // load an earlier version's content into the editor as a draft (publish to
  // actually roll back on the server — consistent with the draft model)
  const restoreVersion = useCallback(
    async (seq: number) => {
      const res = await fetch(`/api/config/${formatterId}/history/${seq}${cfgQuery}`)
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? 'Failed to load version')
        return
      }
      const key = configKey(formatterId, version)
      setContent(data.content)
      if (key) setConfigDraft(key, data.content)
      setImpact(null)
      setShowHistory(false)
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2000)
    },
    [formatterId, version, cfgQuery],
  )

  // run every test of this language against the live config and against this
  // draft config, and report which tests flip pass/fail.
  const checkImpact = useCallback(async () => {
    setChecking(true)
    setError(null)
    const fmt = async (code: string, config?: string): Promise<string | null> => {
      const res = await fetch('/api/format', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          formatter: formatterId,
          // resolve a shadow to its base binary; baseline (no config) uses that
          // version's published config, candidate uses the edited content
          ...(isVersioned(formatterId) && baseOf(version) ? { version: baseOf(version) } : {}),
          ...(config !== undefined ? { config } : {}),
        }),
      })
      const d = await res.json()
      return res.ok ? (d.formatted as string) : null
    }
    try {
      const all: TestCase[] = await (await fetch('/api/tests')).json()
      const mine = all.filter((t) => t.language === langOf(formatterId))
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
  }, [formatterId, version, content])

  return (
    <>
      {open && <div className="drawer-overlay" onClick={onClose} />}
      <div className={`config-drawer${open ? ' open' : ''}`}>
        <div className="config-drawer-header">
          {/* pick which formatter's config to edit — one dropdown, grouped by
              language, so it scales to many languages/formatters */}
          <Select
            value={formatterById(formatterId) ? [formatterId] : []}
            onUpdate={(v) => setFormatterId(v[0])}
            size="s"
            width={240}
            title="Which formatter's config to edit"
            disablePortal
          >
            {formatterGroups.map(([lang, fs]) => (
              <Select.OptionGroup key={lang} label={languageLabel(lang)}>
                {fs.map((f) => (
                  <Select.Option key={f.id} value={f.id}>
                    {`${f.label} · ${f.config!.filename}`}
                  </Select.Option>
                ))}
              </Select.OptionGroup>
            ))}
          </Select>
          {isVersioned(formatterId) && versions.length > 0 && (
            <Select
              value={version ? [version] : []}
              onUpdate={(v) => setVersion(v[0])}
              size="s"
              width={110}
              title="Which version's config to edit"
              // render the menu inside the drawer so it isn't trapped beneath
              // the drawer's stacking layer (the portal layer sits below it)
              disablePortal
              renderSelectedOption={(opt) => <span>{renderVersion(String(opt.value))}</span>}
            >
              {[...versions, ...shadows.map((s) => s.id)].map((v) => (
                <Select.Option key={v} value={v}>
                  {renderVersion(v)}
                </Select.Option>
              ))}
            </Select>
          )}
          <span className="config-drawer-spacer" />
          {shadowSaved && <Text color="positive">shadow saved ✓</Text>}
          {saved && <Text color="positive">draft saved ✓</Text>}
          {isVersioned(formatterId) && (
            // a plain anchored panel (not a portal) so it sits in the drawer's
            // stacking context, above the editor
            <div className="shadow-anchor" ref={shadowBtnRef}>
              <ActionTooltip
                title="Save as shadow config"
                description={`Store these edits as a separate, named config that reuses this ${
                  formatterById(formatterId)?.label ?? formatterId
                } binary but its own ${filenameFor(formatterId)}. It shows up everywhere as a quasi-version — run it and compare it in the matrix next to the real versions. Saved to your local draft; Publish pushes it to the server.`}
              >
                <Button
                  view="action"
                  size="s"
                  onClick={() => setShadowFormOpen((o) => !o)}
                  disabled={loading || !version}
                  aria-label="Save as shadow config"
                >
                  <Icon data={Ghost} size={16} />
                </Button>
              </ActionTooltip>
              {shadowFormOpen && (
                <div className="shadow-form">
                  <Text variant="caption-2" color="secondary">
                    New shadow config from these edits
                  </Text>
                  <div className="shadow-form-row">
                    <TextInput
                      autoFocus
                      value={shadowName}
                      onUpdate={setShadowName}
                      placeholder="Name, e.g. no-align"
                      size="s"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveShadow()
                        if (e.key === 'Escape') setShadowFormOpen(false)
                      }}
                    />
                    <Button
                      view="action"
                      size="s"
                      onClick={saveShadow}
                      disabled={!shadowName.trim()}
                    >
                      Save
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
          <Button
            view={showHistory ? 'action' : 'flat'}
            size="s"
            onClick={() => setShowHistory((s) => !s)}
            disabled={loading || isDraftShadow}
            title={
              isDraftShadow
                ? 'History is available once the shadow config is published'
                : 'Config version history & rollback'
            }
          >
            History
          </Button>
          <Button view="action" size="s" onClick={save} disabled={loading || showHistory}>
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
          ) : showHistory ? (
            <div className="config-history">
              {historyLoading ? (
                <div className="config-drawer-loading">
                  <Spin size="m" />
                </div>
              ) : history.length === 0 ? (
                <Text color="secondary">No history yet — the base config is version 0.</Text>
              ) : (
                history.map((v) => (
                  <div key={v.seq} className="config-history-item">
                    <div className="config-history-head">
                      <Text variant="subheader-1">v{v.seq}</Text>
                      {v.seq === historyHead && (
                        <Text color="positive" variant="caption-2">
                          current
                        </Text>
                      )}
                      <Text color="secondary" variant="caption-2">
                        {v.ts ? new Date(v.ts).toLocaleString() : 'base config'}
                        {v.author ? ` · ${v.author}` : ''}
                      </Text>
                      <span className="config-drawer-spacer" />
                      {v.patch && (
                        <Button
                          view="flat"
                          size="xs"
                          onClick={() =>
                            setExpandedSeq((s) => (s === v.seq ? null : v.seq))
                          }
                        >
                          {expandedSeq === v.seq ? 'hide diff' : 'diff'}
                        </Button>
                      )}
                      {v.seq !== historyHead && (
                        <Button
                          view="outlined"
                          size="xs"
                          onClick={() => restoreVersion(v.seq)}
                          title="Load this version into the editor as a draft"
                        >
                          Load
                        </Button>
                      )}
                    </div>
                    {v.message && (
                      <Text color="secondary" variant="caption-2" className="config-history-msg">
                        {v.message}
                      </Text>
                    )}
                    {expandedSeq === v.seq && v.patch && <PatchView patch={v.patch} />}
                  </div>
                ))
              )}
            </div>
          ) : (
            <CodeMirrorEditor
              key={`${formatterId}@${version ?? ''}`}
              value={content}
              language={langOf(formatterId)}
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
            Editing {filenameFor(formatterId)}
            {isVersioned(formatterId) && version
              ? (() => {
                  const sh = shadows.find((s) => s.id === version)
                  return sh ? (
                    <>
                      {' '}for shadow config <ShadowLabel>{sh.name}</ShadowLabel> ({sh.base})
                    </>
                  ) : (
                    ` for version ${version}`
                  )
                })()
              : ''}{' '}
            — Save keeps it in your local draft and applies to the next format /
            test run. Publish pushes it to the server.
          </Text>
        </div>
      </div>
    </>
  )
}
