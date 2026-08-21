import './Skeleton.css';

/**
 * ⚠️  A skeleton with the dimensions of the content to come, not a spinner in the middle.
 *
 *     A spinner leaves the layout jumping when the data arrives; a skeleton
 *     reserves the space and so fixes the position — which is the difference
 *     between a page that feels fast and one that feels unsettled.
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
