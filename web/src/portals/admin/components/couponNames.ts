/** Splits the textarea into names: one per line, blanks dropped, spaces collapsed. */
export function parseNames(raw: string): string[] {
  return raw
    .split(/\r?\n/)
    .map((line) => line.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
}

/** The first name that appears twice (case-insensitively), or null. */
export function firstDuplicate(names: string[]): string | null {
  const seen = new Set<string>();
  for (const name of names) {
    const key = name.toLocaleLowerCase();
    if (seen.has(key)) return name;
    seen.add(key);
  }
  return null;
}
