import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { StateMessage } from '@/shared/ui/StateMessage';

import { topicHref } from './lookup';
import type { Segment, SearchHit } from './search';

function Marked({ segments }: { segments: readonly Segment[] }) {
  return (
    <>
      {segments.map((segment, index) =>
        segment.mark ? <mark key={index}>{segment.text}</mark> : segment.text,
      )}
    </>
  );
}

/**
 * The search results — shown in place of the article while a query is typed.
 *
 * ⚠️  The count sits in a polite live region: a screen-reader user typing
 *     into the box hears "عدد النتائج: 3" without leaving the field, instead
 *     of having to tab away to find out whether anything matched.
 */
export function SearchResults({
  hits,
  onPick,
}: {
  hits: readonly SearchHit[];
  /** A result was followed — the page clears the query so the article shows. */
  onPick: () => void;
}) {
  const { t } = useTranslation();

  if (hits.length === 0) {
    return (
      <StateMessage icon="🔍" title={t('guide.noResultsTitle')} body={t('guide.noResultsBody')} />
    );
  }

  return (
    <section className="docs-results" aria-label={t('guide.searchLabel')}>
      <p className="docs-results__count" role="status">
        {t('guide.resultsCount', { count: hits.length })}
      </p>

      <ol className="docs-results__list">
        {hits.map((hit) => (
          <li key={hit.topic.id} className="docs-result" lang="ar" dir="rtl">
            <Link to={topicHref(hit)} className="docs-result__title" onClick={onPick}>
              <Marked segments={hit.title} />
            </Link>
            <span className="docs-result__section">{hit.section.title}</span>

            {hit.snippet ? (
              <p className="docs-result__snippet">
                <span className="docs-result__field">{t(`guide.matchIn.${hit.snippet.field}`)}</span>
                {hit.snippet.before ? '… ' : ' '}
                <Marked segments={hit.snippet.segments} />
                {hit.snippet.after ? ' …' : ''}
              </p>
            ) : (
              <p className="docs-result__snippet">{hit.topic.summary.replace(/\*\*/g, '')}</p>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
