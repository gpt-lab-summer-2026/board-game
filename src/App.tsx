import { useState, type ChangeEvent } from 'react';
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
import { spaceById, spaces } from './game/boardDataRestructure';
import type { EdgeKind } from './game/boardDataRestructure';
import {
  createDeck,
  CARD_PAYOUT,
  HOME_CITY_IDS,
  SPECIAL_CITIES,
  type CardKind,
  type PlayerStatus,
} from './game/rules';

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

  const [moveMode, setMoveMode] = useState<EdgeKind>('land');
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
  ): Player => {
    const isGoldCoast =
      SPECIAL_CITIES[cityId] === 'goldCoast';
    const inventory = { ...player.inventory };
    let money = player.money;
    let status = player.status;

    switch (kind) {
      case 'blank':
        inventory.empty += 1;
        if (SPECIAL_CITIES[cityId] === 'slaveCoast') {
          status = { type: 'slave', turnsRemaining: 3 };
        }
        break;
      case 'horseshoe':
        if (starFound) inventory.horseshoe += 1;
        break;
      case 'robber':
        inventory.robber += 1;
        money = 0;
        break;
      case 'topaz':
      case 'emerald':
      case 'ruby': {
        const payout =
          (CARD_PAYOUT[kind] ?? 0) *
          (isGoldCoast ? 2 : 1);
        money += payout;
        inventory[kind] += 1;
        break;
      }
      case 'star':
        inventory.africaStar += 1;
        setStarFound(true);
        break;
    }

    return { ...player, money, inventory, status };
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
        player.id === movedPlayer.id
          ? movedPlayer
          : player,
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
    let steps: number;
    if (moveMode === 'flight') {
      steps = 1;
    } else if (
      moveMode === 'sea' &&
      currentPlayer.money < 100
    ) {
      steps = 2;
    } else if (lastRoll === null) {
      setMoveError('Roll the dice first.');
      return;
    } else {
      steps = lastRoll;
    }

    const cost =
      moveMode === 'flight'
        ? 300
        : moveMode === 'sea' && currentPlayer.money >= 100
          ? 100
          : 0;

    if (cost > 0 && currentPlayer.money < cost) {
      setMoveError(
        `You need at least ${cost} to travel by ${moveMode}.`,
      );
      return;
    }

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
      player = applyCardEffect(
        { ...player, money: player.money - 100 },
        kind,
        cityId,
      );
      removeCard(cityId);
    } else if (action === 'wait') {
      player = {
        ...player,
        status: { type: 'waitingForCard', cityId },
      };
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
      players.map(p =>
        p.id === updated.id ? updated : p,
      ),
    );
    advanceTurn();
  };

  const attemptClaimWhileWaiting = (roll: number) => {
    if (currentPlayer.status?.type !== 'waitingForCard')
      return;
    const cityId = currentPlayer.status.cityId;
    if (roll >= 4) {
      const kind = cards[cityId];
      const updated = applyCardEffect(
        { ...currentPlayer, status: null },
        kind,
        cityId,
      );
      setPlayers(
        players.map(p =>
          p.id === updated.id ? updated : p,
        ),
      );
      removeCard(cityId);
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
        <Board players={players} />
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
              <span
                style={{ color: winner.pieceColor }}
              >
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
                      spaceById[
                        currentPlayer.status.cityId
                      ].name
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
                      disabled={moveMode === 'land'}
                      onClick={() => setMoveMode('land')}
                    >
                      Land
                    </button>
                    <button
                      disabled={moveMode === 'sea'}
                      onClick={() => setMoveMode('sea')}
                    >
                      Sea (100)
                    </button>
                    <button
                      disabled={moveMode === 'flight'}
                      onClick={() => setMoveMode('flight')}
                    >
                      Air (300)
                    </button>
                  </div>

                  {(moveMode === 'land' ||
                    (moveMode === 'sea' &&
                      currentPlayer.money >= 100)) && (
                    <>
                      <RollDice onRoll={setLastRoll} />
                      {lastRoll !== null && (
                        <p>Last roll: {lastRoll}</p>
                      )}
                    </>
                  )}
                  {moveMode === 'sea' &&
                    currentPlayer.money < 100 && (
                      <p>
                        Not enough money to sail with
                        dice — you can still sail 2 steps
                        for free.
                      </p>
                    )}

                  <label>
                    move input:{' '}
                    <input
                      name='moveInput'
                      type='text'
                      value={text}
                      onChange={change}
                    />
                    <button onClick={moveClick}>
                      Move
                    </button>
                  </label>
                  {moveError && <p>{moveError}</p>}
                </>
              )}
            </>
          )}
      </div>
    </div>
  );
}

export default App;
