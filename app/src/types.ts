import type { Language } from './CodeMirrorEditor'

export interface TestCase {
  id: string
  name: string
  language: Language
  input: string
  expected: string
  muted: boolean
  note?: string
}
