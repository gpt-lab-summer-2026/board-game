import type { Player } from '../App';
import mapPath from '../assets/kartta2.png';

import './game.css';

import {
  spaceById,
  spaces,
  edges,
  meta,
} from './boardDataRestructure';
import {
  HOME_CITY_IDS,
  SPECIAL_CITIES,
  CARD_DISPLAY,
  type CardKind,
} from './rules';

function cityFill(id: string) {
  if (HOME_CITY_IDS.includes(id)) return '#efbc3b';
  if (SPECIAL_CITIES[id]) return 'purple';
  return '#79942e';
}

// Splits a label into lines no longer than maxChars, breaking on
// spaces or hyphens (keeping the hyphen at the end of its line) so
// long place names wrap instead of overflowing their circle.
function wrapLabel(
  label: string,
  maxChars: number,
): string[] {
  const tokens = label.match(/[^\s-]+[\s-]?/g) ?? [label];
  const lines: string[] = [];
  let current = '';
  for (const token of tokens) {
    if (
      current &&
      (current + token).trim().length > maxChars
    ) {
      lines.push(current.trim());
      current = token;
    } else {
      current += token;
    }
  }
  if (current.trim()) lines.push(current.trim());
  return lines;
}

function MultilineLabel({
  x,
  y,
  label,
  fontSize,
  maxChars,
}: {
  x: number;
  y: number;
  label: string;
  fontSize: number;
  maxChars: number;
}) {
  const lines = wrapLabel(label, maxChars);
  const lineHeightEm = 1.1;
  const firstDy =
    0.3 - ((lines.length - 1) / 2) * lineHeightEm;

  return (
    <text
      x={x}
      y={y}
      text-anchor='middle'
      fill='white'
      font-size={`${fontSize}px`}
      font-family='Arial'
    >
      {lines.map((line, i) => (
        <tspan
          key={i}
          x={x}
          dy={`${i === 0 ? firstDy : lineHeightEm}em`}
        >
          {line}
        </tspan>
      ))}
    </text>
  );
}

// All place-name labels, rendered as their own top-most layer (see
// bottom of Board) so text always stays readable above routes,
// cards, and player pieces.
function CreateLabels() {
  const labels = spaces.map(
    (item: {
      id: string;
      kind: string;
      x: number;
      y: number;
    }) => {
      const x = item.x * meta['width'];
      const y = item.y * meta['height'];

      if (item.kind === 'city') {
        return (
          <MultilineLabel
            key={item.id}
            x={x}
            y={y}
            label={item.id}
            fontSize={40}
            maxChars={9}
          />
        );
      }
      if (item.kind === 'step') {
        return (
          <MultilineLabel
            key={item.id}
            x={x}
            y={y}
            label={item.id}
            fontSize={25}
            maxChars={6}
          />
        );
      }
      if (item.kind === 'sea') {
        return (
          <MultilineLabel
            key={item.id}
            x={x}
            y={y}
            label={item.id}
            fontSize={10}
            maxChars={6}
          />
        );
      }
      return null;
    },
  );
  return <>{labels}</>;
}

function CreateLandRoutes() {
  const objectArray = edges.map(item => {
    if (item['kind'] === 'land') {
      const a = spaceById[item.a];
      const b = spaceById[item.b];
      return (
        <line
          key={`${item.a}-${item.b}`}
          x1={a.x * meta['width']}
          y1={a.y * meta['height']}
          x2={b.x * meta['width']}
          y2={b.y * meta['height']}
          stroke='black'
          stroke-width='3'
        />
      );
    }

    return null;
  });
  return <>{objectArray}</>;
}

function CreateCities() {
  const objectArray = spaces.map(
    (item: {
      id: string;
      kind: string;
      x: number;
      y: number;
    }) => {
      if (item['kind'] !== 'city') return null;
      return (
        <circle
          key={item.id}
          r='70'
          cx={item['x'] * meta['width']}
          cy={item['y'] * meta['height']}
          fill={cityFill(item.id)}
        />
      );
    },
  );
  return <>{objectArray}</>;
}

function CreateSteps() {
  const objectArray = spaces.map(
    (item: {
      id: string;
      kind: string;
      x: number;
      y: number;
    }) => {
      if (item['kind'] !== 'step') return null;
      return (
        <circle
          key={item.id}
          r='25'
          cx={item['x'] * meta['width']}
          cy={item['y'] * meta['height']}
          fill='blue'
        />
      );
    },
  );
  return <>{objectArray}</>;
}

function CreateWaterRoutes() {
  const objectArray = edges.map(item => {
    if (item['kind'] === 'sea') {
      const a = spaceById[item.a];
      const b = spaceById[item.b];
      return (
        <line
          key={`${item.a}-${item.b}`}
          x1={a.x * meta['width']}
          y1={a.y * meta['height']}
          x2={b.x * meta['width']}
          y2={b.y * meta['height']}
          stroke='#2fabc1'
          stroke-width='5'
        />
      );
    }

    return null;
  });
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
            key={item.id}
            r='25'
            cx={item['x'] * meta['width']}
            cy={item['y'] * meta['height']}
            fill='#2fabc1'
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

// Placeholder for the cardboard piece sitting on each unclaimed city -
// swap the <rect>/<text> below for an <image> (gif) per CardKind later.
function CreateCards({
  cards,
}: {
  cards: Record<string, CardKind>;
}) {
  const cardMarkers = Object.entries(cards).map(
    ([cityId, kind]) => {
      const space = spaceById[cityId];
      if (!space) return null;
      const display = CARD_DISPLAY[kind];
      const x = space.x * meta['width'];
      const y = space.y * meta['height'] - 40;

      return (
        <g
          key={cityId}
          className={`card-piece card-piece-${kind}`}
        >
          <rect
            x={x - 8}
            y={y - 8}
            width='16'
            height='16'
            rx='3'
            fill={display.color}
            stroke='black'
          />
          <text
            x={x}
            y={y}
            text-anchor='middle'
            fill='black'
            font-size='11px'
            font-family='Arial'
            dy='.3em'
          >
            {display.label}
          </text>
        </g>
      );
    },
  );
  return <>{cardMarkers}</>;
}

const PIECE_SPREAD = 16;

// When several pieces share a space, spread them around the center
// in a small ring instead of stacking them exactly on top of each
// other, so every piece stays visible.
function pieceOffset(
  indexInGroup: number,
  groupSize: number,
) {
  if (groupSize <= 1) return { dx: 0, dy: 0 };
  const angle = (2 * Math.PI * indexInGroup) / groupSize;
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

function Board({
  players,
  cards,
}: {
  players: Player[];
  cards: Record<string, CardKind>;
}) {
  return (
    // for loop through the board data and render each object
    <div className='wrapper'>
      <img
        className='wrapper-img'
        src={mapPath}
        alt='Game board map'
      />
      <svg
        className='svg'
        viewBox={`0 0 ${meta.width} ${meta.height}`}
        xmlns='http://www.w3.org/2000/svg'
      >
        <CreateLandRoutes />
        <CreateWaterRoutes />
        <CreateSeaRoutes />
        <CreateCities />
        <CreateSteps />
        <CreateFlightRoutes />
        <CreateCards cards={cards} />
        <CreateButtons players={players} />
        <CreateLabels />
      </svg>
    </div>
  );
}

export default Board;
