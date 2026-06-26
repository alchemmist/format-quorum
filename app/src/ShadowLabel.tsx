import type { ReactNode } from 'react'
import { Icon } from '@gravity-ui/uikit'
import { Ghost } from '@gravity-ui/icons'

/**
 * Renders a shadow ("quasi-version") label as the Ghost icon + text, matching
 * the icon on the "Save as shadow config" button — instead of a 👻 emoji baked
 * into the name string. Purely a frontend presentation concern: the data layer
 * keeps a plain name; wherever the UI shows a quasi-version it wraps it here.
 */
export function ShadowLabel({ children }: { children: ReactNode }) {
  return (
    <span className="shadow-label">
      <Icon data={Ghost} size={14} />
      {children}
    </span>
  )
}
