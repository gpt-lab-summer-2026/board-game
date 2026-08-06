import { cities } from './prompt';

/** Lowercase and strip diacritics, so "Hakametsa" matches "Hakametsä". */
function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFKD')
    .replace(/\p{M}/gu, '');
}

// Every spelling of a city we're willing to recognise verbatim -> its id.
// Both the display name (what players say) and the id (what a player might
// type) are included; verified that no normalised name is a substring of
// another, and that no id collides with a different city's name, so a hit here
// is unambiguous.
const bySpelling = new Map<string, string>();
for (const city of cities) {
  bySpelling.set(normalize(city.id), city.id);
  if (city.name) bySpelling.set(normalize(city.name), city.id);
}

/**
 * The city whose name or id appears verbatim in `transcript`, if exactly one does.
 *
 * This exists because a 4B model loses to lexical similarity on the board's one
 * irregular row: id "Tammelan tori" carries the name "Tampere talo", and the
 * model picks the lexically-closer but wrong "tammela" every time -- even given
 * an explicit worked example and a paragraph explaining the quirk. An exact
 * substring match is strictly stronger evidence than the model's guess, so where
 * one exists it wins.
 *
 * Returns null when nothing matches, or when two different cities are mentioned
 * (genuinely ambiguous -- let the model weigh the sentence).
 */
export function matchCityName(
  transcript: string,
): string | null {
  const haystack = normalize(transcript);
  const hits = new Set<string>();
  for (const [spelling, id] of bySpelling) {
    if (haystack.includes(spelling)) hits.add(id);
  }
  return hits.size === 1
    ? (hits.values().next().value as string)
    : null;
}
