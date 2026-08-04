import type { Player } from '../App';
import mapPath from '../assets/map1.jpg';

import './board.css';

import {
  spaceById,
  spaces,
  edges,
  meta,
} from './boardDataRestructure';

function CreateObjects() {
  const objectArray = spaces.map(
    (item: {
      id: string;
      kind: string;
      x: number;
      y: number;
    }) => {
      if (item['kind'] === 'step') {
        return (
          <circle
            r='10'
            cx={item['x'] * meta['width']}
            cy={item['y'] * meta['height']}
            fill='blue'
          />
        );
      } else if (item['kind'] === 'city') {
        return (
          <circle
            r='30'
            cx={item['x'] * meta['width']}
            cy={item['y'] * meta['height']}
            fill='red'
          />
        );
      }
      return null;
    },
  );
  return <>{objectArray}</>;
}

// in it's own function so the sea routes would be below cities etc
function CreateSeaRoutes() {
  const objectArray = spaces.map(
    (item: {
      id: string;
      kind: string;
      x: number;
      y: number;
    }) => {
      if (item['kind'] === 'sea') {
        return (
          <circle
            r='10'
            cx={item['x'] * meta['width']}
            cy={item['y'] * meta['height']}
            fill='blue'
            opacity='0.6'
          />
        );
      }

      return null;
    },
  );
  return <>{objectArray}</>;
}

function CreateFlightRoutes() {
  const objectArray = edges.map(item => {
    if (item['kind'] === 'flight') {
      // find correct city objects so their postions are known
      const city1 = spaceById[item.a];
      const city2 = spaceById[item.b];

      return (
        <line
          x1={city1['x'] * meta['width']}
          y1={city1['y'] * meta['height']}
          x2={city2['x'] * meta['width']}
          y2={city2['y'] * meta['height']}
          stroke='red'
          stroke-width='5'
          strokeDasharray='10'
        />
      );
    }

    return null;
  });
  return <>{objectArray}</>;
}

function CreateButtons({ players }: { players: Player[] }) {
  const playersArray = players.map(player => {
    console.log('player: ', player);
    return (
      <circle
        r='10'
        cx={player['positionX'] * meta['width']}
        cy={player['positionY'] * meta['height']}
        fill='green'
      />
    );
  });
  return <>{playersArray}</>;
}

function Board({ players }: { players: Player[] }) {
  return (
    // for loop through board.json end render each object
    <div className='wrapper'>
      <img
        className='wrapper-img'
        src={mapPath}
        alt='Game board map'
      />
      <svg
        className='svg'
        viewBox='0 0 733 1024'
        xmlns='http://www.w3.org/2000/svg'
      >
        <CreateSeaRoutes />
        <CreateObjects />
        <CreateFlightRoutes />
        <CreateButtons players={players} />
      </svg>
    </div>
  );
}

export default Board;
