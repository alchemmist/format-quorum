import { describe, expect, it } from 'vitest'
import { languageFromPath } from './url'

describe('languageFromPath', () => {
  const supported = ['cpp', 'python', 'rust', 'java']

  it('restores every supported language from the route', () => {
    expect(languageFromPath('/rust', supported)).toBe('rust')
    expect(languageFromPath('/java', supported)).toBe('java')
  })

  it('falls back to cpp for unknown routes', () => {
    expect(languageFromPath('/missing', supported)).toBe('cpp')
  })
})
