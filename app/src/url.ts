// Small helpers to keep shareable state in the URL query string.
// Each call does a read-modify-write of the full query string, so independent
// params (view, filter, version, test) can be updated without clobbering each
// other.

export function getQueryParam(key: string): string | null {
  return new URLSearchParams(window.location.search).get(key)
}

export function setQueryParam(key: string, value: string | null | undefined) {
  const params = new URLSearchParams(window.location.search)
  if (value === null || value === undefined || value === '') {
    params.delete(key)
  } else {
    params.set(key, value)
  }
  const qs = params.toString()
  const url = window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash
  window.history.replaceState(null, '', url)
}

/** Absolute, shareable link to a specific test on the Tests tab. */
export function testShareUrl(id: string): string {
  const params = new URLSearchParams(window.location.search)
  params.set('view', 'tests')
  params.set('test', id)
  return `${window.location.origin}${window.location.pathname}?${params.toString()}`
}
