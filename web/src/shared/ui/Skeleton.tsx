import './Skeleton.css';

/**
 * ⚠️  هيكل بأبعاد المحتوى القادم لا دوّارة في المنتصف.
 *
 *     الدوّارة تُبقي التخطيط يقفز عند وصول البيانات؛ والهيكل يحجز
 *     المساحة فيثبت المكان — وهو الفرق بين صفحة تبدو سريعة وأخرى
 *     تبدو مضطربة.
 */
export function Skeleton({
  width = '100%',
  height = '1rem',
  radius,
}: {
  width?: string;
  height?: string;
  radius?: string;
}) {
  return (
    <span
      className="skeleton"
      style={{ inlineSize: width, blockSize: height, borderRadius: radius }}
      aria-hidden
    />
  );
}

export function SkeletonGrid({ count = 8 }: { count?: number }) {
  return (
    <div className="grid-auto" aria-hidden>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="surface skeleton-card">
          <Skeleton height="9rem" radius="var(--radius)" />
          <Skeleton width="70%" />
          <Skeleton width="40%" />
        </div>
      ))}
    </div>
  );
}
