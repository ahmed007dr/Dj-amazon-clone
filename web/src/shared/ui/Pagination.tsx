import { useTranslation } from 'react-i18next';

import { Button } from './Button';

import './Pagination.css';

/**
 * ترقيم بالصفحات — لشاشات الأدمن وحدها.
 *
 * ⚠️  «صفحة ٥ من ٤٢» معلومة تشغيلية يحتاجها من يعالج الطلبات،
 *     والخادم يكشف `count` لهذه الشاشات فقط. القوائم العامة تستخدم
 *     المؤشر لأن كشف العدد الكلي يعطي المنافس حجم النشاط. (ADR-32)
 */
export function Pagination({
  page,
  pages,
  onChange,
}: {
  page: number;
  pages: number;
  onChange: (next: number) => void;
}) {
  const { t } = useTranslation();

  if (pages <= 1) return null;

  return (
    <nav className="pagination" aria-label={t('common.next')}>
      <Button
        variant="secondary"
        size="sm"
        disabled={page <= 1}
        onClick={() => {
          onChange(page - 1);
        }}
      >
        {t('common.previous')}
      </Button>

      <span className="pagination__status">{t('common.pageOf', { page, pages })}</span>

      <Button
        variant="secondary"
        size="sm"
        disabled={page >= pages}
        onClick={() => {
          onChange(page + 1);
        }}
      >
        {t('common.next')}
      </Button>
    </nav>
  );
}
