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
import { spaceById } from './game/boardDataRestructure';

export type Player = {
  id: string;
  name: string;
  placeId: string;
  pieceColor: string;
  money: number;
  inventory: Record<string, number>;
};

const START_PLACE_ID = 's70';
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
    placeId: START_PLACE_ID,
    pieceColor: PIECE_COLORS[index % PIECE_COLORS.length],
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
  }));
}

function App() {
  const [players, setPlayers] = useState<Player[]>([]);

  const [turnIndex, setTurnIndex] = useState(0);
  const currentPlayer = players[turnIndex];

  const [lastRoll, setLastRoll] = useState<number | null>(
    null,
  );
  const [text, setText] = useState('');
  const [moveError, setMoveError] = useState<string | null>(
    null,
  );
  const [gameState, setGameState] =
    useState<GameState>('notStarted');

  const moveClick = () => {
    if (lastRoll === null) {
      setMoveError('Roll the dice first.');
      return;
    }

    const destination = text.trim();
    if (destination === '') {
      setMoveError('Type a place to move to.');
      return;
    }

    if (!spaceById[destination]) {
      setMoveError(`"${destination}" is not a place on the board.`);
      return;
    }

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

    const movedPlayer: Player = {
      ...currentPlayer,
      placeId: destination,
    };

    setPlayers(
      players.map(player =>
        player.id === movedPlayer.id ? movedPlayer : player,
      ),
    );
    setTurnIndex(index => (index + 1) % players.length);
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
      <div className='game-info'>
        gaming stats
        <GameStats
          gameState={gameState}
          onStartGame={() => setGameState('starting')}
          onBeginGame={names => {
            setPlayers(createPlayers(names));
            setTurnIndex(0);
            setGameState('gameOn');
          }}
        />
        {gameState === 'gameOn' && currentPlayer && (
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
            <RollDice onRoll={setLastRoll} />
            {lastRoll !== null && (
              <p>Last roll: {lastRoll}</p>
            )}
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
          </>
        )}
      </div>
    </div>
  );
}

export default App;
