import { Select } from '@gravity-ui/uikit'
import { useFormatters, formattersForLanguage } from './formatters'

interface Props {
  language: string
  value: string
  onChange: (formatterId: string) => void
}

/**
 * Picks which formatter to use for a language. Always shown — the formatter is a
 * real choice for every language — but locked (disabled) when the language has a
 * single formatter (e.g. cpp: clang-format), and interactive once it has more
 * than one (e.g. python: ruff / black). Renders nothing only until the registry
 * has loaded.
 */
export default function FormatterControl({ language, value, onChange }: Props) {
  useFormatters() // re-render when the registry loads
  const fmts = formattersForLanguage(language)
  if (fmts.length === 0) return null
  const only = fmts.length === 1
  // when locked to the single formatter, show it regardless of `value` (which may
  // briefly lag the language switch)
  const selected = only ? [fmts[0].id] : value ? [value] : []
  return (
    <Select
      value={selected}
      onUpdate={(v) => onChange(v[0])}
      size="s"
      width={150}
      disabled={only}
      title={only ? `${fmts[0].label} — the only formatter for this language` : 'Which formatter to use'}
    >
      {fmts.map((f) => (
        <Select.Option key={f.id} value={f.id}>
          {f.label}
        </Select.Option>
      ))}
    </Select>
  )
}
