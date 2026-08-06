// Verification entry for the pure (non-network) logic, run with `npm run probe`
// -- rolldown bundles it and node executes it against the real board data.
//
// Not imported by the app, so it never reaches the browser bundle; `tsc -b`
// still type-checks it. This is the repo's only automated check, so prefer
// adding cases here over verifying by hand.
import { findMoves } from '../game/FindMoves';
import { deriveMove } from '../game/rules';
import {
  adjacency,
  spaceById,
} from '../game/boardDataRestructure';
import { chooseDestination, distancesFrom } from './heading';
import { matchCityName } from './names';
import { cityIds } from './prompt';

let failures = 0;
function check(label: string, got: unknown, want: unknown) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log(
    `${ok ? 'ok  ' : 'FAIL'} ${label}\n       got ${JSON.stringify(got)}${ok ? '' : `\n       want ${JSON.stringify(want)}`}`,
  );
}

console.log(`board: ${cityIds.length} cities`);

// --- matchCityName: the deterministic override -------------------------------
// the near-twins the model confuses: these must resolve exactly
check('near-twin "Tampere talo"', matchCityName('go to Tampere talo'), 'tampere-talo');
check('near-twin "Tammelan tori"', matchCityName('heading for Tammelan tori'), 'tammelan-tori');
check('near-twin "Tammerkoski"', matchCityName('toward Tammerkoski'), 'tammerkoski');
check('near-twin Hervanta campus', matchCityName('to the Yliopisto - Hervannan kampus'), 'yliopisto-hervannan-kampus');
check('near-twin Hervanta water tower', matchCityName('to Hervannan vesitorni'), 'hervannan-vesitorni');
check('diacritic-insensitive "Hakametsa"', matchCityName('toward Hakametsa'), 'hakametsa');
check('diacritics present "Hakametsä"', matchCityName('toward Hakametsä'), 'hakametsa');
check('id spelling accepted', matchCityName('go to yliopisto-hervannan-kampus'), 'yliopisto-hervannan-kampus');
check('no city mentioned', matchCityName('the weather is nice'), null);
check('two cities = ambiguous', matchCityName('from Ratina to Turtola'), null);

// --- deriveMove: shared steps/cost rules -------------------------------------
check('land uses the roll, free', deriveMove('land', 300, 4), { ok: true, steps: 4, cost: 0 });
check('land with no roll', deriveMove('land', 300, null), { ok: false, error: 'Roll the dice first.' });
check('flight is 1 step for 300', deriveMove('flight', 300, null), { ok: true, steps: 1, cost: 300 });
check('flight unaffordable', deriveMove('flight', 299, 5), { ok: false, error: 'You need at least 300 to travel by flight.' });
check('sea with money uses roll for 100', deriveMove('sea', 100, 3), { ok: true, steps: 3, cost: 100 });
check('sea when broke sails 2 free', deriveMove('sea', 99, null), { ok: true, steps: 2, cost: 0 });

// --- heading chooser ---------------------------------------------------------
// Asserted as properties rather than against specific square ids: the board gets
// regenerated (board.json -> board2.json already happened once), and hardcoded
// waypoint names would fail for reasons that have nothing to do with this logic.
check('distance to self is 0', distancesFrom('hakametsa', ['land']).get('hakametsa'), 0);

function pick(from: string, steps: number, kind: 'land' | 'sea', heading: string) {
  const cands = [...findMoves(from, steps, [kind]).keys()];
  const chosen = chooseDestination(cands, heading, [kind]);
  const dist = distancesFrom(heading, [kind]);
  return { chosen, after: chosen === null ? null : dist.get(chosen) };
}

// 1. A bigger roll must never leave you further from where you're heading.
let regressions = 0;
for (const from of cityIds) {
  for (const heading of cityIds) {
    if (from === heading) continue;
    let prev = Number.POSITIVE_INFINITY;
    for (const steps of [1, 2, 3, 4, 5, 6]) {
      const { after } = pick(from, steps, 'land', heading);
      if (after === null || after === undefined) continue;
      if (after > prev) regressions++;
      prev = after;
    }
  }
}
check('a bigger roll never ends further away (all city pairs)', regressions, 0);

// 2. Naming a city you can actually reach this turn must land on it exactly.
let missedExact = 0;
let exactCases = 0;
for (const from of cityIds) {
  for (const steps of [1, 2, 3, 4, 5, 6]) {
    const cands = [...findMoves(from, steps, ['land']).keys()];
    for (const target of cands.filter(id => spaceById[id]?.kind === 'city')) {
      exactCases++;
      if (chooseDestination(cands, target, ['land']) !== target) missedExact++;
    }
  }
}
check(`reachable named city is landed on exactly (${exactCases} cases)`, missedExact, 0);

// 3. A heading with no route by that mode yields no move, rather than a wrong one.
const strandedByLand = cityIds.filter(
  id => distancesFrom(id, ['land']).size === 1,
);
check(
  `heading somewhere unreachable by that mode returns null (${strandedByLand.length} land-isolated cities)`,
  strandedByLand.every(
    id => pick('keskustori', 3, 'land', id).chosen === null,
  ),
  true,
);

// --- paths -------------------------------------------------------------------
// Stopping at a city passed on the way (to look at its card) and then walking
// off the rest of the roll depends entirely on findMoves' path being a real,
// contiguous route -- so check that rather than trusting it.
let badStart = 0;
let badEnd = 0;
let badLength = 0;
let disconnected = 0;
let pathCount = 0;
for (const from of cityIds) {
  for (const kind of ['land', 'sea'] as const) {
    for (const steps of [1, 2, 3, 4, 5, 6]) {
      for (const [dest, path] of findMoves(from, steps, [kind])) {
        pathCount++;
        if (path[0] !== from) badStart++;
        if (path[path.length - 1] !== dest) badEnd++;
        // A path may be shorter than the roll (you're allowed to stop early at
        // a city) but never longer than it.
        if (path.length - 1 > steps) badLength++;
        for (let i = 0; i < path.length - 1; i++) {
          const linked = (adjacency[path[i]] ?? []).some(
            c => c.to === path[i + 1] && c.kind === kind,
          );
          if (!linked) disconnected++;
        }
      }
    }
  }
}
check(`every path starts at the origin (${pathCount} paths)`, badStart, 0);
check('every path ends at its destination', badEnd, 0);
check('no path is longer than the roll allows', badLength, 0);
check('every step of every path follows a real edge of that mode', disconnected, 0);

// A path that stops early must be stopping at a city -- that's the only reason
// findMoves is allowed to end a route before the roll is spent.
let earlyNonCity = 0;
for (const from of cityIds) {
  for (const steps of [2, 4, 6]) {
    for (const [dest, path] of findMoves(from, steps, ['land'])) {
      if (path.length - 1 < steps && spaceById[dest]?.kind !== 'city') {
        earlyNonCity++;
      }
    }
  }
}
check('a route only ends early on a city', earlyNonCity, 0);

// every chosen square must actually be a legal landing square
let illegal = 0;
for (const from of cityIds) {
  for (const steps of [1, 2, 3, 4, 5, 6]) {
    const cands = new Set(findMoves(from, steps, ['land']).keys());
    for (const heading of cityIds) {
      const chosen = chooseDestination([...cands], heading, ['land']);
      if (chosen !== null && !cands.has(chosen)) illegal++;
    }
  }
}
check('chooseDestination never returns an illegal square (all city x roll x heading)', illegal, 0);

// spaceById must cover everything findMoves can return
let unknown = 0;
for (const from of cityIds) {
  for (const kind of ['land', 'sea', 'flight'] as const) {
    for (const id of findMoves(from, 3, [kind]).keys()) {
      if (!spaceById[id]) unknown++;
    }
  }
}
check('all candidates exist in spaceById', unknown, 0);

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILURE(S)`);
