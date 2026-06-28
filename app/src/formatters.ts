// Client mirror of the backend formatter registry (GET /api/formatters).
//
// The frontend is registry-driven: language/formatter lists, config filenames
// and which formatters support a version axis all come from here, not hardcoded
// cpp/clang-format, python/ruff. Loaded once at startup; components subscribe via
// useFormatters() and re-render when it arrives.
import { useSyncExternalStore } from 'react'
import { bundledLanguages } from './languages'

export interface FormatterInfo {
  id: string // "clang-format", "ruff"
  label: string // "clang-format", "ruff format"
  language: string // "cpp", "python"
  default: boolean // the default formatter for its language
  versioned: boolean // supports the version axis (versions, matrix, shadows)
  patchable: boolean // top-level key patch (whatif) applies
  config: { filename: string; syntax: string } | null
}

let _formatters: FormatterInfo[] = []
let _loaded = false
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((l) => l())
}

export async function loadFormatters(): Promise<FormatterInfo[]> {
  try {
    const r = await fetch('/api/formatters')
    const d = await r.json()
    _formatters = (d.formatters ?? []) as FormatterInfo[]
  } catch {
    _formatters = []
  }
  _loaded = true
  emit()
  return _formatters
}

export const allFormatters = (): FormatterInfo[] => _formatters
export const formattersLoaded = (): boolean => _loaded

export const formatterById = (id: string | undefined): FormatterInfo | undefined =>
  id ? _formatters.find((f) => f.id === id) : undefined

export const formattersForLanguage = (lang: string): FormatterInfo[] =>
  _formatters.filter((f) => f.language === lang)

export const defaultFormatter = (lang: string | undefined): FormatterInfo | undefined =>
  lang
    ? _formatters.find((f) => f.language === lang && f.default) ?? formattersForLanguage(lang)[0]
    : undefined

/** Resolve a formatter id OR a legacy language name to a FormatterInfo. */
export const resolveFormatter = (key: string | undefined): FormatterInfo | undefined =>
  formatterById(key) ?? defaultFormatter(key)

/**
 * Languages offered in the UI: those the backend has a formatter for AND the
 * frontend can syntax-highlight. Falls back to the bundled set until the
 * registry has loaded, so the pickers never flash empty.
 */
export function availableLanguages(): string[] {
  const bundled = new Set(bundledLanguages())
  if (!_loaded || _formatters.length === 0) return [...bundled]
  const seen = new Set<string>()
  const out: string[] = []
  for (const f of _formatters) {
    if (bundled.has(f.language) && !seen.has(f.language)) {
      seen.add(f.language)
      out.push(f.language)
    }
  }
  return out
}

// re-render when the registry loads/changes
export const useFormatters = (): FormatterInfo[] =>
  useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => _formatters,
  )
