import { useTranslation } from 'react-i18next';

import './PeriodPicker.css';

/**
 * اختيار الفترة.
 *
 * ⚠️  **الشهر الحالي افتراضًا لا «كل الوقت».**
 *
 *     «كل الوقت» يخلط شهرًا رابحًا بآخر خاسرًا في رقم واحد لا
 *     يدل على شيء، ويثقل الاستعلام بلا فائدة. والاختصارات أسفلها
 *     تغطي ما يُطلَب فعلًا: هذا الشهر · الماضي · هذه السنة.
 */

function iso(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function monthRange(offset: number): { start: string; end: string } {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  // ⚠️  اليوم صفر من الشهر التالي = آخر يوم في الشهر المطلوب.
  //     كتابة ٣٠ أو ٣١ يدويًا تكسر فبراير وكل شهر من ٣٠ يومًا.
  const end = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0);
  return { start: iso(start), end: iso(end) };
}

export function PeriodPicker({
  value,
  onChange,
}: {
  value: { start?: string; end?: string };
  onChange: (next: { start?: string; end?: string }) => void;
}) {
  const { t } = useTranslation();

  const presets = [
    { key: 'thisMonth', range: monthRange(0) },
    { key: 'lastMonth', range: monthRange(-1) },
    {
      key: 'thisYear',
      range: {
        start: `${new Date().getFullYear()}-01-01`,
        end: iso(new Date()),
      },
    },
  ];

  return (
    <div className="period-picker">
      <div className="period-picker__presets">
        {presets.map((preset) => (
          <button
            key={preset.key}
            type="button"
            className={`period-picker__preset ${
              value.start === preset.range.start && value.end === preset.range.end
                ? 'is-active'
                : ''
            }`}
            onClick={() => onChange(preset.range)}
          >
            {t(`finance.${preset.key}`)}
          </button>
        ))}
      </div>

      <div className="period-picker__range">
        <label>
          {t('finance.from')}
          <input
            type="date"
            value={value.start ?? ''}
            // ⚠️  `max` يمنع اختيار بداية بعد النهاية من الواجهة؛
            //     والخادم يرفضها أيضًا — المدى المقلوب يُنتج تقريرًا
            //     بأصفار يبدو حقيقيًا.
            max={value.end}
            onChange={(event) => onChange({ ...value, start: event.target.value })}
          />
        </label>
        <label>
          {t('finance.to')}
          <input
            type="date"
            value={value.end ?? ''}
            min={value.start}
            onChange={(event) => onChange({ ...value, end: event.target.value })}
          />
        </label>
      </div>
    </div>
  );
}
