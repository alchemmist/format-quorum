import { beforeEach, describe, expect, it, vi } from 'vitest'

const storage = new Map<string, string>()

beforeEach(() => {
  storage.clear()
  vi.resetModules()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
  })
})

describe('draft persistence', () => {
  it('recovers from structurally invalid saved data', async () => {
    storage.set('fq-draft-v1', JSON.stringify({ configs: null, deleted: {} }))
    const drafts = await import('./draftStore')
    expect(drafts.draftCount()).toBe(0)
  })

  it('removes successful operations after a partial publish', async () => {
    storage.set('fq-draft-v1', JSON.stringify({
      created: {
        'draft-1': {
          id: 'draft-1', name: 'one', language: 'cpp', input: 'a', expected: 'a', muted: false,
        },
        'draft-2': {
          id: 'draft-2', name: 'two', language: 'cpp', input: 'b', expected: 'b', muted: false,
        },
      },
    }))
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{"error":"failed"}', { status: 500 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const drafts = await import('./draftStore')

    expect((await drafts.publishDraft()).ok).toBe(false)
    expect(drafts.draftCount()).toBe(1)
    expect((await drafts.publishDraft()).ok).toBe(true)
    expect(drafts.draftCount()).toBe(0)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })
})
