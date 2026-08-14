import './StatusTabs.css';

export interface TabOption {
  value: string;
  label: string;
  count?: number;
}

/**
 * تبويبات الحالة.
 *
 * ⚠️  تتمرّر أفقيًا على الهاتف ولا تُلفّ في سطرين.
 *
 *     اللفّ يجعل ارتفاع الشريط يقفز عند تغيّر عدد التبويبات، فيتحرّك
 *     المحتوى تحته بينما يقرأه المستخدم.
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
