/**
 * بيانات الهوية النصية — للاستهلاك في الهيدر والفوتر وعنوان الصفحة.
 *
 * ⚠️  الاسم والشعار والتواصل تُقرأ في مواضع كثيرة. تمريرها كخصائص
 *     من الجذر يعني سلسلة `props` تعبر خمس طبقات لتصل إلى الفوتر.
 */

import { useLocalizedMap } from '@/shared/i18n/useLocalized';
import { useTheme } from '@/shared/theme';

export function useBrand() {
  const { theme } = useTheme();
  const localized = useLocalizedMap();

  return {
    name: localized(theme?.name),
    tagline: localized(theme?.tagline),
    address: localized(theme?.contact.address),
    contact: theme?.contact,
    social: theme?.social ?? {},
    assets: theme?.assets,
  };
}
