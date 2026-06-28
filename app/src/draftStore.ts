// Client-side draft layer.
//
// format-quorum is a shared service: writing config/test edits straight to the
// server means concurrent users clobber each other. Instead every edit lands
// here, in localStorage, as a personal draft over the live server state. The UI
// renders "server merged with draft"; nothing reaches the server until the user
// hits Publish (which flushes the whole draft) or Discard (which drops it).
import { useSyncExternalStore } from 'react'
import type { TestCase } from './types'
import { resolveFormatter } from './formatters'

const KEY = 'fq-draft-v1'
const JSON_H = { 'Content-Type': 'application/json' }

// a shadow config: a named alt .clang-format that reuses a real version's binary
// (`base`) but its own config. It appears in the UI as a pseudo-version.
export interface ShadowMeta {
  id: string // `shadow-<n>`; also the clang_version it's selected as
  base: string // the real clang-format version whose binary it runs on
  name: string
}
export interface ShadowDraft extends ShadowMeta {
  content: string // the shadow's .clang-format text (its config draft lives here)
}

export interface Draft {
  // overridden config text per config key. The key is `python` or, since cpp
  // configs are per clang-format version, `cpp@<version>` (see configKey()).
  configs: Record<string, string>
  created: Record<string, TestCase> // draft-only tests (id starts with "draft-")
  updated: Record<string, Partial<TestCase>> // patches to existing server tests
  deleted: string[] // ids of server tests marked for deletion
  // shadow configs created locally (id → meta+content); their config text lives
  // here rather than in `configs`, so creating one counts as a single change.
  shadowsCreated: Record<string, ShadowDraft>
  shadowsDeleted: string[] // ids of *published* shadows staged for deletion
}

const empty = (): Draft => ({
  configs: {},
  created: {},
  updated: {},
  deleted: [],
  shadowsCreated: {},
  shadowsDeleted: [],
})

function load(): Draft {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return { ...empty(), ...JSON.parse(raw) }
  } catch {
    /* ignore corrupt drafts */
  }
  return empty()
}

let state: Draft = load()
const listeners = new Set<() => void>()

function commit(next: Draft) {
  state = next
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    /* storage full / disabled — keep working in-memory */
  }
  listeners.forEach((l) => l())
}

export function subscribe(l: () => void) {
  listeners.add(l)
  return () => {
    listeners.delete(l)
  }
}
export const getDraft = () => state

export function draftCount(s: Draft = state): number {
  return (
    Object.keys(s.configs).length +
    Object.keys(s.created).length +
    Object.keys(s.updated).length +
    s.deleted.length +
    Object.keys(s.shadowsCreated).length +
    s.shadowsDeleted.length
  )
}

let seq = Date.now()
export const newDraftId = () => `draft-${seq++}`
export const isDraftId = (id: string) => id.startsWith('draft-')

// ── config drafts ───────────────────────────────────────────────────────────
// A config draft is keyed by *formatter*: `<formatter>` for an unversioned one
// (e.g. `ruff`), or `<formatter>@<version>` for a versioned one (e.g.
// `clang-format@22.1.8`). configKey() resolves the formatter from the code's
// language; it returns undefined for a versioned formatter when the version
// isn't known yet so callers fall back to the server's resolved-default config.
// `formatter` is a formatter id (or a legacy language, resolved to its default)
export function configKey(formatter: string, version?: string): string | undefined {
  const fmt = resolveFormatter(formatter)
  if (!fmt) return undefined
  if (!fmt.versioned) return fmt.id
  return version ? `${fmt.id}@${version}` : undefined
}
export function parseConfigKey(key: string): { formatter: string; version?: string } {
  const at = key.indexOf('@')
  if (at < 0) return { formatter: key }
  return { formatter: key.slice(0, at), version: key.slice(at + 1) }
}

// a `<formatter>@<id>` key whose id is a locally-created shadow → that shadow's
// content lives in shadowsCreated, not in `configs`
function shadowIdOfKey(key: string): string | undefined {
  const at = key.indexOf('@')
  if (at < 0) return undefined
  const id = key.slice(at + 1)
  return state.shadowsCreated[id] ? id : undefined
}

export function setConfigDraft(key: string, content: string) {
  const sid = shadowIdOfKey(key)
  if (sid) {
    const sh = state.shadowsCreated[sid]
    commit({ ...state, shadowsCreated: { ...state.shadowsCreated, [sid]: { ...sh, content } } })
    return
  }
  commit({ ...state, configs: { ...state.configs, [key]: content } })
}
export function clearConfigDraft(key: string) {
  const configs = { ...state.configs }
  delete configs[key]
  commit({ ...state, configs })
}
export const draftConfig = (key: string | undefined): string | undefined => {
  if (key === undefined) return undefined
  const sid = shadowIdOfKey(key)
  if (sid) return state.shadowsCreated[sid].content
  return state.configs[key]
}

// ── shadow configs ──────────────────────────────────────────────────────────
export const isShadowId = (id: string | undefined): boolean =>
  !!id && id.startsWith('shadow-')
export const newShadowId = () => `shadow-${seq++}`

export function addDraftShadow(meta: ShadowMeta, content: string) {
  commit({
    ...state,
    shadowsCreated: { ...state.shadowsCreated, [meta.id]: { ...meta, content } },
  })
}
/** Delete a shadow: drop a local draft one, or stage a published one for deletion. */
export function deleteShadow(id: string) {
  if (state.shadowsCreated[id]) {
    const shadowsCreated = { ...state.shadowsCreated }
    delete shadowsCreated[id]
    commit({ ...state, shadowsCreated })
  } else {
    const shadowsDeleted = state.shadowsDeleted.includes(id)
      ? state.shadowsDeleted
      : [...state.shadowsDeleted, id]
    commit({ ...state, shadowsDeleted })
  }
}
export const draftShadow = (id: string | undefined): ShadowDraft | undefined =>
  id === undefined ? undefined : state.shadowsCreated[id]

// locally-created (unpublished) shadows — the server doesn't know these yet, so
// the matrix takes them as ad-hoc columns to run before they're published
export const draftCreatedShadows = (): ShadowDraft[] => Object.values(state.shadowsCreated)

// server shadows merged with the local draft — what the UI's version lists show
export function effectiveShadows(server: ShadowMeta[]): ShadowMeta[] {
  const kept = server.filter((s) => !state.shadowsDeleted.includes(s.id))
  return [...kept, ...Object.values(state.shadowsCreated)]
}

/**
 * What to send to /api/format (and friends) for a (language, selected version),
 * applying any local draft. Returns the `formatter` + `version` + `config`
 * overrides ready to spread into the request body.
 *
 * A *draft* shadow isn't on the server yet, so we run its base version with its
 * draft config. A *published* shadow is selected by its id (the server resolves
 * the binary); a draft edit of its config rides along as a `config` override.
 */
export function formatOverrides(
  formatter: string,
  version: string | undefined,
): { formatter?: string; version?: string; config?: string } {
  const fmt = resolveFormatter(formatter)
  if (!fmt) return {}
  if (!fmt.versioned) {
    const cfg = draftConfig(fmt.id)
    return { formatter: fmt.id, ...(cfg !== undefined ? { config: cfg } : {}) }
  }
  if (!version) return { formatter: fmt.id }
  const sh = state.shadowsCreated[version]
  if (sh) return { formatter: fmt.id, version: sh.base, config: sh.content }
  const cfg = draftConfig(`${fmt.id}@${version}`)
  return { formatter: fmt.id, version, ...(cfg !== undefined ? { config: cfg } : {}) }
}

// ── test drafts ─────────────────────────────────────────────────────────────
export function addDraftTest(t: TestCase) {
  commit({ ...state, created: { ...state.created, [t.id]: t } })
}
export function patchTest(id: string, patch: Partial<TestCase>) {
  if (isDraftId(id)) {
    commit({ ...state, created: { ...state.created, [id]: { ...state.created[id], ...patch } } })
  } else {
    commit({ ...state, updated: { ...state.updated, [id]: { ...state.updated[id], ...patch } } })
  }
}
export function removeTest(id: string) {
  if (isDraftId(id)) {
    const created = { ...state.created }
    delete created[id]
    commit({ ...state, created })
  } else {
    const updated = { ...state.updated }
    delete updated[id]
    const deleted = state.deleted.includes(id) ? state.deleted : [...state.deleted, id]
    commit({ ...state, updated, deleted })
  }
}
export const discardAll = () => commit(empty())

// server tests merged with the draft overlay — what the UI actually shows
export function effectiveTests(server: TestCase[]): TestCase[] {
  const merged = server
    .filter((t) => !state.deleted.includes(t.id))
    .map((t) => (state.updated[t.id] ? { ...t, ...state.updated[t.id] } : t))
  return [...merged, ...Object.values(state.created)]
}

// ── publish ─────────────────────────────────────────────────────────────────
export async function publishDraft(): Promise<{ ok: boolean; errors: string[] }> {
  const s = state
  const errors: string[] = []
  const fail = async (label: string, r: Response) =>
    errors.push(`${label}: ${(await r.json().catch(() => ({}))).error ?? r.status}`)

  // shadow configs first, so their config key exists before any config edit of
  // a published shadow lands; the create call carries the shadow's content
  for (const sh of Object.values(s.shadowsCreated)) {
    const r = await fetch('/api/shadow-configs', {
      method: 'POST', headers: JSON_H,
      body: JSON.stringify({ id: sh.id, base: sh.base, name: sh.name, content: sh.content }),
    })
    if (!r.ok) await fail(`shadow "${sh.name}"`, r)
  }
  for (const key of Object.keys(s.configs)) {
    const { formatter, version } = parseConfigKey(key)
    const r = await fetch(`/api/config/${formatter}`, {
      method: 'PUT', headers: JSON_H,
      body: JSON.stringify({ content: s.configs[key], ...(version ? { version } : {}) }),
    })
    if (!r.ok) await fail(`config ${key}`, r)
  }
  for (const id of s.deleted) {
    const r = await fetch(`/api/tests/${id}`, { method: 'DELETE' })
    if (!r.ok && r.status !== 404) await fail(`delete ${id}`, r)
  }
  for (const id of Object.keys(s.updated)) {
    const r = await fetch(`/api/tests/${id}`, {
      method: 'PUT', headers: JSON_H, body: JSON.stringify(s.updated[id]),
    })
    if (!r.ok) await fail(`update ${id}`, r)
  }
  for (const t of Object.values(s.created)) {
    const { id: _drop, ...body } = t
    const r = await fetch('/api/tests', { method: 'POST', headers: JSON_H, body: JSON.stringify(body) })
    if (!r.ok) await fail(`create "${t.name}"`, r)
  }
  for (const id of s.shadowsDeleted) {
    const r = await fetch(`/api/shadow-configs/${id}`, { method: 'DELETE' })
    if (!r.ok && r.status !== 404) await fail(`delete shadow ${id}`, r)
  }
  if (errors.length === 0) discardAll()
  return { ok: errors.length === 0, errors }
}

// ── hooks ───────────────────────────────────────────────────────────────────
export const useDraft = (): Draft => useSyncExternalStore(subscribe, getDraft)
export const useDraftCount = (): number => draftCount(useDraft())
// server shadows merged with the draft, re-rendering when the draft changes
export const useShadows = (server: ShadowMeta[]): ShadowMeta[] => {
  useDraft()
  return effectiveShadows(server)
}
