import boardData from './board.json';
import mapPath from '../assets/map1.jpg';

function CreateObjects() {
  const objectArray = boardData['spaces'].map(
    (item: {
      id: string;
      kind: string;
      x: number;
      y: number;
    }) => {
      console.log('id ', item['id']);
      if (item['kind'] === 'city') {
        return (
          <circle
            r='0.015'
            cx={item['x']}
            cy={item['y']}
            fill='red'
          />
        );
      } else if (item['kind'] === 'step') {
        return (
          <circle
            r='0.008'
            cx={item['x']}
            cy={item['y']}
            fill='blue'
          />
        );
      } else if (item['kind'] === 'sea') {
        return (
          <circle
            r='0.008'
            cx={item['x']}
            cy={item['y']}
            fill='blue'
            opacity='0.6'
          />
        );

        return null;
      }
    },
  );
  return <>{objectArray}</>;
}

function Board() {
  return (
    // for loop through board.json end render each object
    <div>
      <svg
        viewBox='0 0 1 1'
        xmlns='http://www.w3.org/2000/svg'
      >
        <CreateObjects />
      </svg>

      <img src={mapPath} alt='Game board map' />
    </div>
  );
}

export default Board;
