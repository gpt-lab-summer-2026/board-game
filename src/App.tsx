import { useState } from 'react';
import './App.css';
import Board from './game/board';

export type Player = {
  id: string;
  positionX: number;
  positionY: number;
  money: number;
  inventory: Record<string, number>;
};

function InitializeGame(): Player[] {
  return [
    {
      id: 'player-1',
      positionX: 0.65293,
      positionY: 0.31191,
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

function App() {
  const [players, setPlayers] = useState<Player[]>(
    InitializeGame(),
  );

  return (
    <div className='parent-box'>
      <div className='game-board'>
        <Board players={players} />
      </div>
      <div className='gaming-stats'>gaming stats</div>
    </div>
  );
}

export default App;
