import { ActionTooltip, Button, Icon, Spin, type IconData } from '@gravity-ui/uikit'
import { ArrowUpFromLine, Code, Flask, Gear, TrashBin } from '@gravity-ui/icons'
import type { ReactNode } from 'react'

// The set of top-level tabs. Adding a new tab is just another entry here.
const TABS = [
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
  center: ReactNode
  actions?: ReactNode
}

/**
 * The single header shared by every tab.
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
  center,
  actions,
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

      <div className="app-header-center">{center}</div>

      <div className="app-header-right">
        <div className="app-header-actions">{actions}</div>

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
