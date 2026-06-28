// Per-language editor support that the frontend bundles: a display label, the
// CodeMirror syntax extension, and a playground demo sample.
//
// The backend formatter registry (`formatters.ts` / GET /api/formatters) says
// *which* languages have formatters; this table provides the editor-side support
// for the languages the app can highlight. Adding a language = one entry here
// (+ bundling its CodeMirror module) plus registering a formatter on the backend.
import type { Extension } from '@codemirror/state'
import { cpp } from '@codemirror/lang-cpp'
import { python } from '@codemirror/lang-python'

// @ts-ignore — Vite raw import
import demoCpp from './demo.cpp?raw'
// @ts-ignore — Vite raw import
import demoPy from './demo.py?raw'

export interface LanguageDef {
  label: string // display name, e.g. "C++"
  cm: () => Extension // CodeMirror language extension factory
  demo: string // playground sample
}

export const LANGUAGE_DEFS: Record<string, LanguageDef> = {
  cpp: { label: 'C++', cm: cpp, demo: demoCpp as string },
  python: { label: 'Python', cm: python, demo: demoPy as string },
}

export const hasLanguage = (lang: string): boolean => lang in LANGUAGE_DEFS
export const languageLabel = (lang: string): string => LANGUAGE_DEFS[lang]?.label ?? lang
export const languageDemo = (lang: string): string => LANGUAGE_DEFS[lang]?.demo ?? ''
export const bundledLanguages = (): string[] => Object.keys(LANGUAGE_DEFS)
