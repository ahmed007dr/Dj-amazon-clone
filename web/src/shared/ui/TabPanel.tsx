import type { ReactNode } from 'react';

import { panelDomId, tabDomId } from './tabIds';

import './TabPanel.css';

/**
 * The panel a `StatusTabs` tab controls.
 *
 * ⚠️  `keepMounted` is for panels that **hold state or work in progress**.
 *
 *     Unmounting a panel throws its local state away — an import that is halfway
 *     through its chunk loop, a form with unsaved edits. Such a panel stays
 *     mounted and is only `hidden`. The default is the opposite on purpose: a
 *     panel that holds a password field *should* be wiped when the user leaves
 *     it, and an unmounted panel also costs no queries.
 *
 * The wrapper element is always rendered (hidden when inactive) so that the
 * tab's `aria-controls` never points at an id that is not in the document.
 */
export function TabPanel({
  id,
  value,
  active,
  keepMounted = false,
  className,
  children,
}: {
  /** The same `id` given to the matching `StatusTabs`. */
  id: string;
  value: string;
  active: boolean;
  keepMounted?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={panelDomId(id, value)}
      aria-labelledby={tabDomId(id, value)}
      hidden={!active}
      className={className ? `tab-panel ${className}` : 'tab-panel'}
    >
      {active || keepMounted ? children : null}
    </div>
  );
}
