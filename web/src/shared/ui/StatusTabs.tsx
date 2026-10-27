import { useRef, type KeyboardEvent } from 'react';

import { panelDomId, tabDomId } from './tabIds';

import './StatusTabs.css';

export interface TabOption {
  value: string;
  label: string;
  count?: number;
}

/**
 * The status tabs.
 *
 * ⚠️  They scroll horizontally on a phone rather than wrapping onto two lines.
 *
 *     Wrapping makes the bar's height jump when the number of tabs changes, so
 *     the content beneath it moves while the user is reading it.
 *
 * ⚠️  **Roving tabindex** — only the selected tab is in the Tab order.
 *
 *     With every tab focusable, a keyboard user crossing the page has to press
 *     Tab once per tab to get past the bar. The arrows move *within* it instead
 *     (Home/End jump to the ends), which is the pattern the `tablist` role
 *     promises to assistive technology.
 *
 * ⚠️  The arrows are **RTL-aware**: in Arabic the first tab is on the right, so
 *     the right arrow goes to the *previous* tab. Hard-coding "right = next"
 *     makes the arrows fight the visual order for the default language.
 *
 * `id` and `label` are optional so the existing filter-style call sites keep
 * working untouched. Pass `id` when the tabs switch real panels (see `TabPanel`):
 * it wires `id`/`aria-controls` on both sides.
 */
export function StatusTabs({
  options,
  value,
  onChange,
  id,
  label,
}: {
  options: TabOption[];
  value: string;
  onChange: (next: string) => void;
  /** Base for the tab/panel ids — set it when the tabs control `TabPanel`s. */
  id?: string;
  /** The accessible name of the tab list. */
  label?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  // A value matching no option (a stale URL, say) must not leave the bar with no
  // tab stop at all — the first one stays reachable.
  const selectedIndex = options.findIndex((option) => option.value === value);
  const tabStop = selectedIndex === -1 ? 0 : selectedIndex;

  function focusTab(index: number) {
    const option = options[index];
    if (!option) return;
    refs.current[index]?.focus();
    // Selection follows focus: the panels switch instantly (no request per
    // arrow press worth worrying about), and it spares a second keypress.
    if (option.value !== value) onChange(option.value);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (options.length === 0) return;

    const rtl = getComputedStyle(event.currentTarget).direction === 'rtl';
    const current = refs.current.findIndex((node) => node === document.activeElement);
    const from = current === -1 ? tabStop : current;

    let next: number | null = null;
    switch (event.key) {
      case 'ArrowRight':
        next = from + (rtl ? -1 : 1);
        break;
      case 'ArrowLeft':
        next = from + (rtl ? 1 : -1);
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = options.length - 1;
        break;
      default:
        return;
    }

    event.preventDefault();
    // Wraps around: the last tab's "next" is the first
    focusTab((next + options.length) % options.length);
  }

  return (
    <div
      className="status-tabs tabs-scroll"
      role="tablist"
      aria-label={label}
      onKeyDown={handleKeyDown}
    >
      {options.map((option, index) => {
        const selected = value === option.value;

        return (
          <button
            key={option.value}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            role="tab"
            id={id ? tabDomId(id, option.value) : undefined}
            aria-selected={selected}
            aria-controls={id ? panelDomId(id, option.value) : undefined}
            tabIndex={index === tabStop ? 0 : -1}
            className={`status-tab ${selected ? 'is-active' : ''}`}
            onClick={() => {
              onChange(option.value);
            }}
          >
            {option.label}
            {option.count !== undefined ? (
              <span className="status-tab__count">{option.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
