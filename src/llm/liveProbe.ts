// End-to-end check of the REAL client path against a running llama-server:
// resolveMoveIntent -> client.ts fetch -> schema/grammar -> validation ->
// findMoves -> chooseDestination. Run with `npm run probe:live` (needs
// `npm run llm` up first).
//
// Separate from probe.ts because that one is pure and instant; this one costs
// ~10s per case on real hardware.
import { spaceById } from '../game/boardDataRestructure';
import { resolveMoveIntent } from './intent';

type Case = {
  transcript: string;
  uiMode: 'land' | 'sea' | 'flight';
  lastRoll: number | null;
  expect: 'move' | 'unclear';
  /** For a move: the city the player named, which we must end up closer to. */
  heading?: string;
};

const START = 'keskustori';
const CASES: Case[] = [
  { transcript: 'heading for Hakametsä', uiMode: 'land', lastRoll: 3, expect: 'move', heading: 'hakametsa' },
  { transcript: 'fly toward Turtola', uiMode: 'land', lastRoll: null, expect: 'move', heading: 'turtola' },
  { transcript: 'go to Tampere talo', uiMode: 'land', lastRoll: 4, expect: 'move', heading: 'tampere-talo' },
  { transcript: 'we walk toward Laukontori', uiMode: 'sea', lastRoll: 6, expect: 'move', heading: 'laukontori' },
  { transcript: 'the weather is nice today', uiMode: 'land', lastRoll: 3, expect: 'unclear' },
  { transcript: 'heading for Nairobi', uiMode: 'land', lastRoll: 3, expect: 'unclear' },
  // land with no roll must be refused by deriveMove before any move is applied
  { transcript: 'heading for Hakametsä', uiMode: 'land', lastRoll: null, expect: 'unclear' },
];

let failures = 0;

for (const c of CASES) {
  const started = Date.now();
  const result = await resolveMoveIntent({
    transcript: c.transcript,
    currentPlaceId: START,
    money: 300,
    lastRoll: c.lastRoll,
    uiMode: c.uiMode,
  });
  const secs = ((Date.now() - started) / 1000).toFixed(1);

  let ok = result.kind === c.expect;
  let detail: string;
  if (result.kind === 'move') {
    const legal = Boolean(spaceById[result.destinationId]);
    if (!legal) ok = false;
    detail = `-> ${result.destinationId} (${result.mode}, cost ${result.cost})`;
  } else {
    detail = `-> unclear: ${result.message}`;
  }

  if (!ok) failures++;
  console.log(
    `${ok ? 'ok  ' : 'FAIL'} [${secs}s] ${JSON.stringify(c.transcript)} ` +
      `roll=${c.lastRoll} ui=${c.uiMode} ${detail}`,
  );
}

console.log(
  failures === 0
    ? `\nALL PASS (${CASES.length} live cases)`
    : `\n${failures} FAILURE(S)`,
);
