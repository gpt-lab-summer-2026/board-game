import { useState, type ChangeEvent } from 'react';
import './App.css';
import Board from './game/board';
import RollDice from './game/RollDice';
import { library } from '@fortawesome/fontawesome-svg-core';
import { fas } from '@fortawesome/free-solid-svg-icons';
library.add(fas);
import { adjacency, spaceById } from './game/boardDataRestructure';
import type { EdgeKind } from './game/boardDataRestructure';

export type Player = {
  id: string;
  placeId: string;
  positionX: number;
  positionY: number;
  money: number;
  inventory: Record<string, number>;
};

function InitializeGame(): Player[] {
  return [
    {
      id: 'player-1',
      placeId: 's70',
      positionX: 0.45389,
      positionY: 0.38926,
      money: 300,
      inventory: {
        empty: 0,
        horseShoe: 0,
        robber: 0,
        topaz: 0,
        emerald: 0,
        ruby: 0,
        africaStar: 0,
      },
    },
  ];
}

/**
 * All nodes reachable from `start` using only the given route kinds,
 * never revisiting a node within a single path. A destination is valid
 * either after using every one of the `steps` moves, or earlier if it
 * lands on a city (red circle) - per the rules, you may always stop
 * early at a city without using the rest of the roll.
 *
 * Returns destination id -> path (including start, ending at destination).
 */
export function findMoves(
  start: string,
  steps: number,
  kinds: EdgeKind[] = ['land'],
): Map<string, string[]> {
  const results = new Map<string, string[]>();

  function explore(
    current: string,
    path: string[],
    remaining: number,
  ) {
    const isEarlyStop = path.length > 1 && remaining > 0;
    if (
      (isEarlyStop && spaceById[current]?.kind === 'city') ||
      remaining === 0
    ) {
      // first path found to a given destination wins
      if (!results.has(current)) {
        results.set(current, path);
      }
      if (remaining === 0) return;
    }

    for (const connection of adjacency[current] ?? []) {
      if (!kinds.includes(connection.kind)) continue;
      if (path.includes(connection.to)) continue; // no revisiting
      explore(
        connection.to,
        [...path, connection.to],
        remaining - 1,
      );
    }
  }

  explore(start, [start], steps);
  return results;
}

function App() {
  const [players, setPlayers] = useState<Player[]>(
    InitializeGame(),
  );
  const [currentPlayer, setCurrentPlayer] =
    useState<Player>(players[0]);
  const [lastRoll, setLastRoll] = useState<number | null>(
    null,
  );
  const [text, setText] = useState('');
  const [moveError, setMoveError] = useState<
    string | null
  >(null);

  const moveClick = () => {
    if (lastRoll === null) {
      setMoveError('Roll the dice first.');
      return;
    }

    const destination = text.trim();
    const moves = findMoves(
      currentPlayer['placeId'],
      lastRoll,
      ['land'],
    );

    if (!moves.has(destination)) {
      setMoveError(
        `Can't reach "${destination}" in ${lastRoll} steps.`,
      );
      return;
    }

    const space = spaceById[destination];
    const movedPlayer: Player = {
      ...currentPlayer,
      placeId: destination,
      positionX: space.x,
      positionY: space.y,
    };

    setPlayers(
      players.map(player =>
        player.id === movedPlayer.id ? movedPlayer : player,
      ),
    );
    setCurrentPlayer(movedPlayer);
    setLastRoll(null);
    setText('');
    setMoveError(null);
  };

  const change = (event: ChangeEvent<HTMLInputElement>) => {
    setText(event.target.value);
  };

  return (
    <div className='parent-box'>
      <div className='game-board'>
        <Board players={players} />
      </div>
      <div className='gaming-stats'>
        gaming stats
        <RollDice onRoll={setLastRoll} />
        {lastRoll !== null && <p>Last roll: {lastRoll}</p>}
        <label>
          move input:{' '}
          <input
            name='moveInput'
            type='text'
            value={text}
            onChange={change}
          />
          <button onClick={moveClick}>Move</button>
        </label>
        {moveError && <p>{moveError}</p>}
      </div>
    </div>
  );
}

export default App;
