import type { EdgeKind } from './boardDataRestructure';

export type CardKind =
  | 'blank'
  | 'horseshoe'
  | 'robber'
  | 'topaz'
  | 'emerald'
  | 'ruby'
  | 'star';

type MoveCost =
  | { ok: true; steps: number; cost: number }
  | { ok: false; error: string };

/**
 * How far a player may travel this turn and what it costs them.
 *
 * Extracted so the typed-destination path and the natural-language path
 * (src/llm/intent.ts) share one copy -- the language model is allowed to choose
 * the travel mode, so without this the flight-300 / sea-100 / free-sail-2 rules
 * would exist in two places and drift.
 */
export function deriveMove(
  moveMode: EdgeKind,
  money: number,
  lastRoll: number | null,
): MoveCost {
  let steps: number;
  if (moveMode === 'flight') {
    steps = 1;
  } else if (moveMode === 'sea' && money < 100) {
    steps = 2;
  } else if (lastRoll === null) {
    return { ok: false, error: 'Roll the dice first.' };
  } else {
    steps = lastRoll;
  }

  const cost =
    moveMode === 'flight'
      ? 300
      : moveMode === 'sea' && money >= 100
        ? 100
        : 0;

  if (cost > 0 && money < cost) {
    return {
      ok: false,
      error: `You need at least ${cost} to travel by ${moveMode}.`,
    };
  }

  return { ok: true, steps, cost };
}

export const CARD_PAYOUT: Partial<Record<CardKind, number>> = {
  topaz: 300,
  emerald: 600,
  ruby: 1000,
};

const DECK_COUNTS: Record<CardKind, number> = {
  star: 1,
  ruby: 2,
  emerald: 3,
  topaz: 4,
  robber: 3,
  horseshoe: 5,
  blank: 12,
};

export function createDeck(
  cityIds: string[],
): Record<string, CardKind> {
  const cards: CardKind[] = [];
  for (const kind of Object.keys(
    DECK_COUNTS,
  ) as CardKind[]) {
    for (let i = 0; i < DECK_COUNTS[kind]; i++) {
      cards.push(kind);
    }
  }

  for (let i = cards.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [cards[i], cards[j]] = [cards[j], cards[i]];
  }

  const deck: Record<string, CardKind> = {};
  cityIds.forEach((cityId, index) => {
    deck[cityId] = cards[index];
  });
  return deck;
}

// The Tangier / Cairo equivalents on this board: players start here,
// and getting the star (or, once it's found, a horseshoe) back to
// either one wins the game.
export const HOME_CITY_IDS = ['keskustori', 'tammelan-tori'];

type SpecialEffect =
  | 'capetown'
  | 'goldCoast'
  | 'slaveCoast'
  | 'stHelena'
  | 'sahara';

export const SPECIAL_CITIES: Record<string, SpecialEffect> =
  {
    'yliopisto-hervannan-kampus': 'capetown',
    rantaperkio: 'goldCoast',
    perensaari: 'slaveCoast',
    viikinsaari: 'stHelena',
    finlayson: 'sahara',
  };

// Placeholder look for each cardboard piece on the board, until real
// artwork/gif animations are swapped in later.
export const CARD_DISPLAY: Record<
  CardKind,
  { label: string; color: string }
> = {
  star: { label: '★', color: '#ffffff' },
  ruby: { label: 'R', color: '#e0115f' },
  emerald: { label: 'E', color: '#50c878' },
  topaz: { label: 'T', color: '#ffc040' },
  horseshoe: { label: 'H', color: '#b0b0b0' },
  robber: { label: 'X', color: '#333333' },
  blank: { label: '', color: '#999999' },
};

export type PlayerStatus =
  | { type: 'waitingForCard'; cityId: string }
  | { type: 'captured'; effect: 'stHelena' | 'sahara' }
  | { type: 'slave'; turnsRemaining: number }
  | null;
