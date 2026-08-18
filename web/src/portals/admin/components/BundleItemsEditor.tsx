import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useBundleItems,
  useDeleteBundleItem,
  useSaveBundleItem,
  type Bundle,
} from '@/features/academic/adminApi';
import type { AdminProduct } from '@/features/catalog/adminApi';
import { isApiError } from '@/shared/http/errors';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';
import { ProductPicker } from '@/portals/admin/components/ProductPicker';

import './AcademicPanels.css';

/**
 * بنود الحزمة.
 *
 * ⚠️  **«أساسي» يفصل ما لا غنى عنه عمّا يُستحسن.**
 *
 *     الطالب يشتري الأساسي وحده حين يضيق المال؛ وحزمة بلا هذا
 *     التمييز تُعرض «كلها أو لا شيء» فلا تُشترى.
 *
 * ⚠️  و**المنتج يُختار من `ProductPicker` لا من حقل معرّف**.
 *
 *     لصق UUID خطأً يضيف صنفًا لا علاقة له بالحزمة، ولا شيء في
 *     الشاشة يكشفه إلا فتحها من عين الطالب. والمنتقي نفسه المستعمل
 *     في التسويات والشراء — سلوك واحد لا ثلاثة.
 */
export function BundleItemsEditor({ bundle }: { bundle: Bundle }) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const items = useBundleItems(bundle.id);
  const save = useSaveBundleItem();
  const remove = useDeleteBundleItem();

  const [picked, setPicked] = useState<AdminProduct | null>(null);

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const chosen = new Set(items.data?.map((row) => row.product) ?? []);

  const add = () => {
    if (picked === null) return;

    // ⚠️  التكرار يُمنَع هنا بلطف بدل انتظار خطأ الخادم: الرسالة
    //     «موجود سلفًا» أوضح من رفض بقيد فريد.
    if (chosen.has(picked.id)) {
      notify(t('academic.alreadyAdded'), 'info');
      return;
    }

    save.mutate(
      { bundle: bundle.id, product: picked.id, quantity: 1, is_essential: true },
      {
        onSuccess: () => {
          notify(t('academic.itemAdded'), 'success');
          setPicked(null);
        },
        onError: fail,
      },
    );
  };

  return (
    <section className="bundle-items">
      <header className="bundle-items__head">
        <h4>{t('academic.bundleItems')}</h4>
      </header>

      <div className="bundle-items__add">
        <ProductPicker value={picked} onChange={setPicked} />
        <Button size="sm" disabled={picked === null} loading={save.isPending} onClick={add}>
          {t('academic.addItem')}
        </Button>
      </div>

      {items.data && items.data.length > 0 ? (
        <ul className="bundle-items__list">
          {items.data.map((item) => (
            <li key={item.id}>
              <div className="bundle-items__info">
                <strong>{item.product_name}</strong>
                <code dir="ltr">{item.product_sku}</code>
              </div>

              <label className="bundle-items__qty">
                {t('academic.quantity')}
                <input
                  type="number"
                  min="1"
                  dir="ltr"
                  defaultValue={item.quantity}
                  // ⚠️  الحفظ عند مغادرة الحقل لا عند كل ضغطة:
                  //     نداء لكل رقم يعني عشرات الطلبات لبند واحد.
                  onBlur={(event) => {
                    const quantity = Number(event.target.value);
                    if (quantity < 1 || quantity === item.quantity) return;
                    save.mutate({ bundle: bundle.id, id: item.id, quantity }, { onError: fail });
                  }}
                />
              </label>

              <label className="bundle-items__essential">
                <input
                  type="checkbox"
                  checked={item.is_essential}
                  onChange={(event) =>
                    save.mutate(
                      { bundle: bundle.id, id: item.id, is_essential: event.target.checked },
                      { onError: fail },
                    )
                  }
                />
                {t('academic.essential')}
              </label>

              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  remove.mutate(
                    { bundle: bundle.id, id: item.id },
                    {
                      onSuccess: () => notify(t('academic.deleted'), 'success'),
                      onError: fail,
                    },
                  )
                }
              >
                {t('common.delete')}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        // ⚠️  حزمة بلا بنود تُعرض للطالب فارغة — قول ذلك هنا يمنع
        //     نشرها قبل تعبئتها.
        <p className="academic-hint">{t('academic.noItems')}</p>
      )}
    </section>
  );
}
