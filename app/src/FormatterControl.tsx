import { Select } from '@gravity-ui/uikit'
import { useFormatters, formattersForLanguage } from './formatters'

interface Props {
  language: string
  value: string
  onChange: (formatterId: string) => void
}

/**
 * Picks which formatter to use for a language. Renders nothing when the language
 * has a single formatter (the common case) — only appears once a language has
 * more than one (e.g. python: ruff / black).
 */
export default function FormatterControl({ language, value, onChange }: Props) {
  useFormatters() // re-render when the registry loads
  const fmts = formattersForLanguage(language)
  if (fmts.length <= 1) return null
  return (
    <Select
      value={value ? [value] : []}
      onUpdate={(v) => onChange(v[0])}
      size="s"
      width={120}
      title="Which formatter to use"
    >
      {fmts.map((f) => (
        <Select.Option key={f.id} value={f.id}>
          {f.label}
        </Select.Option>
      ))}
    </Select>
  )
}
