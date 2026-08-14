import { useTranslation } from 'react-i18next';

import type { ContrastEntry } from '../adminApi';

import './ContrastReport.css';

/**
 * تقرير التباين.
 *
 * ⚠️  **يُعرض الناجح والفاشل معًا** لا الفاشل وحده.
 *
 *     إظهار الناجح يجعل الأدمن يرى أثر تعديله لحظةً بلحظة: النسبة
 *     تتحرّك مع كل تغيير لون، فيقترب من الحد بدل أن يخمّن.
 *
 * ⚠️  والحد ٤٫٥:١ ليس رأيًا جماليًا — نص رمادي فاتح على أبيض يبدو
 *     أنيقًا على شاشة المصمّم وغير مقروء على هاتف تحت الشمس.
 */
export function ContrastReport({ entries }: { entries: ContrastEntry[] }) {
  const { t } = useTranslation();

  const failing = entries.filter((entry) => !entry.passes_aa).length;

  return (
    <div className="contrast">
      <p className={`contrast__summary ${failing > 0 ? 'is-failing' : ''}`}>
        {failing === 0
          ? t('admin.contrastAllPass')
          : t('admin.contrastFailing', { count: failing })}
      </p>

      <ul className="contrast__list">
        {entries.map((entry) => (
          <li key={entry.key} className="contrast__row">
            <span
              className="contrast__swatch"
              style={{ background: entry.background, color: entry.foreground }}
              aria-hidden
            >
              Aa
            </span>

            <span className="contrast__label">{entry.label}</span>

            <span className={`contrast__ratio ${entry.passes_aa ? 'is-pass' : 'is-fail'}`}>
              {entry.ratio}:1
            </span>

            <span aria-hidden>{entry.passes_aa ? '✓' : '✕'}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
