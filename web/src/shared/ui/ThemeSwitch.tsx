import { useTranslation } from 'react-i18next';

import { useTheme } from '@/shared/theme';
import type { DefaultMode } from '@/shared/theme';

import './ThemeSwitch.css';

const OPTIONS: { value: DefaultMode; icon: string; key: string }[] = [
  { value: 'LIGHT', icon: '☀', key: 'theme.light' },
  { value: 'DARK', icon: '☾', key: 'theme.dark' },
  { value: 'SYSTEM', icon: '◐', key: 'theme.system' },
];

/**
 * ⚠️  ثلاثة خيارات لا زرّ تبديل ثنائي.
 *
 *     الزر الثنائي يفقد «حسب الجهاز» — فمستخدم يبدّل هاتفه إلى
 *     الداكن ليلًا يجد الموقع وحده بقي فاتحًا، بلا طريقة للعودة.
 */
export function ThemeSwitch() {
  const { t } = useTranslation();
  const { preference, setPreference } = useTheme();

  return (
    <div className="theme-switch" role="group" aria-label={t('theme.label')}>
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          className={`theme-switch__option ${preference === option.value ? 'is-active' : ''}`}
          aria-pressed={preference === option.value}
          aria-label={t(option.key)}
          title={t(option.key)}
          onClick={() => {
            setPreference(option.value);
          }}
        >
          <span aria-hidden>{option.icon}</span>
        </button>
      ))}
    </div>
  );
}
