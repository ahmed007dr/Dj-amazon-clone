import type { DocSection, DocTopic } from './types';

/**
 * Guide search — Arabic-friendly, client side, over a few dozen topics.
 *
 * ⚠️  Filtering in the browser is right *here* (contrast `FilterBar`, which
 *     insists on the server): the whole guide is a static bundle of a few
 *     hundred kilobytes, there is no endpoint to ask, and nothing grows with data.
 *
 * ⚠️  **Both sides are folded before comparing.** People type "اضافه منتج",
 *     "إضافة منتج" and "اضافة منتج" for the same thing, with or without the
 *     diacritics, and copy-pasted text arrives with tatweel and presentation
 *     forms. Matching on the raw characters makes the guide look like it does
 *     not contain what is plainly written in it.
 */

/** Where a hit came from — also the order of relevance (title first). */
export type DocField = 'title' | 'summary' | 'benefits' | 'steps' | 'problems' | 'tips';

const WEIGHT: Record<DocField, number> = {
  title: 12,
  summary: 6,
  benefits: 4,
  steps: 4,
  problems: 4,
  tips: 2,
};

// ── Normalisation ───────────────────────────────────────────

/** Harakat, dagger alef, Quranic marks, and tatweel — decoration, never meaning. */
const DECORATION = /[ً-ٰٟۖ-ۭـ]/;

const FOLD: Readonly<Record<string, string>> = {
  // alef with hamza / madda / wasla → bare alef
  'أ': 'ا',
  'إ': 'ا',
  'آ': 'ا',
  'ٱ': 'ا',
  // alef maqsura and the Persian yeh → yeh
  'ى': 'ي',
  'ی': 'ي',
  // hamza carriers → their seat letter ("رسائل" = "رسايل")
  'ئ': 'ي',
  'ؤ': 'و',
  // teh marbuta → heh ("مدرسة" = "مدرسه"): the most common typing variation
  'ة': 'ه',
  // Persian kaf → Arabic kaf
  'ک': 'ك',
};

function foldDigit(ch: string): string {
  const code = ch.charCodeAt(0);
  // Arabic-Indic (٠-٩) and Persian (۰-۹) digits → ASCII, so "٣" finds "3".
  if (code >= 0x0660 && code <= 0x0669) return String(code - 0x0660);
  if (code >= 0x06f0 && code <= 0x06f9) return String(code - 0x06f0);
  return ch;
}

/** A normalised string, with each of its characters mapped back to the source index. */
export interface Normalized {
  text: string;
  /** `map[i]` = index in the source string of normalised character `i`. */
  map: number[];
}

export function normalizeWithMap(source: string): Normalized {
  let text = '';
  const map: number[] = [];

  for (let index = 0; index < source.length; index += 1) {
    // `*` is the bold marker — never part of what anyone searches for.
    const raw = source.charAt(index);
    if (raw === '*') continue;

    // ⚠️  Per character on purpose: one source character may expand (ﻻ → لا),
    //     and the map is what lets a hit be highlighted in the *original* text.
    for (const ch of raw.normalize('NFKC').toLowerCase()) {
      if (DECORATION.test(ch)) continue;
      text += foldDigit(FOLD[ch] ?? ch);
      map.push(index);
    }
  }

  return { text, map };
}

export function normalize(source: string): string {
  return normalizeWithMap(source).text;
}

// ── Highlighting ────────────────────────────────────────────

export interface Segment {
  text: string;
  mark: boolean;
}

type Range = readonly [start: number, end: number];

/** Every occurrence of every token, as merged ranges in the *source* string. */
function findRanges(norm: Normalized, tokens: readonly string[]): Range[] {
  const found: [number, number][] = [];

  for (const token of tokens) {
    let from = norm.text.indexOf(token);
    while (from !== -1) {
      const first = norm.map[from];
      const last = norm.map[from + token.length - 1];
      if (first !== undefined && last !== undefined) found.push([first, last + 1]);
      from = norm.text.indexOf(token, from + token.length);
    }
  }

  found.sort((a, b) => a[0] - b[0]);

  const merged: [number, number][] = [];
  for (const [start, end] of found) {
    const previous = merged[merged.length - 1];
    if (previous && start <= previous[1]) previous[1] = Math.max(previous[1], end);
    else merged.push([start, end]);
  }
  return merged;
}

/** Cut `plain[from, to)` into marked / unmarked runs. */
function toSegments(plain: string, ranges: readonly Range[], from: number, to: number): Segment[] {
  const segments: Segment[] = [];
  let cursor = from;

  for (const [start, end] of ranges) {
    const clippedStart = Math.max(start, from);
    const clippedEnd = Math.min(end, to);
    if (clippedEnd <= clippedStart) continue;
    if (clippedStart > cursor) segments.push({ text: plain.slice(cursor, clippedStart), mark: false });
    segments.push({ text: plain.slice(clippedStart, clippedEnd), mark: true });
    cursor = clippedEnd;
  }
  if (cursor < to) segments.push({ text: plain.slice(cursor, to), mark: false });
  return segments;
}

/** Characters of context kept before the first hit, and the most a snippet shows. */
const LEAD = 40;
const SNIPPET_MAX = 170;

// ── Index ───────────────────────────────────────────────────

interface IndexedField {
  field: DocField;
  /** The text as the reader sees it — `**` markers removed. */
  plain: string;
  norm: Normalized;
}

export interface IndexedTopic {
  section: DocSection;
  topic: DocTopic;
  fields: IndexedField[];
  /** Every field, normalised and joined — what "does this topic contain every word" asks. */
  haystack: string;
}

function stripMarkup(text: string): string {
  return text.replace(/\*\*/g, '');
}

function indexTopic(section: DocSection, topic: DocTopic): IndexedTopic {
  const fields: IndexedField[] = [];
  const add = (field: DocField, text: string | undefined) => {
    if (!text) return;
    const plain = stripMarkup(text);
    fields.push({ field, plain, norm: normalizeWithMap(plain) });
  };

  add('title', topic.title);
  add('summary', topic.summary);
  for (const benefit of topic.benefits) add('benefits', benefit);
  for (const step of topic.steps) {
    add('steps', step.title);
    add('steps', step.detail);
  }
  for (const tip of topic.tips ?? []) add('tips', tip);
  for (const problem of topic.problems) {
    add('problems', problem.problem);
    add('problems', problem.cause);
    add('problems', problem.solution);
  }

  return { section, topic, fields, haystack: fields.map((entry) => entry.norm.text).join('\n') };
}

export function buildIndex(sections: readonly DocSection[]): IndexedTopic[] {
  return sections.flatMap((section) => section.topics.map((topic) => indexTopic(section, topic)));
}

// ── Search ──────────────────────────────────────────────────

export interface SearchHit {
  section: DocSection;
  topic: DocTopic;
  score: number;
  /** The title, with the matched words marked. */
  title: Segment[];
  /** The best matching passage outside the title, or `null` when only the title matched. */
  snippet: { field: DocField; segments: Segment[]; before: boolean; after: boolean } | null;
}

/** A query's words, normalised. Empty when the query holds nothing searchable. */
export function tokenize(query: string): string[] {
  return normalize(query)
    .split(/\s+/)
    .filter((token) => token.length > 0);
}

export function searchTopics(index: readonly IndexedTopic[], query: string): SearchHit[] {
  const tokens = tokenize(query);
  if (tokens.length === 0) return [];

  const hits: SearchHit[] = [];

  for (const entry of index) {
    // Every word must appear somewhere in the topic — AND, not OR.
    if (!tokens.every((token) => entry.haystack.includes(token))) continue;

    let score = 0;
    for (const token of tokens) {
      let best = 0;
      for (const field of entry.fields) {
        if (field.norm.text.includes(token)) best = Math.max(best, WEIGHT[field.field]);
      }
      score += best;
    }

    const titleField = entry.fields.find((field) => field.field === 'title');
    const phrase = tokens.join(' ');
    // The whole query inside the title outranks the same words scattered about.
    if (titleField?.norm.text.includes(phrase)) score += 10;

    const title = titleField
      ? toSegments(titleField.plain, findRanges(titleField.norm, tokens), 0, titleField.plain.length)
      : [{ text: entry.topic.title, mark: false }];

    // The passage with the most distinct query words (ties: the more relevant field).
    let bestField: IndexedField | null = null;
    let bestCount = 0;
    for (const field of entry.fields) {
      if (field.field === 'title') continue;
      const count = tokens.filter((token) => field.norm.text.includes(token)).length;
      if (count === 0) continue;
      if (
        count > bestCount ||
        (count === bestCount && bestField !== null && WEIGHT[field.field] > WEIGHT[bestField.field])
      ) {
        bestField = field;
        bestCount = count;
      }
    }

    let snippet: SearchHit['snippet'] = null;
    if (bestField) {
      const ranges = findRanges(bestField.norm, tokens);
      const firstHit = ranges[0]?.[0] ?? 0;
      let from = Math.max(0, firstHit - LEAD);
      // Start on a word boundary rather than mid-word.
      if (from > 0) {
        const space = bestField.plain.indexOf(' ', from);
        if (space !== -1 && space < firstHit) from = space + 1;
      }
      const to = Math.min(bestField.plain.length, from + SNIPPET_MAX);
      snippet = {
        field: bestField.field,
        segments: toSegments(bestField.plain, ranges, from, to),
        before: from > 0,
        after: to < bestField.plain.length,
      };
    }

    hits.push({ section: entry.section, topic: entry.topic, score, title, snippet });
  }

  // `sort` is stable, so equal scores keep the guide's own reading order.
  return hits.sort((a, b) => b.score - a.score);
}
