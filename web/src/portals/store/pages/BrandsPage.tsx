import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useBrands, useManufacturers } from '@/features/catalog/hooks';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Skeleton } from '@/shared/ui/Skeleton';
import { StateMessage } from '@/shared/ui/StateMessage';

import './BrandsPage.css';

/**
 * صفحة الماركات.
 *
 * ⚠️  **المميّزة أولًا وبعنوان يفصلها.**
 *
 *     `is_featured` قرار تجاري يتّخذه الأدمن ويكلّف اتفاقًا مع
 *     المورّد؛ عرض الماركات بترتيب واحد يُلغي القرار كله ويجعل
 *     الحقل زخرفة في قاعدة البيانات.
 *
 * ⚠️  و**الشعار الغائب يُستبدَل بالحرف الأول لا بمربع فارغ**.
 *
 *     أغلب الماركات المحلية بلا شعار مرفوع؛ الشبكة المليئة
 *     بمربعات رمادية تُقرأ «الصور لم تُحمَّل» لا «لا شعار».
 */
export function BrandsPage() {
  const { t } = useTranslation();
  const localized = useLocalized();

  const brands = useBrands();
  const manufacturers = useManufacturers();

  if (brands.isPending) {
    return (
      <div className="container brands-page">
        <Skeleton height="3rem" />
        <Skeleton height="14rem" />
      </div>
    );
  }

  const all = brands.data ?? [];
  const featured = all.filter((row) => row.is_featured);
  const rest = all.filter((row) => !row.is_featured);

  if (all.length === 0) {
    return (
      <div className="container">
        <PageHeader title={t('catalog.brands')} />
        <StateMessage icon="🏷️" title={t('catalog.noBrands')} body={t('catalog.noBrandsBody')} />
      </div>
    );
  }

  const card = (brand: (typeof all)[number]) => (
    <li key={brand.id}>
      <Link to={`/brands/${brand.slug}`} className="brand-card">
        {brand.logo ? (
          <img src={brand.logo} alt="" loading="lazy" />
        ) : (
          <span className="brand-card__initial" aria-hidden>
            {localized(brand, 'name').slice(0, 1)}
          </span>
        )}
        <strong>{localized(brand, 'name')}</strong>
        {brand.manufacturer ? (
          <small>{localized(brand.manufacturer, 'name')}</small>
        ) : null}
      </Link>
    </li>
  );

  return (
    <div className="container brands-page">
      <PageHeader title={t('catalog.brands')} description={t('catalog.brandsHint')} />

      {featured.length > 0 ? (
        <section>
          <h2 className="brands-page__heading">{t('catalog.featuredBrands')}</h2>
          <ul className="brands-grid">{featured.map(card)}</ul>
        </section>
      ) : null}

      {rest.length > 0 ? (
        <section>
          {featured.length > 0 ? (
            <h2 className="brands-page__heading">{t('catalog.allBrands')}</h2>
          ) : null}
          <ul className="brands-grid">{rest.map(card)}</ul>
        </section>
      ) : null}

      {/* ⚠️  المصنّعون قائمة نصّية لا شبكة: العميل يبحث بالماركة
          («بنادول») لا بالمصنّع («GSK»)، والمصنّع سياق يُطمئن
          لا مدخل تصفّح. */}
      {manufacturers.data && manufacturers.data.length > 0 ? (
        <section>
          <h2 className="brands-page__heading">{t('catalog.manufacturers')}</h2>
          <ul className="manufacturer-list">
            {manufacturers.data.map((row) => (
              <li key={row.id}>
                <strong>{localized(row, 'name')}</strong>
                {row.country ? <span>{row.country}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
