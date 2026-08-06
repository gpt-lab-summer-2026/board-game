import {
  useRef,
  useState,
  type ChangeEvent,
} from 'react';
import './App.css';
import Board from './game/board';
import RollDice from './game/RollDice';
import GameStats, {
  type GameState,
} from './game/GameStats';
import { library } from '@fortawesome/fontawesome-svg-core';
import { fas } from '@fortawesome/free-solid-svg-icons';
library.add(fas);
import { findMoves } from './game/FindMoves';
import {
  spaceById,
  spaces,
} from './game/boardDataRestructure';
import type { EdgeKind } from './game/boardDataRestructure';
import {
  createDeck,
  deriveMove,
  CARD_PAYOUT,
  HOME_CITY_IDS,
  SPECIAL_CITIES,
  type CardKind,
  type PlayerStatus,
} from './game/rules';
import { resolveMoveIntent } from './llm/intent';

export type Player = {
  id: string;
  name: string;
  placeId: string;
  pieceColor: string;
  money: number;
  inventory: Record<string, number>;
  status: PlayerStatus;
};

const PIECE_COLORS = [
  '#e6194b',
  '#3cb44b',
  '#4363d8',
  '#f58231',
  '#911eb4',
];

function createPlayers(names: string[]): Player[] {
  return names.map((name, index) => ({
    id: `player-${index + 1}`,
    name,
    placeId: HOME_CITY_IDS[index % HOME_CITY_IDS.length],
    pieceColor: PIECE_COLORS[index % PIECE_COLORS.length],
    money: 300,
    inventory: {
      empty: 0,
      horseshoe: 0,
      robber: 0,
      topaz: 0,
      emerald: 0,
      ruby: 0,
      africaStar: 0,
    },
    status: null,
  }));
}

function dealCards(): Record<string, CardKind> {
  const cityIds = spaces
    .filter(space => space.kind === 'city')
    .map(space => space.id)
    .filter(id => !HOME_CITY_IDS.includes(id));
  return createDeck(cityIds);
}

function App() {
  const [players, setPlayers] = useState<Player[]>([]);
  const [turnIndex, setTurnIndex] = useState(0);
  const currentPlayer = players[turnIndex];

  const [moveMode, setMoveMode] =
    useState<EdgeKind>('land');
  const [lastRoll, setLastRoll] = useState<number | null>(
    null,
  );
  const [text, setText] = useState('');
  const [moveError, setMoveError] = useState<string | null>(
    null,
  );
  const [infoMessage, setInfoMessage] = useState<
    string | null
  >(null);
  const [gameState, setGameState] =
    useState<GameState>('notStarted');

  // Natural-language move input. `llmPending` is what keeps the async path safe:
  // applyArrival and friends read players/cards/starFound from the render
  // closure, so resolving a move after an await would otherwise write back a
  // stale snapshot. Rather than detect that afterwards, every control that could
  // change the relevant state is inert while a request is in flight -- so the
  // closure is still current when it resolves. Nothing else mutates state (no
  // effects, no timers beyond RollDice's cosmetic delay).
  const [nlText, setNlText] = useState('');
  const [llmPending, setLlmPending] = useState(false);
  const [llmMessage, setLlmMessage] = useState<
    string | null
  >(null);
  const llmAbort = useRef<AbortController | null>(null);

  const [cards, setCards] = useState<
    Record<string, CardKind>
  >({});
  const [pendingCard, setPendingCard] = useState<{
    cityId: string;
  } | null>(null);
  const [capetownAwarded, setCapetownAwarded] =
    useState(false);
  const [starFound, setStarFound] = useState(false);
  const [winner, setWinner] = useState<Player | null>(null);

  const advanceTurn = () => {
    setTurnIndex(index => (index + 1) % players.length);
  };

  const removeCard = (cityId: string) => {
    setCards(prev => {
      const next = { ...prev };
      delete next[cityId];
      return next;
    });
  };

  const applyCardEffect = (
    player: Player,
    kind: CardKind,
    cityId: string,
  ): { player: Player; message: string } => {
    const isGoldCoast =
      SPECIAL_CITIES[cityId] === 'goldCoast';
    const inventory = { ...player.inventory };
    let money = player.money;
    let status = player.status;
    let message = '';

    switch (kind) {
      case 'blank':
        inventory.empty += 1;
        message = 'It was an empty piece.';
        if (SPECIAL_CITIES[cityId] === 'slaveCoast') {
          status = { type: 'slave', turnsRemaining: 3 };
          message +=
            ' Enslaved at the Slave Coast for 3 turns!';
        }
        break;
      case 'horseshoe':
        if (starFound) {
          inventory.horseshoe += 1;
          message =
            'A horseshoe! The star has already been found, so you can still win by racing this home.';
        } else {
          message =
            'A horseshoe, but no one has found the star yet, so it goes back in the box.';
        }
        break;
      case 'robber':
        inventory.robber += 1;
        money = 0;
        message = 'A robber! You lost all your money.';
        break;
      case 'topaz':
      case 'emerald':
      case 'ruby': {
        const payout =
          (CARD_PAYOUT[kind] ?? 0) * (isGoldCoast ? 2 : 1);
        money += payout;
        inventory[kind] += 1;
        message = `A ${kind}! +${payout}${isGoldCoast ? ' (doubled at the Gold Coast!)' : ''}`;
        break;
      }
      case 'star':
        inventory.africaStar += 1;
        setStarFound(true);
        message =
          'The Afrikan tähti! Get it to a home city to win.';
        break;
    }

    return {
      player: { ...player, money, inventory, status },
      message,
    };
  };

  const applyArrival = (
    destinationId: string,
    cost: number,
  ) => {
    let money = currentPlayer.money - cost;
    let status: PlayerStatus = null;
    let capetownMessage: string | null = null;
    let nextCapetownAwarded = capetownAwarded;

    if (
      SPECIAL_CITIES[destinationId] === 'capetown' &&
      !capetownAwarded
    ) {
      money += 500;
      nextCapetownAwarded = true;
      capetownMessage = `${currentPlayer.name} was first to reach ${spaceById[destinationId].name} and won 500!`;
    }

    const specialEffect = SPECIAL_CITIES[destinationId];
    if (
      specialEffect === 'stHelena' ||
      specialEffect === 'sahara'
    ) {
      status = { type: 'captured', effect: specialEffect };
    }

    const movedPlayer: Player = {
      ...currentPlayer,
      placeId: destinationId,
      money,
      status,
    };

    setPlayers(
      players.map(player =>
        player.id === movedPlayer.id ? movedPlayer : player,
      ),
    );
    setCapetownAwarded(nextCapetownAwarded);
    setInfoMessage(capetownMessage);
    setLastRoll(null);
    setText('');
    setMoveError(null);

    const isHome = HOME_CITY_IDS.includes(destinationId);
    const wins =
      isHome &&
      (movedPlayer.inventory.africaStar > 0 ||
        (starFound && movedPlayer.inventory.horseshoe > 0));
    if (wins) {
      setWinner(movedPlayer);
      return;
    }

    const card = cards[destinationId];
    if (card) {
      setPendingCard({ cityId: destinationId });
    } else {
      advanceTurn();
    }
  };

  const moveClick = () => {
    const derived = deriveMove(
      moveMode,
      currentPlayer.money,
      lastRoll,
    );
    if (!derived.ok) {
      setMoveError(derived.error);
      return;
    }
    const { steps, cost } = derived;

    const destination = text.trim();
    if (destination === '') {
      setMoveError('Type a place to move to.');
      return;
    }

    if (!spaceById[destination]) {
      setMoveError(
        `"${destination}" is not a place on the board.`,
      );
      return;
    }

    const moves = findMoves(currentPlayer.placeId, steps, [
      moveMode,
    ]);

    if (!moves.has(destination)) {
      setMoveError(
        `Can't reach "${destination}" by ${moveMode}.`,
      );
      return;
    }

    applyArrival(destination, cost);
  };

  /**
   * Resolve a spoken/typed move like "heading for Hakametsä" or "fly to
   * Turtola". gemma3 only extracts a heading city and a travel mode; where the
   * piece actually lands is decided here by the same findMoves the typed path
   * uses. Takes ~10s on this machine, hence the pending state and cancel.
   */
  const askClick = async () => {
    if (llmPending) return;
    const controller = new AbortController();
    llmAbort.current = controller;
    setLlmPending(true);
    setLlmMessage('Thinking…');
    setMoveError(null);

    try {
      const result = await resolveMoveIntent({
        transcript: nlText,
        currentPlaceId: currentPlayer.placeId,
        money: currentPlayer.money,
        lastRoll,
        uiMode: moveMode,
        signal: controller.signal,
      });

      if (result.kind === 'unclear') {
        setLlmMessage(result.message);
        return;
      }

      setLlmMessage(result.note);
      setNlText('');
      // Mirror the mode the player actually asked for, so the buttons agree with
      // what was just charged for.
      setMoveMode(result.mode);
      applyArrival(result.destinationId, result.cost);
    } finally {
      setLlmPending(false);
      llmAbort.current = null;
    }
  };

  const resolveCard = (action: 'pay' | 'wait' | 'skip') => {
    if (!pendingCard) return;
    const cityId = pendingCard.cityId;
    const kind = cards[cityId];
    let player = currentPlayer;

    if (action === 'pay') {
      if (player.money < 100) {
        setMoveError('Not enough money to buy this card.');
        return;
      }
      const result = applyCardEffect(
        { ...player, money: player.money - 100 },
        kind,
        cityId,
      );
      player = result.player;
      setInfoMessage(result.message);
      removeCard(cityId);
    } else if (action === 'wait') {
      player = {
        ...player,
        status: { type: 'waitingForCard', cityId },
      };
      setInfoMessage(null);
    } else {
      setInfoMessage(null);
    }

    setPlayers(
      players.map(p => (p.id === player.id ? player : p)),
    );
    setPendingCard(null);
    setMoveError(null);
    advanceTurn();
  };

  const attemptEscape = (roll: number) => {
    if (currentPlayer.status?.type !== 'captured') return;
    const escaped = roll === 1 || roll === 2;
    const updated: Player = {
      ...currentPlayer,
      status: escaped ? null : currentPlayer.status,
    };
    setPlayers(
      players.map(p => (p.id === updated.id ? updated : p)),
    );
    advanceTurn();
  };

  const attemptClaimWhileWaiting = (roll: number) => {
    if (currentPlayer.status?.type !== 'waitingForCard')
      return;
    const cityId = currentPlayer.status.cityId;
    if (roll >= 4) {
      const kind = cards[cityId];
      const result = applyCardEffect(
        { ...currentPlayer, status: null },
        kind,
        cityId,
      );
      setPlayers(
        players.map(p =>
          p.id === result.player.id ? result.player : p,
        ),
      );
      setInfoMessage(result.message);
      removeCard(cityId);
    } else {
      setInfoMessage(
        `Rolled ${roll} — not enough to claim the card yet.`,
      );
    }
    advanceTurn();
  };

  const continueSlaveTurn = () => {
    if (currentPlayer.status?.type !== 'slave') return;
    const remaining =
      currentPlayer.status.turnsRemaining - 1;
    const freed = remaining <= 0;
    setPlayers(
      players.map(p =>
        p.id === currentPlayer.id
          ? {
              ...p,
              status: freed
                ? null
                : {
                    type: 'slave' as const,
                    turnsRemaining: remaining,
                  },
            }
          : p,
      ),
    );
    if (!freed) advanceTurn();
  };

  const change = (event: ChangeEvent<HTMLInputElement>) => {
    setText(event.target.value);
  };

  const restartGame = () => {
    setPlayers([]);
    setTurnIndex(0);
    setMoveMode('land');
    setLastRoll(null);
    setText('');
    setMoveError(null);
    setInfoMessage(null);
    setCards({});
    setPendingCard(null);
    setCapetownAwarded(false);
    setStarFound(false);
    setWinner(null);
    setGameState('notStarted');
  };

  return (
    <div className='parent-box'>
      <div className='game-board'>
        <Board players={players} cards={cards} />
      </div>
      <div className='game-info'>
        gaming stats
        {!winner && (
          <GameStats
            gameState={gameState}
            onStartGame={() => setGameState('starting')}
            onBeginGame={names => {
              setPlayers(createPlayers(names));
              setCards(dealCards());
              setTurnIndex(0);
              setGameState('gameOn');
            }}
          />
        )}
        {winner && (
          <div>
            <p>
              <span style={{ color: winner.pieceColor }}>
                {winner.name}
              </span>{' '}
              brought the treasure home and wins!
            </p>
            <button onClick={restartGame}>
              Play again
            </button>
          </div>
        )}
        {gameState === 'gameOn' &&
          !winner &&
          currentPlayer && (
            <>
              <p>
                Current turn:{' '}
                <span
                  style={{
                    color: currentPlayer.pieceColor,
                  }}
                >
                  {currentPlayer.name}
                </span>
              </p>
              <p>Money: {currentPlayer.money}</p>
              <p>
                Location:{' '}
                {spaceById[currentPlayer.placeId].name}
              </p>
              {infoMessage && <p>{infoMessage}</p>}

              {currentPlayer.status?.type ===
                'captured' && (
                <div>
                  <p>
                    {currentPlayer.status.effect ===
                    'sahara'
                      ? 'Captured by bedouins in the desert!'
                      : 'Held by pirates at the island!'}{' '}
                    Roll 1 or 2 to escape.
                  </p>
                  <RollDice onRoll={attemptEscape} />
                </div>
              )}

              {currentPlayer.status?.type === 'slave' && (
                <div>
                  <p>
                    Enslaved at the Slave Coast —{' '}
                    {currentPlayer.status.turnsRemaining}{' '}
                    turn(s) left.
                  </p>
                  <button onClick={continueSlaveTurn}>
                    Continue
                  </button>
                </div>
              )}

              {currentPlayer.status?.type ===
                'waitingForCard' && (
                <div>
                  <p>
                    Waiting to claim the card at{' '}
                    {
                      spaceById[currentPlayer.status.cityId]
                        .name
                    }{' '}
                    — roll 4, 5 or 6.
                  </p>
                  <RollDice
                    onRoll={attemptClaimWhileWaiting}
                  />
                </div>
              )}

              {!currentPlayer.status && pendingCard && (
                <div>
                  <p>
                    There's an unclaimed card at{' '}
                    {spaceById[pendingCard.cityId].name}!
                  </p>
                  <button
                    disabled={currentPlayer.money < 100}
                    onClick={() => resolveCard('pay')}
                  >
                    Buy for 100
                  </button>
                  <button
                    onClick={() => resolveCard('wait')}
                  >
                    Wait for 4-5-6
                  </button>
                  <button
                    onClick={() => resolveCard('skip')}
                  >
                    Leave it
                  </button>
                </div>
              )}

              {!currentPlayer.status && !pendingCard && (
                <>
                  <div className='move-mode'>
                    <button
                      disabled={
                        moveMode === 'land' || llmPending
                      }
                      onClick={() => setMoveMode('land')}
                    >
                      Land
                    </button>
                    <button
                      disabled={
                        moveMode === 'sea' || llmPending
                      }
                      onClick={() => setMoveMode('sea')}
                    >
                      Sea (100)
                    </button>
                    <button
                      disabled={
                        moveMode === 'flight' || llmPending
                      }
                      onClick={() => setMoveMode('flight')}
                    >
                      Air (300)
                    </button>
                  </div>

                  {(moveMode === 'land' ||
                    (moveMode === 'sea' &&
                      currentPlayer.money >= 100)) && (
                    <>
                      <RollDice
                        onRoll={value => {
                          // Ignored mid-request: a new roll would invalidate the
                          // steps the pending move was resolved against.
                          if (!llmPending)
                            setLastRoll(value);
                        }}
                      />
                      {lastRoll !== null && (
                        <p>Last roll: {lastRoll}</p>
                      )}
                    </>
                  )}
                  {moveMode === 'sea' &&
                    currentPlayer.money < 100 && (
                      <p>
                        Not enough money to sail with dice —
                        you can still sail 2 steps for free.
                      </p>
                    )}

                  <label>
                    move input:{' '}
                    <input
                      name='moveInput'
                      type='text'
                      value={text}
                      onChange={change}
                      disabled={llmPending}
                    />
                    <button
                      onClick={moveClick}
                      disabled={llmPending}
                    >
                      Move
                    </button>
                  </label>
                  {moveError && <p>{moveError}</p>}

                  <label>
                    say it instead:{' '}
                    <input
                      name='nlInput'
                      type='text'
                      value={nlText}
                      placeholder='heading for Hakametsä'
                      disabled={llmPending}
                      onChange={event =>
                        setNlText(event.target.value)
                      }
                    />
                    <button
                      onClick={askClick}
                      disabled={
                        llmPending || nlText.trim() === ''
                      }
                    >
                      Ask
                    </button>
                  </label>
                  {llmPending && (
                    <button
                      onClick={() =>
                        llmAbort.current?.abort()
                      }
                    >
                      Cancel
                    </button>
                  )}
                  {llmMessage && <p>{llmMessage}</p>}
                </>
              )}
            </>
          )}
      </div>
    </div>
  );
}

export default App;
