import { useState, type ChangeEvent } from 'react';
import './game.css';

export type GameState =
  | 'notStarted'
  | 'starting'
  | 'gameOn';

type GameStatsProps = {
  gameState: GameState;
  onStartGame: () => void;
  onBeginGame: (names: string[]) => void;
};

const MAX_PLAYERS = 5;

function GameStats({
  gameState,
  onStartGame,
  onBeginGame,
}: GameStatsProps) {
  const [names, setNames] = useState<string[]>(
    Array(MAX_PLAYERS).fill(''),
  );

  if (gameState === 'notStarted') {
    return (
      <div className='gaming-stats'>
        <button onClick={onStartGame}>Start game</button>
      </div>
    );
  }

  if (gameState === 'starting') {
    const changeName =
      (index: number) =>
      (event: ChangeEvent<HTMLInputElement>) => {
        setNames(
          names.map((name, i) =>
            i === index ? event.target.value : name,
          ),
        );
      };
    const players = names
      .map(name => name.trim())
      .filter(name => name !== '');

    return (
      <div className='gaming-stats'>
        <p>Choose players:</p>
        <div className='players-input'>
          {names.map((name, index) => (
            <label key={index}>
              player {index + 1}:{' '}
              <input
                type='text'
                value={name}
                onChange={changeName(index)}
              />
            </label>
          ))}
        </div>

        <button
          disabled={players.length === 0}
          onClick={() => onBeginGame(players)}
        >
          Begin!
        </button>
      </div>
    );
  }

  return null;
}

export default GameStats;
