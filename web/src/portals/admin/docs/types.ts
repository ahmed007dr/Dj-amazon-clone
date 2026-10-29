/**
 * The in-app user guide — content model.
 *
 * ⚠️  Content is Arabic, written for the people who *operate* the store (owner,
 *     admin, cashier, sales rep, customer) — not for developers. The developer
 *     docs live in `/docs` at the repo root; this is a different audience.
 *
 * ⚠️  Strings are plain text, with one inline marker: `**text**` renders bold.
 *     Use it for the exact on-screen label of a button / tab / field
 *     (e.g. `اضغط **إضافة منتج**`) so the reader can find it by eye.
 *     No HTML, no markdown links — cross-references go through `related`.
 *
 * ⚠️  Every claim must be grounded in the real screen (its component, its i18n
 *     labels in `shared/i18n/locales/ar.json`, its server permission). A guide
 *     that describes a button that does not exist is worse than no guide.
 */

/** One numbered step of a how-to. */
export interface DocStep {
  /** The action, one sentence: "افتح **المنتجات** من القائمة الجانبية". */
  title: string;
  /** Optional extra detail: what to type, what happens next, a caveat. */
  detail?: string;
}

/** A symptom the operator can hit, and how to get out of it. */
export interface DocProblem {
  /** What the person sees / complains about, in their words. */
  problem: string;
  /** Why it happens (omit when there is nothing useful to say). */
  cause?: string;
  /** What to do about it. */
  solution: string;
}

/** One screen or one feature — the unit that gets a page-section and a search hit. */
export interface DocTopic {
  /** Stable slug, unique across the whole guide — used in the URL hash. */
  id: string;
  /** Arabic title, normally the screen name as it appears in the sidebar. */
  title: string;
  /** One or two sentences: what it is and who it is for. */
  summary: string;
  /** The app route this topic documents (e.g. `/admin/products`) — enables "open this screen" and the contextual help link. */
  path?: string;
  /** Django permission the server checks for it, if any (informational). */
  permission?: string;
  /** الفائدة والمزايا — why it exists, what it gives the business. Concrete, not marketing. */
  benefits: string[];
  /** كيفية الاستخدام — ordered steps for the main job(s). */
  steps: DocStep[];
  /** Short practical advice and things worth knowing. */
  tips?: string[];
  /** حل المشاكل — real symptoms with cause and fix. At least two per topic. */
  problems: DocProblem[];
  /** Ids of other topics worth reading next. */
  related?: string[];
}

/** A group of topics shown together in the guide's side navigation. */
export interface DocSection {
  /** Stable slug — used in the URL (`/admin/docs/<section id>`). */
  id: string;
  title: string;
  /** One sentence under the section title. */
  description: string;
  /** A single emoji used as the section's icon. */
  icon: string;
  topics: DocTopic[];
}
