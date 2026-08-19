import { useTranslation } from 'react-i18next';

import { useAdminCommissionExplain, type CommissionRecord } from '@/features/targets/api';
import { Drawer } from '@/shared/ui/Drawer';
import { Spinner } from '@/shared/ui/Spinner';

import './CommissionExplainDrawer.css';

/** ترتيب مقصود: من الإيراد إلى الربح إلى الشريحة إلى المبلغ. */
const ORDER = [
  'employee',
  'period',
  'orders_count',
  'gross_sales',
  'returns',
  'net_sales',
  'cost',
  'gross_profit',
  'target',
  'achieved',
  'achievement_percent',
  'scheme',
  'base',
  'base_amount',
  'tier',
  'rate',
  'amount',
];

/**
 * تفسير العمولة.
 *
 * ⚠️  **العمولة رقم يُصرَف — ولا يُصرَف رقم لا يُفسَّر.**
 *
 *     «لماذا عمولتي ٤٢٠ لا ٦٠٠؟» سؤال يأتي من كل مندوب في أول
 *     شهر. بلا هذا اللوح يفتح المحاسب الشيفرة أو يخمّن، وكلاهما
 *     يُنتج إجابة لا تُثبَت.
 *
 * ⚠️  و**السطور بترتيب الاشتقاق لا الأبجدية**: المبيعات ثم
 *     المرتجعات ثم الصافي ثم التكلفة ثم الربح — كل سطر يُشتق
 *     ممّا فوقه، والقارئ يتتبّع الحساب بدل أن يقفز فيه.
 */
export function CommissionExplainDrawer({
  record,
  onClose,
}: {
  record: CommissionRecord | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const explain = useAdminCommissionExplain(record?.id ?? null);

  return (
    <Drawer
      open={record !== null}
      onClose={onClose}
      {...(record ? { title: record.employee_name } : {})}
    >
      {explain.isPending ? (
        <Spinner />
      ) : explain.data ? (
        <dl className="commission-explain">
          {ORDER.filter((key) => explain.data[key] !== undefined).map((key) => (
            <div key={key} className={key === 'amount' ? 'is-total' : ''}>
              <dt>{t(`targets.explainRow.${key}`, { defaultValue: key })}</dt>
              <dd dir="ltr">{String(explain.data[key])}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </Drawer>
  );
}
