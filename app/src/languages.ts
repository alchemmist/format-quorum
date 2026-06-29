// Per-language editor support that the frontend bundles: a display label, the
// CodeMirror syntax extension, and a playground demo sample.
//
// The backend formatter registry (`formatters.ts` / GET /api/formatters) says
// *which* languages have formatters; this table provides the editor-side support
// for the languages the app can highlight. Adding a language = one entry here
// (+ bundling its CodeMirror module) plus registering a formatter on the backend.
import type { Extension } from '@codemirror/state'
import { StreamLanguage } from '@codemirror/language'
import { cpp } from '@codemirror/lang-cpp'
import { python } from '@codemirror/lang-python'
import { rust } from '@codemirror/lang-rust'
import { javascript } from '@codemirror/lang-javascript'
import { json } from '@codemirror/lang-json'
import { css } from '@codemirror/lang-css'
import { html } from '@codemirror/lang-html'
import { markdown } from '@codemirror/lang-markdown'
import { yaml } from '@codemirror/lang-yaml'
import { java } from '@codemirror/lang-java'
import { shell } from '@codemirror/legacy-modes/mode/shell'
import { toml } from '@codemirror/legacy-modes/mode/toml'

import demoCpp from './demo.cpp?raw'
import demoPy from './demo.py?raw'
import demoRs from './demo.rs?raw'
import demoJs from './demo.js?raw'
import demoTs from './demo.ts?raw'
import demoJson from './demo.json?raw'
import demoCss from './demo.css?raw'
import demoHtml from './demo.html?raw'
import demoMd from './demo.md?raw'
import demoYaml from './demo.yaml?raw'
import demoJava from './demo.java?raw'
import demoSh from './demo.sh?raw'
import demoToml from './demo.toml?raw'

export interface LanguageDef {
  label: string // display name, e.g. "C++"
  cm: () => Extension // CodeMirror language extension factory
  demo: string // playground sample
}

export const LANGUAGE_DEFS: Record<string, LanguageDef> = {
  cpp: { label: 'C++', cm: cpp, demo: demoCpp as string },
  python: { label: 'Python', cm: python, demo: demoPy as string },
  rust: { label: 'Rust', cm: rust, demo: demoRs as string },
  javascript: { label: 'JavaScript', cm: () => javascript(), demo: demoJs as string },
  typescript: {
    label: 'TypeScript',
    cm: () => javascript({ typescript: true }),
    demo: demoTs as string,
  },
  json: { label: 'JSON', cm: json, demo: demoJson as string },
  css: { label: 'CSS', cm: css, demo: demoCss as string },
  html: { label: 'HTML', cm: () => html(), demo: demoHtml as string },
  markdown: { label: 'Markdown', cm: () => markdown(), demo: demoMd as string },
  yaml: { label: 'YAML', cm: yaml, demo: demoYaml as string },
  java: { label: 'Java', cm: java, demo: demoJava as string },
  shell: { label: 'Shell', cm: () => StreamLanguage.define(shell), demo: demoSh as string },
  toml: { label: 'TOML', cm: () => StreamLanguage.define(toml), demo: demoToml as string },
}

export const hasLanguage = (lang: string): boolean => lang in LANGUAGE_DEFS
export const languageLabel = (lang: string): string => LANGUAGE_DEFS[lang]?.label ?? lang
export const languageDemo = (lang: string): string => LANGUAGE_DEFS[lang]?.demo ?? ''
export const bundledLanguages = (): string[] => Object.keys(LANGUAGE_DEFS)
