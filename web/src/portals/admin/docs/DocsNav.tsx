import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { GUIDE_SECTIONS, guideHref, topicHref } from './lookup';
import type { SearchHit } from './search';

/**
 * The guide's search box and contents tree.
 *
 * ⚠️  The search box stays outside the part that collapses on a phone: the
 *     reader who came to find one answer should not have to open a menu first.
 *
 * ⚠️  Section expansion is local state seeded from the route — the current
 *     section opens itself, but every other one stays as the reader left it.
 *     Deriving "open" from the route alone would make the section you are in
 *     impossible to collapse.
 */
export function DocsNav({
  query,
  onQueryChange,
  hits,
  currentSectionId,
  currentTopicId,
  onNavigate,
}: {
  query: string;
  onQueryChange: (next: string) => void;
  /** Non-null while searching: the tree then shows only the matching topics. */
  hits: readonly SearchHit[] | null;
  currentSectionId: string | undefined;
  currentTopicId: string | undefined;
  /** Any link in the tree was followed — the page clears its search. */
  onNavigate: () => void;
}) {
  const { t } = useTranslation();
  const uid = useId();
  const searchRef = useRef<HTMLInputElement>(null);

  // Phone only: whether the contents sit open above the article. Ignored at ≥1200px, where they are always shown.
  const [mobileOpen, setMobileOpen] = useState(false);
  const [openIds, setOpenIds] = useState<ReadonlySet<string>>(
    () => new Set(currentSectionId ? [currentSectionId] : []),
  );

  useEffect(() => {
    if (!currentSectionId) return;
    setOpenIds((previous) =>
      previous.has(currentSectionId) ? previous : new Set(previous).add(currentSectionId),
    );
  }, [currentSectionId]);

  const hitIds = hits ? new Set(hits.map((hit) => hit.topic.id)) : null;

  const toggleSection = (id: string) => {
    setOpenIds((previous) => {
      const next = new Set(previous);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  };

  const followed = () => {
    setMobileOpen(false);
    onNavigate();
  };

  const bodyId = `${uid}-body`;
  const searchId = `${uid}-search`;

  return (
    <div className="docs-nav">
      <div role="search" className="docs-search">
        <label htmlFor={searchId} className="visually-hidden">
          {t('guide.searchLabel')}
        </label>
        <input
          ref={searchRef}
          id={searchId}
          type="search"
          className="docs-search__input"
          value={query}
          placeholder={t('guide.searchPlaceholder')}
          autoComplete="off"
          enterKeyHint="search"
          onChange={(event) => {
            onQueryChange(event.target.value);
          }}
        />
        {query ? (
          <button
            type="button"
            className="docs-search__clear"
            aria-label={t('guide.clearSearch')}
            onClick={() => {
              onQueryChange('');
              searchRef.current?.focus();
            }}
          >
            <span aria-hidden>×</span>
          </button>
        ) : null}
      </div>

      <button
        type="button"
        className="docs-nav__toggle"
        aria-expanded={mobileOpen}
        aria-controls={bodyId}
        onClick={() => {
          setMobileOpen((previous) => !previous);
        }}
      >
        <span>{t('guide.navLabel')}</span>
        <span className="docs-nav__chevron" aria-hidden />
      </button>

      <nav
        id={bodyId}
        className={`docs-nav__body ${mobileOpen ? 'is-open' : ''}`}
        aria-label={t('guide.navLabel')}
      >
        <ul className="docs-nav__sections" lang="ar" dir="rtl">
          {GUIDE_SECTIONS.map((section) => {
            const topics = hitIds
              ? section.topics.filter((topic) => hitIds.has(topic.id))
              : section.topics;
            if (topics.length === 0) return null;

            const open = hitIds !== null || openIds.has(section.id);
            const listId = `${uid}-${section.id}`;
            const sectionCurrent = section.id === currentSectionId && !currentTopicId;

            return (
              <li key={section.id} className="docs-nav__section">
                <div className="docs-nav__row">
                  <Link
                    to={guideHref(section.id)}
                    className="docs-nav__section-link"
                    aria-current={sectionCurrent ? 'page' : undefined}
                    onClick={followed}
                  >
                    <span aria-hidden>{section.icon}</span>
                    <span>{section.title}</span>
                  </Link>
                  {/* Hidden while searching: the matches are all shown, there is nothing to fold. */}
                  {hitIds === null ? (
                    <button
                      type="button"
                      className="docs-nav__fold"
                      aria-expanded={open}
                      aria-controls={listId}
                      aria-label={t('guide.toggleSection', { section: section.title })}
                      onClick={() => {
                        toggleSection(section.id);
                      }}
                    >
                      <span className="docs-nav__chevron" aria-hidden />
                    </button>
                  ) : null}
                </div>

                <ul id={listId} className="docs-nav__topics" hidden={!open}>
                  {topics.map((topic) => (
                    <li key={topic.id}>
                      <Link
                        to={topicHref({ section, topic })}
                        className="docs-nav__topic"
                        aria-current={
                          section.id === currentSectionId && topic.id === currentTopicId
                            ? 'page'
                            : undefined
                        }
                        onClick={followed}
                      >
                        {topic.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
