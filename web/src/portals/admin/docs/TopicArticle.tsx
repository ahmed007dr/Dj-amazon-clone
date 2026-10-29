import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useCan } from '@/features/auth/useCan';

import { Inline } from './Inline';
import { problemKey, TOPICS_BY_ID, topicDomId, topicHref } from './lookup';
import type { DocTopic } from './types';

/** A route with a `:param` cannot be opened as written — there is no id to fill in. */
function isLinkable(path: string): boolean {
  return !path.split(/[?#]/)[0]?.split('/').some((segment) => segment.startsWith(':'));
}

/**
 * One topic of the guide.
 *
 * ⚠️  The article is `lang="ar" dir="rtl"` whatever the interface language is:
 *     the content is written in Arabic only (it is not in the locale files), and
 *     an English-mode panel would otherwise lay Arabic sentences out left-to-right,
 *     scrambling the punctuation and the order of mixed Latin/Arabic words.
 *     The chrome labels inside it (headings) carry the *interface* language back.
 */
export function TopicArticle({
  topic,
  openProblems,
  onToggleProblem,
}: {
  topic: DocTopic;
  openProblems: ReadonlySet<string>;
  onToggleProblem: (key: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const can = useCan();

  const domId = topicDomId(topic.id);
  const chrome = { lang: i18n.language, dir: i18n.dir() } as const;

  // ⚠️  An id that matches no topic is dropped rather than rendered as a dead link:
  //     content is written section by section, so a `related` entry may point at a
  //     topic that has not been published yet.
  const related = (topic.related ?? []).flatMap((id) => {
    const ref = TOPICS_BY_ID.get(id);
    return ref && ref.topic.id !== topic.id ? [ref] : [];
  });

  const tips = topic.tips ?? [];

  return (
    <article id={domId} className="docs-topic" aria-labelledby={`${domId}-title`} lang="ar" dir="rtl">
      <header className="docs-topic__head">
        {/* ⚠️  `tabIndex={-1}`: a deep link or a nav click moves focus here, so a
            keyboard / screen-reader user lands on the topic and not back at the top of the page. */}
        <h3 id={`${domId}-title`} className="docs-topic__title" tabIndex={-1}>
          {topic.title}
        </h3>
        <p className="docs-topic__summary">
          <Inline text={topic.summary} />
        </p>

        <div className="docs-topic__meta">
          {topic.path && isLinkable(topic.path) && can(topic.permission) ? (
            <Link className="btn btn--secondary btn--sm docs-topic__open" to={topic.path}>
              <span {...chrome}>{t('guide.openScreen')}</span>
              <span aria-hidden>←</span>
            </Link>
          ) : null}
          {topic.permission ? (
            <span className="docs-topic__perm">
              {/* ⚠️  The colon sits *inside* the labelled span: left outside, in an English
                  interface it falls into the article's RTL run and lands before the label. */}
              <span {...chrome}>{t('guide.permission')}:</span>{' '}
              <code dir="ltr">{topic.permission}</code>
            </span>
          ) : null}
        </div>
      </header>

      {topic.benefits.length > 0 ? (
        <section className="docs-block" aria-labelledby={`${domId}-benefits`}>
          <h4 id={`${domId}-benefits`} className="docs-block__title" {...chrome}>
            {t('guide.benefits')}
          </h4>
          <ul className="docs-list docs-list--check">
            {topic.benefits.map((benefit, index) => (
              <li key={index}>
                <Inline text={benefit} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {topic.steps.length > 0 ? (
        <section className="docs-block" aria-labelledby={`${domId}-steps`}>
          <h4 id={`${domId}-steps`} className="docs-block__title" {...chrome}>
            {t('guide.steps')}
          </h4>
          <ol className="docs-steps">
            {topic.steps.map((step, index) => (
              <li key={index} className="docs-step">
                <span className="docs-step__title">
                  <Inline text={step.title} />
                </span>
                {step.detail ? (
                  <span className="docs-step__detail">
                    <Inline text={step.detail} />
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {tips.length > 0 ? (
        <section className="docs-block" aria-labelledby={`${domId}-tips`}>
          <h4 id={`${domId}-tips`} className="docs-block__title" {...chrome}>
            {t('guide.tips')}
          </h4>
          <ul className="docs-list docs-list--tip">
            {tips.map((tip, index) => (
              <li key={index}>
                <Inline text={tip} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {topic.problems.length > 0 ? (
        <section className="docs-block" aria-labelledby={`${domId}-problems`}>
          <h4 id={`${domId}-problems`} className="docs-block__title" {...chrome}>
            {t('guide.problems')}
          </h4>
          <ul className="docs-problems">
            {topic.problems.map((problem, index) => {
              const key = problemKey(topic.id, index);
              const open = openProblems.has(key);
              const bodyId = `${domId}-problem-${index}`;

              return (
                <li key={key} className={`docs-problem ${open ? 'is-open' : ''}`}>
                  <h5 className="docs-problem__heading">
                    <button
                      type="button"
                      className="docs-problem__trigger"
                      aria-expanded={open}
                      aria-controls={bodyId}
                      onClick={() => {
                        onToggleProblem(key);
                      }}
                    >
                      <span>
                        <Inline text={problem.problem} />
                      </span>
                      <span className="docs-problem__chevron" aria-hidden />
                    </button>
                  </h5>
                  {/* ⚠️  `hidden`, not a class: it is the one switch that hides the body from
                      assistive tech too — and the print stylesheet overrides it in a single
                      rule, so a printed sheet always carries every solution. */}
                  <div id={bodyId} className="docs-problem__body" hidden={!open}>
                    <dl className="docs-problem__facts">
                      {problem.cause ? (
                        <div>
                          <dt {...chrome}>{t('guide.cause')}</dt>
                          <dd>
                            <Inline text={problem.cause} />
                          </dd>
                        </div>
                      ) : null}
                      <div>
                        <dt {...chrome}>{t('guide.solution')}</dt>
                        <dd>
                          <Inline text={problem.solution} />
                        </dd>
                      </div>
                    </dl>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {related.length > 0 ? (
        <section className="docs-block docs-block--related" aria-labelledby={`${domId}-related`}>
          <h4 id={`${domId}-related`} className="docs-block__title" {...chrome}>
            {t('guide.related')}
          </h4>
          <ul className="docs-related">
            {related.map((ref) => (
              <li key={ref.topic.id}>
                <Link to={topicHref(ref)}>{ref.topic.title}</Link>
                <span className="docs-related__section">{ref.section.title}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
