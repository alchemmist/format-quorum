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
import { go } from '@codemirror/lang-go'
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

export interface LanguageDef {
  label: string // display name, e.g. "C++"
  cm: () => Extension // CodeMirror language extension factory
  demo: string // playground sample
}

export const LANGUAGE_DEFS: Record<string, LanguageDef> = {
  cpp: { label: 'C++', cm: cpp, demo: demoCpp as string },
  python: { label: 'Python', cm: python, demo: demoPy as string },
  go: {
    label: 'Go',
    cm: go,
    demo: 'package main\n\nfunc main() {\n\tx := 1\n\t_ = x\n}\n',
  },
  rust: {
    label: 'Rust',
    cm: rust,
    demo: 'fn main(){let x=1;let _=x;}\n',
  },
  javascript: {
    label: 'JavaScript',
    cm: () => javascript(),
    demo: 'const x={a:1,b:2}\nfunction f(a,b){return a+b}\n',
  },
  typescript: {
    label: 'TypeScript',
    cm: () => javascript({ typescript: true }),
    demo: 'const x:number=1\ninterface P{a:number;b:string}\n',
  },
  json: {
    label: 'JSON',
    cm: json,
    demo: '{"a":1,"b":[1,2,3],"c":{"d":true}}\n',
  },
  css: {
    label: 'CSS',
    cm: css,
    demo: 'a{color:red;margin:0}\n.box{padding:1px;border:none}\n',
  },
  html: {
    label: 'HTML',
    cm: () => html(),
    demo: '<div>\n<p>hi</p>\n<span>x</span>\n</div>\n',
  },
  markdown: {
    label: 'Markdown',
    cm: () => markdown(),
    demo: '#   Title\n\n-  one\n- two\n',
  },
  yaml: {
    label: 'YAML',
    cm: yaml,
    demo: 'a:   1\nb:  2\nlist:\n- x\n- y\n',
  },
  java: {
    label: 'Java',
    cm: java,
    demo: 'class A{int x=1;public int f(){return x;}}\n',
  },
  shell: {
    label: 'Shell',
    cm: () => StreamLanguage.define(shell),
    demo: 'if [ "$x" = 1 ];then echo hi;fi\n',
  },
  toml: {
    label: 'TOML',
    cm: () => StreamLanguage.define(toml),
    demo: 'a={b=1,c=2}\n[x]\ny=1\n',
  },
}

export const hasLanguage = (lang: string): boolean => lang in LANGUAGE_DEFS
export const languageLabel = (lang: string): string => LANGUAGE_DEFS[lang]?.label ?? lang
export const languageDemo = (lang: string): string => LANGUAGE_DEFS[lang]?.demo ?? ''
export const bundledLanguages = (): string[] => Object.keys(LANGUAGE_DEFS)
