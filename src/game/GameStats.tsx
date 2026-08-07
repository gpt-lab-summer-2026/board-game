import {
  useImperativeHandle,
  useState,
  type ChangeEvent,
  type Ref,
} from 'react';
import './game.css';
import { spaceById } from './boardDataRestructure';
import { HOME_CITY_IDS } from './rules';

export type GameState =
  | 'notStarted'
  | 'starting'
  | 'gameOn';

export type PlayerSetup = { name: string; startId: string };

/**
 * Lets voice input drive the same setup this component's own inputs/button
 * do, without lifting names/startIds into App -- the form keeps owning its
 * state, voice just calls the same effect a keystroke or click would have.
 */
export type GameStatsHandle = {
  addPlayerByName: (name: string) => void;
  triggerBegin: () => void;
};

type GameStatsProps = {
  gameState: GameState;
  onStartGame: () => void;
  onBeginGame: (players: PlayerSetup[]) => void;
  ref?: Ref<GameStatsHandle>;
};

const MAX_PLAYERS = 5;

function GameStats({
  gameState,
  onStartGame,
  onBeginGame,
  ref,
}: GameStatsProps) {
  const [names, setNames] = useState<string[]>(
    Array(MAX_PLAYERS).fill(''),
  );
  // Default to alternating between the home cities, which is what the game did
  // before this was selectable -- so leaving the dropdowns alone behaves as it
  // always has.
  const [startIds, setStartIds] = useState<string[]>(
    Array.from(
      { length: MAX_PLAYERS },
      (_, i) => HOME_CITY_IDS[i % HOME_CITY_IDS.length],
    ),
  );

  useImperativeHandle(ref, () => ({
    addPlayerByName(name: string) {
      setNames(prev => {
        const emptyIndex = prev.findIndex(
          existing => existing.trim() === '',
        );
        if (emptyIndex === -1) return prev; // all MAX_PLAYERS slots taken
        const next = [...prev];
        next[emptyIndex] = name;
        return next;
      });
    },
    triggerBegin() {
      const setups: PlayerSetup[] = names
        .map((name, index) => ({
          name: name.trim(),
          startId: startIds[index],
        }))
        .filter(player => player.name !== '');
      if (setups.length > 0) onBeginGame(setups);
    },
  }));

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
    const changeStart =
      (index: number) =>
      (event: ChangeEvent<HTMLSelectElement>) => {
        setStartIds(
          startIds.map((id, i) =>
            i === index ? event.target.value : id,
          ),
        );
      };
    const players: PlayerSetup[] = names
      .map((name, index) => ({
        name: name.trim(),
        startId: startIds[index],
      }))
      .filter(player => player.name !== '');

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
              />{' '}
              <select
                value={startIds[index]}
                onChange={changeStart(index)}
                aria-label={`player ${index + 1} starting city`}
              >
                {HOME_CITY_IDS.map(id => (
                  <option key={id} value={id}>
                    {spaceById[id]?.name ?? id}
                  </option>
                ))}
              </select>
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
