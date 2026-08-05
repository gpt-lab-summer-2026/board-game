import type { Player } from '../App';
import mapPath from '../assets/map1.jpg';

import './game.css';

import {
  spaceById,
  spaces,
  edges,
  meta,
} from './boardDataRestructure';
import { HOME_CITY_IDS, SPECIAL_CITIES } from './rules';

function cityFill(id: string) {
  if (HOME_CITY_IDS.includes(id)) return 'gold';
  if (SPECIAL_CITIES[id]) return 'purple';
  return 'red';
}

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
          <g>
            <circle
              r='10'
              cx={item['x'] * meta['width']}
              cy={item['y'] * meta['height']}
              fill='blue'
            />
            <text
              x={item['x'] * meta['width']}
              y={item['y'] * meta['height']}
              text-anchor='middle'
              fill='white'
              font-size='10px'
              font-family='Arial'
              dy='.3em'
            >
              {item.id}
            </text>
          </g>
        );
      } else if (item['kind'] === 'city') {
        return (
          <g>
            <circle
              r='30'
              cx={item['x'] * meta['width']}
              cy={item['y'] * meta['height']}
              fill={cityFill(item.id)}
            />
            <text
              x={item['x'] * meta['width']}
              y={item['y'] * meta['height']}
              text-anchor='middle'
              fill='white'
              font-size='15px'
              font-family='Arial'
              dy='.3em'
            >
              {item.id}
            </text>
          </g>
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
          <g>
            <circle
              r='10'
              cx={item['x'] * meta['width']}
              cy={item['y'] * meta['height']}
              fill='blue'
            />
            <text
              x={item['x'] * meta['width']}
              y={item['y'] * meta['height']}
              text-anchor='middle'
              fill='white'
              font-size='10px'
              font-family='Arial'
              dy='.3em'
            >
              {item.id}
            </text>
          </g>
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

const PIECE_SPREAD = 16;

// When several pieces share a space, spread them around the center
// in a small ring instead of stacking them exactly on top of each
// other, so every piece stays visible.
function pieceOffset(indexInGroup: number, groupSize: number) {
  if (groupSize <= 1) return { dx: 0, dy: 0 };
  const angle =
    (2 * Math.PI * indexInGroup) / groupSize;
  return {
    dx: Math.cos(angle) * PIECE_SPREAD,
    dy: Math.sin(angle) * PIECE_SPREAD,
  };
}

function CreateButtons({ players }: { players: Player[] }) {
  const byPlace = new Map<string, Player[]>();
  for (const player of players) {
    const group = byPlace.get(player.placeId) ?? [];
    group.push(player);
    byPlace.set(player.placeId, group);
  }

  const playersArray = players.map(player => {
    const playerSpace = spaceById[player.placeId];
    const group = byPlace.get(player.placeId) ?? [player];
    const offset = pieceOffset(
      group.indexOf(player),
      group.length,
    );
    return (
      <circle
        key={player.id}
        r='10'
        cx={playerSpace.x * meta['width'] + offset.dx}
        cy={playerSpace.y * meta['height'] + offset.dy}
        fill={player.pieceColor}
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
