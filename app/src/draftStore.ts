// Client-side draft layer.
//
// format-quorum is a shared service: writing config/test edits straight to the
// server means concurrent users clobber each other. Instead every edit lands
// here, in localStorage, as a personal draft over the live server state. The UI
// renders "server merged with draft"; nothing reaches the server until the user
// hits Publish (which flushes the whole draft) or Discard (which drops it).
import { useSyncExternalStore } from 'react'
import type { Language } from './CodeMirrorEditor'
import type { TestCase } from './types'

const KEY = 'fq-draft-v1'
const JSON_H = { 'Content-Type': 'application/json' }

export interface Draft {
  // overridden config text per config key. The key is `python` or, since cpp
  // configs are per clang-format version, `cpp@<version>` (see configKey()).
  configs: Record<string, string>
  created: Record<string, TestCase> // draft-only tests (id starts with "draft-")
  updated: Record<string, Partial<TestCase>> // patches to existing server tests
  deleted: string[] // ids of server tests marked for deletion
}

const empty = (): Draft => ({ configs: {}, created: {}, updated: {}, deleted: [] })

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
    s.deleted.length
  )
}

let seq = Date.now()
export const newDraftId = () => `draft-${seq++}`
export const isDraftId = (id: string) => id.startsWith('draft-')

// ── config drafts ───────────────────────────────────────────────────────────
// cpp configs are per clang-format version, so a config draft is keyed by
// `python` or `cpp@<version>`. configKey() builds that key; it returns undefined
// for cpp when the version isn't known yet (e.g. versions still loading) so
// callers fall back to the server's resolved-default config.
export function configKey(lang: Language, version?: string): string | undefined {
  if (lang === 'python') return 'python'
  return version ? `cpp@${version}` : undefined
}
export function parseConfigKey(key: string): { lang: Language; version?: string } {
  if (key.startsWith('cpp@')) return { lang: 'cpp', version: key.slice(4) }
  if (key === 'cpp') return { lang: 'cpp' }
  return { lang: 'python' }
}

export function setConfigDraft(key: string, content: string) {
  commit({ ...state, configs: { ...state.configs, [key]: content } })
}
export function clearConfigDraft(key: string) {
  const configs = { ...state.configs }
  delete configs[key]
  commit({ ...state, configs })
}
export const draftConfig = (key: string | undefined): string | undefined =>
  key === undefined ? undefined : state.configs[key]

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

  for (const key of Object.keys(s.configs)) {
    const { lang, version } = parseConfigKey(key)
    const r = await fetch(`/api/config/${lang}`, {
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
  if (errors.length === 0) discardAll()
  return { ok: errors.length === 0, errors }
}

// ── hooks ───────────────────────────────────────────────────────────────────
export const useDraft = (): Draft => useSyncExternalStore(subscribe, getDraft)
export const useDraftCount = (): number => draftCount(useDraft())
