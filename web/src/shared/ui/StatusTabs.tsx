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
 */
export function StatusTabs({
  options,
  value,
  onChange,
}: {
  options: TabOption[];
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="status-tabs tabs-scroll" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={value === option.value}
          className={`status-tab ${value === option.value ? 'is-active' : ''}`}
          onClick={() => {
            onChange(option.value);
          }}
        >
          {option.label}
          {option.count !== undefined ? (
            <span className="status-tab__count">{option.count}</span>
          ) : null}
        </button>
      ))}
    </div>
  );
}
