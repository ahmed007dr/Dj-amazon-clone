import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';

import './ActionMenu.css';

export interface ActionMenuItem {
  /** Stable key — the label may change with the language. */
  key: string;
  label: string;
  onSelect: () => void;
  /** `danger` for the destructive one (delete) — it is also separated from the rest. */
  tone?: 'default' | 'danger';
  disabled?: boolean;
  /** Leaves the item out entirely (permission, record state) — unlike `disabled`, nothing is shown. */
  hidden?: boolean;
}

interface Props {
  items: ActionMenuItem[];
  /** The trigger's text. Defaults to "Actions". */
  label?: string;
  /** Also the accessible name of the menu, e.g. "Actions for <product>". */
  menuLabel?: string;
  /** Disables the trigger — e.g. while a mutation for this row is running. */
  disabled?: boolean;
}

const GAP = 4;
const EDGE = 8;

/**
 * A row's "Actions" dropdown — pick one action from a list.
 *
 * ⚠️  **A list to choose from, not a row of buttons.**
 *
 *     Five ghost buttons side by side make the actions column the widest cell in
 *     the table, push the data off a 1280px screen, and give a delete button the
 *     same weight and the same distance from the cursor as "edit". Here the
 *     destructive item sits last, behind a divider.
 *
 * ⚠️  **Rendered in a portal with `position: fixed`.**
 *
 *     Tables and cards sit inside wrappers that clip overflow (and on a phone,
 *     inside a card list). An absolutely-positioned menu is cut off by the last
 *     row of a short table; measured against the viewport, it opens upwards
 *     instead and is never clipped.
 *
 * ⚠️  The menu closes on scroll and resize rather than following the trigger.
 *     A menu left floating over content that moved away is worse than closing it.
 *
 * ⚠️  Choosing an item closes the menu **without returning focus to the trigger**.
 *     The action usually opens a drawer or modal that takes focus itself; moving
 *     focus back here afterwards would steal it from the first field (the same
 *     failure the shared Drawer/Modal had to be fixed for). Escape, which opens
 *     nothing, does return focus.
 */
export function ActionMenu({ items, label, menuLabel, disabled = false }: Props) {
  const { t } = useTranslation();
  const menuId = useId();

  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);

  const visible = items.filter((item) => !item.hidden);

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false);
    setPosition(null);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  // Measure after the menu is in the DOM (hidden), then place it against the trigger.
  useLayoutEffect(() => {
    if (!open || position !== null) return;
    const trigger = triggerRef.current;
    const menu = menuRef.current;
    if (!trigger || !menu) return;

    const anchor = trigger.getBoundingClientRect();
    const { offsetWidth: width, offsetHeight: height } = menu;
    const rtl = getComputedStyle(trigger).direction === 'rtl';

    // The menu's end edge lines up with the trigger's end edge in both directions.
    const wanted = rtl ? anchor.left : anchor.right - width;
    const left = Math.max(EDGE, Math.min(wanted, window.innerWidth - width - EDGE));

    const below = anchor.bottom + GAP;
    const fitsBelow = below + height <= window.innerHeight - EDGE;
    const top = fitsBelow ? below : Math.max(EDGE, anchor.top - GAP - height);

    setPosition({ top, left });
  }, [open, position]);

  // Focus the first enabled item once the menu is placed (so it does not scroll the page while hidden).
  useEffect(() => {
    if (!open || position === null) return;
    menuRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
    // ⚠️  Depends on `position` only — not on `items`, which is a fresh array every render.
  }, [open, position]);

  // Outside click / scroll / resize close it. Bound only while open.
  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      close(false);
    }
    function onDismiss() {
      close(false);
    }
    function onScroll(event: Event) {
      // ⚠️  The menu itself scrolls when it is taller than the viewport — that must not close it.
      if (menuRef.current?.contains(event.target as Node)) return;
      close(false);
    }

    document.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('resize', onDismiss);
    // Capture: the scroll that matters is usually the page's or a wrapper's, not the window's.
    window.addEventListener('scroll', onScroll, true);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('resize', onDismiss);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [open, close]);

  if (visible.length === 0) return null;

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    // ⚠️  React events bubble through a portal to the *React* parent — a clickable table row
    //     would otherwise receive the Enter / Space meant for a menu item.
    event.stopPropagation();
    const buttons = Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [],
    );
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        buttons[(index + 1) % buttons.length]?.focus();
        break;
      case 'ArrowUp':
        event.preventDefault();
        buttons[(index - 1 + buttons.length) % buttons.length]?.focus();
        break;
      case 'Home':
        event.preventDefault();
        buttons[0]?.focus();
        break;
      case 'End':
        event.preventDefault();
        buttons[buttons.length - 1]?.focus();
        break;
      case 'Escape':
        event.preventDefault();
        event.stopPropagation();
        close(true);
        break;
      case 'Tab':
        // Leaving by Tab closes it; focus continues from the trigger, not from the portal at the end of <body>.
        close(true);
        break;
      default:
    }
  }

  const text = label ?? t('admin.actions');

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="action-menu__trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        disabled={disabled}
        onClick={(event) => {
          // A clickable row must not also open its detail when its menu is opened.
          event.stopPropagation();
          if (open) close(false);
          else setOpen(true);
        }}
        onKeyDown={(event) => {
          event.stopPropagation();
          if (event.key === 'ArrowDown' && !open) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span>{text}</span>
        <svg className="action-menu__chevron" viewBox="0 0 12 12" aria-hidden>
          <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>

      {open
        ? createPortal(
            <div
              ref={menuRef}
              id={menuId}
              role="menu"
              aria-label={menuLabel ?? text}
              className="action-menu__panel surface"
              style={{
                top: position?.top ?? 0,
                left: position?.left ?? 0,
                visibility: position ? 'visible' : 'hidden',
              }}
              onKeyDown={onMenuKeyDown}
              onClick={(event) => {
                event.stopPropagation();
              }}
            >
              {visible.map((item, index) => {
                // The destructive item is set apart so it is not the one a hurried click lands on.
                const separated = item.tone === 'danger' && index > 0;
                return (
                  <div key={item.key} role="none">
                    {separated ? <hr className="action-menu__divider" /> : null}
                    <button
                      type="button"
                      role="menuitem"
                      className={`action-menu__item${item.tone === 'danger' ? ' is-danger' : ''}`}
                      disabled={item.disabled}
                      onClick={() => {
                        close(false);
                        item.onSelect();
                      }}
                    >
                      {item.label}
                    </button>
                  </div>
                );
              })}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
