import { spaces } from '../game/boardDataRestructure';
import type { EdgeKind } from '../game/boardDataRestructure';

/** The 32 city spaces, in board.json order. */
export const cities = spaces.filter(
  space => space.kind === 'city',
);

export const cityIds: readonly string[] = cities.map(
  city => city.id,
);

// `id` is what findMoves/spaceById key on; `name` is what a player actually
// says. All 32 differ (diacritics folded, spaces hyphenated: hakametsa /
// Hakametsä), so the model needs both columns to map speech onto an id.
//
// One row is genuinely odd rather than merely slugged: id 'Tammelan tori'
// carries name 'Tampere talo' -- an unrelated place, and a separate city
// 'tammela' / 'Tammela' also exists. It's a HOME_CITY_ID, so it's listed
// verbatim rather than "corrected" here.
const cityTable = cities
  .map(city => `${city.id} = ${city.name}`)
  .join('\n');

/**
 * Fixed for every request, so it sits in llama-server's reusable prompt prefix
 * (see scripts/llama-server.sh on why --swa-full is what makes that reuse
 * actually happen). Anything that varies per turn belongs in the user block.
 */
export const SYSTEM_PROMPT = `You read a board-game player's spoken move and \
extract two things: which city they are heading toward, and how they intend to \
travel. You do not decide whether the move is legal -- the game engine does \
that. Never invent a place that is not in the list below.

The player names a place they are heading TOWARD. They will usually not reach \
it this turn; that is fine and expected. Report the city they named.

Cities (use the left-hand id in your answer, the right-hand name is what \
players say):
${cityTable}

Travel modes:
land = walking, roads, driving
sea = boat, ship, sailing, ferry, by water
flight = plane, flying, by air
not_stated = the player did not say how they are travelling

Report mode only from the player's own words. If they did not say how they are \
travelling, you must answer "not_stated" -- do not assume land, and do not copy \
the mode currently selected in the UI. Guessing here can spend the player's \
money on a boat or a plane they never asked for.

Set action to "move" and fill in heading and mode. If they named no place, or \
named something that isn't in the list, or the words aren't a move at all, set \
action to "unclear" and give the matching unclear_reason instead of guessing.

Match the place the player actually said, letter by letter. Several names start \
alike or share a word -- Turtola and Tammelan tori and Tammela are three \
different places, and so are Hervannan vesitorni and Yliopisto - Hervannan \
kampus. Pick the one whose name matches what they said, not merely a name that \
begins the same way.

One row of the table is genuinely irregular rather than just spelled \
differently: the id "Tammelan tori" carries the name "Tampere talo". A player \
saying "Tampere talo" means that row -- not the separate city "tammela" \
("Tammela"), which is a different place.

Examples:
"fly toward Turtola" -> {"action":"move","heading":"turtola","mode":"flight"}
"heading for Tammela" -> {"action":"move","heading":"tammela","mode":"not_stated"}
"go to Tampere talo" -> {"action":"move","heading":"Tammelan tori","mode":"not_stated"}
"sail to the Hervanta campus" -> {"action":"move","heading":"yliopisto-hervannan-kampus","mode":"sea"}
"toward the water tower in Hervanta" -> {"action":"move","heading":"hervannan-vesitorni","mode":"not_stated"}
"heading for Nairobi" -> {"action":"unclear","heading":"","mode":"not_stated","unclear_reason":"no_heading"}
"whose turn is it" -> {"action":"unclear","heading":"","mode":"not_stated","unclear_reason":"not_a_move"}

Answer with only the JSON object, formatted exactly like those examples: one \
line, no line breaks, no indentation, no spaces after the colons. Every token \
you generate costs about a third of a second on this machine.`;

export function buildUserBlock(args: {
  transcript: string;
  currentCityLabel: string;
  uiMode: EdgeKind;
  lastRoll: number | null;
}): string {
  const roll =
    args.lastRoll === null
      ? 'not rolled yet'
      : String(args.lastRoll);
  return [
    `Player is currently at: ${args.currentCityLabel}`,
    `Mode currently selected in the UI: ${args.uiMode}`,
    `Dice roll: ${roll}`,
    `Player said: "${args.transcript}"`,
  ].join('\n');
}
