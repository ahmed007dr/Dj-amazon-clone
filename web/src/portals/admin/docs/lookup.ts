import { DOC_SECTIONS } from './index';
import { GUIDE_ROOT } from './paths';
import type { DocSection, DocTopic } from './types';

export { GUIDE_ROOT };

export interface TopicRef {
  section: DocSection;
  topic: DocTopic;
}

/**
 * The sections that actually have something to read.
 *
 * ⚠️  An empty section is skipped everywhere (navigation, welcome page, routes)
 *     rather than shown as an empty shell: the guide is written section by
 *     section, and a heading over nothing reads as "this failed to load".
 */
export const GUIDE_SECTIONS: readonly DocSection[] = DOC_SECTIONS.filter(
  (section) => section.topics.length > 0,
);

/** Topic id → where it lives. The first topic wins if two ever share an id. */
export const TOPICS_BY_ID: ReadonlyMap<string, TopicRef> = (() => {
  const byId = new Map<string, TopicRef>();
  for (const section of GUIDE_SECTIONS) {
    for (const topic of section.topics) {
      if (!byId.has(topic.id)) byId.set(topic.id, { section, topic });
    }
  }
  return byId;
})();

/** The URL of a section, or of one topic inside it. */
export function guideHref(sectionId?: string, topicId?: string): string {
  if (!sectionId) return GUIDE_ROOT;
  return topicId ? `${GUIDE_ROOT}/${sectionId}#${topicId}` : `${GUIDE_ROOT}/${sectionId}`;
}

export function topicHref(ref: TopicRef): string {
  return guideHref(ref.section.id, ref.topic.id);
}

/** The DOM id of a topic's `<article>` — prefixed so a slug can never collide with the page's own ids. */
export function topicDomId(topicId: string): string {
  return `doc-${topicId}`;
}

/** The key of one problem inside the page-level "which problems are open" set. */
export function problemKey(topicId: string, index: number): string {
  return `${topicId}:${index}`;
}

/** A hash like `#products` → `products`; tolerant of malformed percent-encoding. */
export function readHash(hash: string): string {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

// ── Contextual help: which topic explains the screen I am on? ────────────

interface PathEntry {
  ref: TopicRef;
  /** Path segments; a `:param` segment matches any single segment. */
  segments: string[];
  /** `?tab=staff` style conditions — a topic bound to a tab answers for that tab only. */
  query: [string, string][];
}

function splitSegments(pathname: string): string[] {
  return pathname.split('/').filter((segment) => segment.length > 0);
}

const PATH_ENTRIES: readonly PathEntry[] = GUIDE_SECTIONS.flatMap((section) =>
  section.topics.flatMap((topic): PathEntry[] => {
    if (!topic.path) return [];
    const [beforeHash = ''] = topic.path.split('#');
    const [pathname = '', search = ''] = beforeHash.split('?');
    return [
      {
        ref: { section, topic },
        segments: splitSegments(pathname),
        query: [...new URLSearchParams(search).entries()],
      },
    ];
  }),
);

/** The portal root: a prefix of every admin URL, so it may only answer for itself. */
const PORTAL_ROOT_SEGMENTS = 1;

/**
 * The topic that best explains a location: the longest matching path prefix,
 * an exact match winning over a prefix, a literal segment over a `:param`.
 *
 * ⚠️  Segment-wise, not `startsWith`: `/admin/orders` must not claim
 *     `/admin/orders-archive`, and `/admin` (the dashboard) must answer for
 *     itself only — as a prefix it would explain every screen that has no topic of its own.
 */
export function findTopicForLocation(pathname: string, search: string): TopicRef | null {
  const here = splitSegments(pathname);
  const params = new URLSearchParams(search);

  let best: { ref: TopicRef; score: number } | null = null;

  for (const entry of PATH_ENTRIES) {
    const { segments } = entry;
    if (segments.length === 0 || segments.length > here.length) continue;
    if (segments.length === PORTAL_ROOT_SEGMENTS && here.length !== PORTAL_ROOT_SEGMENTS) continue;

    let literal = 0;
    let matches = true;
    for (let index = 0; index < segments.length; index += 1) {
      const segment = segments[index];
      if (segment?.startsWith(':')) continue;
      if (segment !== here[index]) {
        matches = false;
        break;
      }
      literal += 1;
    }
    if (!matches) continue;
    if (!entry.query.every(([key, value]) => params.get(key) === value)) continue;

    const score = segments.length * 1000 + literal * 10 + entry.query.length;
    if (!best || score > best.score) best = { ref: entry.ref, score };
  }

  return best?.ref ?? null;
}
