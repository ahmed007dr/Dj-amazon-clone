import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useLocation, useParams } from 'react-router-dom';

import { DocsNav } from '@/portals/admin/docs/DocsNav';
import {
  GUIDE_ROOT,
  GUIDE_SECTIONS,
  guideHref,
  problemKey,
  readHash,
  TOPICS_BY_ID,
  topicDomId,
  topicHref,
} from '@/portals/admin/docs/lookup';
import { SearchResults } from '@/portals/admin/docs/SearchResults';
import { buildIndex, searchTopics } from '@/portals/admin/docs/search';
import { TopicArticle } from '@/portals/admin/docs/TopicArticle';
import type { DocSection } from '@/portals/admin/docs/types';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AdminDocsPage.css';

/** The `<h2>` of whatever the content area shows — what focus moves to after a navigation. */
const CONTENT_HEADING_ID = 'docs-content-title';

/**
 * The in-app user guide: `/admin/docs` (welcome) and `/admin/docs/:sectionId`
 * (one section, every topic of it stacked), with `#topicId` deep links.
 *
 * ⚠️  **A section is one long page, not one topic at a time.**
 *
 *     The owner prints or saves a section as PDF to hand to a new cashier; a
 *     page per topic would make that twelve prints. Stacking also lets a reader
 *     scroll from "add a product" into "prices" without a click. The cost —
 *     the browser cannot scroll to `#topic` by itself, the element does not
 *     exist when it looks — is paid once, in the effect below.
 *
 * ⚠️  **Open to every admin-portal user, with no permission guard.**
 *     The guide only explains; nothing in it reads or changes data. A guard
 *     would hide the explanation from exactly the person who was just refused
 *     a screen and wants to know what it is.
 */
export function AdminDocsPage() {
  const { t, i18n } = useTranslation();
  const { sectionId } = useParams<{ sectionId: string }>();
  const location = useLocation();

  const [query, setQuery] = useState('');

  const index = useMemo(() => buildIndex(GUIDE_SECTIONS), []);
  const hits = useMemo(
    () => (query.trim() ? searchTopics(index, query) : null),
    [index, query],
  );
  const searching = hits !== null;

  // ⚠️  Stable on purpose — both are handed to children that put them in effects / memo deps.
  const clearSearch = useCallback(() => {
    setQuery('');
  }, []);

  const section = GUIDE_SECTIONS.find((candidate) => candidate.id === sectionId);
  const hashId = readHash(location.hash);
  const hashRef = hashId ? TOPICS_BY_ID.get(hashId) : undefined;

  // ── Scroll & focus ────────────────────────────────────────
  // ⚠️  The browser scrolls to `#id` only if the element exists when the URL
  //     is loaded; here it is rendered by React a moment later (and a nav click
  //     inside the same page never reloads anything). So the page does it.
  //
  // ⚠️  `signature` guards the replay: StrictMode runs this effect twice with
  //     identical inputs on mount, and the second run must not scroll or
  //     steal focus again. A *click on the link already in the URL* produces a
  //     new `location.key`, so it correctly re-scrolls.
  //
  // ⚠️  No `scroll-behavior` fight: the first arrival jumps (`instant`), later
  //     moves defer to the stylesheet (smooth, switched off for reduced motion).
  const lastSignature = useRef<string | null>(null);
  const { key: locationKey, hash } = location;
  useEffect(() => {
    // The results replace the article, so there is nothing to scroll to yet.
    // `searching` is a dependency: when the query clears, this runs again and
    // finds the topic the reader just picked.
    if (searching) return;

    const signature = `${locationKey}|${hash}`;
    if (lastSignature.current === signature) return;
    const firstArrival = lastSignature.current === null;
    lastSignature.current = signature;

    const id = readHash(hash);
    const target = id ? document.getElementById(topicDomId(id)) : null;

    if (target) {
      target.scrollIntoView({ block: 'start', behavior: firstArrival ? 'instant' : 'auto' });
      target.querySelector<HTMLElement>('.docs-topic__title')?.focus({ preventScroll: true });
      return;
    }

    // ⚠️  Navigating inside a SPA keeps the previous scroll offset — landing in the
    //     middle of the next section reads as "the page is broken".
    window.scrollTo({ top: 0, behavior: 'instant' });
    // Focus is moved only after a navigation the reader made, never on first load
    // (that would pull a screen reader away from the page it just announced).
    if (!firstArrival) {
      document.getElementById(CONTENT_HEADING_ID)?.focus({ preventScroll: true });
    }
  }, [locationKey, hash, searching]);

  // ── Nothing written yet ───────────────────────────────────
  if (GUIDE_SECTIONS.length === 0) {
    return (
      <div className="docs-page">
        <PageHeader title={t('guide.title')} description={t('guide.subtitle')} />
        <StateMessage icon="📘" title={t('guide.emptyTitle')} body={t('guide.emptyBody')} />
      </div>
    );
  }

  // ⚠️  A `#topic` that lives in another section is sent there instead of failing
  //     silently. Related links and old bookmarks do not always know which section
  //     a topic ended up in — the topic id is the stable part, the section is not.
  if (hashRef && hashRef.section.id !== sectionId) {
    return <Navigate to={topicHref(hashRef)} replace />;
  }

  const arabic = i18n.language.startsWith('ar');

  let content: ReactNode;
  if (hits) {
    content = <SearchResults hits={hits} onPick={clearSearch} />;
  } else if (section) {
    content = <SectionView key={section.id} section={section} />;
  } else if (sectionId) {
    content = (
      <StateMessage
        icon="🧭"
        title={t('guide.notFoundTitle')}
        body={t('guide.notFoundBody')}
        action={
          <Link className="btn btn--secondary btn--md" to={GUIDE_ROOT}>
            {t('guide.backToGuide')}
          </Link>
        }
      />
    );
  } else {
    content = <Welcome />;
  }

  return (
    <div className="docs-page">
      <PageHeader title={t('guide.title')} description={t('guide.subtitle')} />

      {arabic ? null : <Alert tone="info">{t('guide.arabicOnly')}</Alert>}

      <div className="docs">
        <div className="docs__side">
          <DocsNav
            query={query}
            onQueryChange={setQuery}
            hits={hits}
            currentSectionId={section?.id}
            currentTopicId={hashRef?.topic.id}
            onNavigate={clearSearch}
          />
        </div>

        <div className="docs__main">{content}</div>
      </div>
    </div>
  );
}

function Welcome() {
  const { t } = useTranslation();

  return (
    <section className="docs-welcome" aria-labelledby={CONTENT_HEADING_ID}>
      <h2 id={CONTENT_HEADING_ID} className="docs-welcome__title" tabIndex={-1}>
        {t('guide.welcomeTitle')}
      </h2>
      <p className="docs-welcome__body">{t('guide.welcomeBody')}</p>

      <ul className="docs-cards">
        {GUIDE_SECTIONS.map((section) => (
          <li key={section.id} className="docs-card" lang="ar" dir="rtl">
            <Link to={guideHref(section.id)} className="docs-card__title">
              <span aria-hidden>{section.icon}</span>
              <span>{section.title}</span>
            </Link>
            {section.description ? <p className="docs-card__desc">{section.description}</p> : null}
            <ul className="docs-card__topics">
              {section.topics.slice(0, 4).map((topic) => (
                <li key={topic.id}>
                  <Link to={topicHref({ section, topic })}>{topic.title}</Link>
                </li>
              ))}
            </ul>
            <p className="docs-card__count">
              {t('guide.sectionTopics', { count: section.topics.length })}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function SectionView({ section }: { section: DocSection }) {
  const { t } = useTranslation();
  const [openProblems, setOpenProblems] = useState<ReadonlySet<string>>(() => new Set());

  const allKeys = useMemo(
    () =>
      section.topics.flatMap((topic) =>
        topic.problems.map((_, position) => problemKey(topic.id, position)),
      ),
    [section],
  );
  const allOpen = allKeys.length > 0 && allKeys.every((key) => openProblems.has(key));

  const toggleProblem = useCallback((key: string) => {
    setOpenProblems((previous) => {
      const next = new Set(previous);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  }, []);

  return (
    <section className="docs-section" aria-labelledby={CONTENT_HEADING_ID}>
      <header className="docs-section__head" lang="ar" dir="rtl">
        <h2 id={CONTENT_HEADING_ID} className="docs-section__title" tabIndex={-1}>
          <span aria-hidden>{section.icon}</span> {section.title}
        </h2>
        {section.description ? <p className="docs-section__desc">{section.description}</p> : null}
      </header>

      <div className="docs-section__toolbar">
        {allKeys.length > 0 ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setOpenProblems(allOpen ? new Set() : new Set(allKeys));
            }}
          >
            {allOpen ? t('guide.collapseAll') : t('guide.expandAll')}
          </Button>
        ) : null}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            window.print();
          }}
        >
          {t('guide.print')}
        </Button>
      </div>

      {section.topics.length > 1 ? (
        <nav className="docs-toc" aria-label={t('guide.inThisSection')} lang="ar" dir="rtl">
          <ul>
            {section.topics.map((topic) => (
              <li key={topic.id}>
                <Link to={topicHref({ section, topic })}>{topic.title}</Link>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}

      <div className="docs-section__topics">
        {section.topics.map((topic) => (
          <TopicArticle
            key={topic.id}
            topic={topic}
            openProblems={openProblems}
            onToggleProblem={toggleProblem}
          />
        ))}
      </div>
    </section>
  );
}
