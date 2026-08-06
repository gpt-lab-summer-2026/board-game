// Verification entry for the pure (non-network) logic, run with `npm run probe`
// -- rolldown bundles it and node executes it against the real board data.
//
// Not imported by the app, so it never reaches the browser bundle; `tsc -b`
// still type-checks it. This is the repo's only automated check, so prefer
// adding cases here over verifying by hand.
import { findMoves } from '../game/FindMoves';
import { deriveMove } from '../game/rules';
import { spaceById } from '../game/boardDataRestructure';
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
check('exact name "go to Tampere talo"', matchCityName('go to Tampere talo'), 'Tammelan tori');
check('exact name "heading for Tammela"', matchCityName('heading for Tammela'), 'tammela');
check('diacritic-insensitive "Hakametsa"', matchCityName('toward Hakametsa'), 'hakametsa');
check('diacritics present "Hakametsä"', matchCityName('toward Hakametsä'), 'hakametsa');
check('id spelling accepted', matchCityName('go to yliopisto-hervannan-kampus'), 'yliopisto-hervannan-kampus');
check('no city mentioned', matchCityName('the weather is nice'), null);
check('two cities = ambiguous', matchCityName('from Tammela to Turtola'), null);

// --- deriveMove: shared steps/cost rules -------------------------------------
check('land uses the roll, free', deriveMove('land', 300, 4), { ok: true, steps: 4, cost: 0 });
check('land with no roll', deriveMove('land', 300, null), { ok: false, error: 'Roll the dice first.' });
check('flight is 1 step for 300', deriveMove('flight', 300, null), { ok: true, steps: 1, cost: 300 });
check('flight unaffordable', deriveMove('flight', 299, 5), { ok: false, error: 'You need at least 300 to travel by flight.' });
check('sea with money uses roll for 100', deriveMove('sea', 100, 3), { ok: true, steps: 3, cost: 100 });
check('sea when broke sails 2 free', deriveMove('sea', 99, null), { ok: true, steps: 2, cost: 0 });

// --- heading chooser ---------------------------------------------------------
const d = distancesFrom('hakametsa', ['land']);
check('distance to self is 0', d.get('hakametsa'), 0);
check('viikinsaari unreachable by land', d.get('viikinsaari'), undefined);

function pick(from: string, steps: number, kind: 'land' | 'sea', heading: string) {
  const cands = [...findMoves(from, steps, [kind]).keys()];
  const chosen = chooseDestination(cands, heading, [kind]);
  const dist = distancesFrom(heading, [kind]);
  return { chosen, before: dist.get(from), after: chosen ? dist.get(chosen) : null };
}
// progress must scale with the roll, and land exactly on a reachable named city
check('roll 1 toward hakametsa', pick('keskustori', 1, 'land', 'hakametsa'), { chosen: 's84', before: 17, after: 16 });
check('roll 3 toward hakametsa', pick('keskustori', 3, 'land', 'hakametsa'), { chosen: 's82', before: 17, after: 14 });
check('roll 3 toward laukontori lands on it', pick('keskustori', 3, 'land', 'laukontori'), { chosen: 'laukontori', before: 2, after: 0 });
check('roll 6 toward finlayson lands on it', pick('keskustori', 6, 'land', 'finlayson'), { chosen: 'finlayson', before: 5, after: 0 });
check('island unreachable on foot', pick('keskustori', 1, 'land', 'viikinsaari'), { chosen: null, before: undefined, after: null });

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
