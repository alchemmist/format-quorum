import { ActionTooltip, Button, Icon, Spin, type IconData } from '@gravity-ui/uikit'
import { ArrowUpFromLine, Code, Flask, Gear, TrashBin } from '@gravity-ui/icons'
import { HEADER_SLOT_IDS } from './HeaderSlot'

// The set of top-level tabs. Adding a new tab is just another entry here — the
// header chrome (toggle + slots) adapts; the new view contributes its own
// controls via <HeaderSlot>.
export const TABS = [
  { key: 'playground', label: 'Playground', icon: Code },
  { key: 'tests', label: 'Tests', icon: Flask },
] as const satisfies ReadonlyArray<{ key: string; label: string; icon: IconData }>

export type View = (typeof TABS)[number]['key']

interface Props {
  view: View
  onChangeView: (view: View) => void
  onOpenConfig: () => void
  // universal draft bar — shown for any tab whenever there are local edits
  draftCount: number
  publishing: boolean
  publishingEnabled: boolean
  onPublish: () => void
  onDiscard: () => void
}

/**
 * The single header shared by every tab. It renders only the universal chrome —
 * the title, the tab toggle, the Config button and the draft bar — plus two
 * empty slots (`center`, `right`) that the active view fills via {@link HeaderSlot}.
 */
export default function AppHeader({
  view,
  onChangeView,
  onOpenConfig,
  draftCount,
  publishing,
  publishingEnabled,
  onPublish,
  onDiscard,
}: Props) {
  return (
    <header className="app-header">
      <div className="app-header-left">
        <h1 className="app-title">Format Quorum</h1>

        <div className="view-toggle">
          {TABS.map((tab) => (
            <Button
              key={tab.key}
              view={view === tab.key ? 'action' : 'flat'}
              size="s"
              onClick={() => onChangeView(tab.key)}
            >
              <Icon data={tab.icon} size={15} />
              <span className="view-toggle-label">{tab.label}</span>
            </Button>
          ))}
        </div>

        <ActionTooltip
          title="Edit config"
          description="Open the formatter config editor — Ctrl/Cmd + ,"
        >
          <Button
            view="outlined"
            size="s"
            className="config-open-btn"
            onClick={onOpenConfig}
            aria-label="Edit config"
          >
            <Icon data={Gear} size={15} />
          </Button>
        </ActionTooltip>
      </div>

      {/* the active view portals its language/version pickers here */}
      <div className="app-header-center" id={HEADER_SLOT_IDS.center} />

      <div className="app-header-right">
        {/* the active view portals its own actions (Format, Reset, …) here */}
        <div className="app-header-actions" id={HEADER_SLOT_IDS.right} />

        {/* the draft plate stays the right-most thing in the header on every tab */}
        {draftCount > 0 && (
          <div className="draft-bar" title="Local unsaved changes (config + tests)">
            <span className="draft-count">{draftCount} unsaved</span>
            <Button
              view="action"
              size="s"
              onClick={onPublish}
              disabled={publishing || !publishingEnabled}
              title={publishingEnabled ? undefined : 'Publishing is disabled on production'}
            >
              {publishing ? (
                <span className="btn-spin">
                  <Spin size="xs" />
                  Publishing
                </span>
              ) : (
                <>
                  <Icon data={ArrowUpFromLine} size={14} />
                  Publish
                </>
              )}
            </Button>
            <Button view="flat" size="s" onClick={onDiscard} disabled={publishing}>
              <Icon data={TrashBin} size={14} />
              Discard
            </Button>
          </div>
        )}
      </div>
    </header>
  )
}
