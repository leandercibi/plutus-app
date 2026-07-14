// Angel One's script master includes a handful of non-tradable *NSETEST placeholder
// symbols — exclude them from search everywhere we offer a symbol picker.
const JUNK_SUBSTRING = 'NSETEST'

/** Rank symbols for a typeahead: prefix matches first (alphabetical), then
 * contains-matches (alphabetical), junk test symbols excluded. */
export function searchSymbols(symbols: string[], query: string, limit = 30): string[] {
  const q = query.trim().toUpperCase()
  if (!q) return []

  const starts: string[] = []
  const contains: string[] = []
  for (const s of symbols) {
    if (s.includes(JUNK_SUBSTRING)) continue
    if (s.startsWith(q)) starts.push(s)
    else if (s.includes(q)) contains.push(s)
  }
  starts.sort()
  contains.sort()
  return [...starts, ...contains].slice(0, limit)
}
