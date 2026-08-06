export type CardKind =
  | 'blank'
  | 'horseshoe'
  | 'robber'
  | 'topaz'
  | 'emerald'
  | 'ruby'
  | 'star';

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
export const HOME_CITY_IDS = ['keskustori', 'Tammelan tori'];

export type SpecialEffect =
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
