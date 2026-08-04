import './App.css';
import Board from './game/board';

function App() {
  return (
    <div className='parent-box'>
      <div className='game-board'>
        <Board />
      </div>
      <div className='gaming-stats'>gaming stats</div>
    </div>
  );
}

export default App;
