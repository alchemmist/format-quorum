import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/**
 * Lets any view "contribute" controls into the shared {@link AppHeader} without
 * the header knowing anything about them. The header renders stable, empty slot
 * containers; a view renders `<HeaderSlot slot="center">…</HeaderSlot>` and its
 * controls are portaled into the matching spot in the header.
 *
 * - `center` — the centered cluster (language/version pickers, etc.)
 * - `right`  — the right action cluster, after the universal draft bar
 *
 * Only the active view is mounted at a time, so two views never fight over a
 * slot.
 */
export const HEADER_SLOT_IDS = {
  center: 'app-header-center-slot',
  right: 'app-header-right-slot',
} as const

export function HeaderSlot({
  slot,
  children,
}: {
  slot: keyof typeof HEADER_SLOT_IDS
  children: ReactNode
}) {
  const id = HEADER_SLOT_IDS[slot]
  const [el, setEl] = useState<HTMLElement | null>(null)
  useEffect(() => {
    setEl(document.getElementById(id))
  }, [id])
  return el ? createPortal(children, el) : null
}
