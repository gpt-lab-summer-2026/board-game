import rawBoard from './board.json';

export type SpaceKind = 'city' | 'step' | 'sea';
export type EdgeKind = 'land' | 'sea' | 'flight';

export type Meta = {
  image: string;
  width: number;
  height: number;
  generated: string;
  cities: number;
  spaces: number;
  edges: number;
};

export type Space = {
  id: string;
  kind: SpaceKind;
  name?: string;
  x: number;
  y: number;
};

export type Edge = {
  a: string;
  b: string;
  kind: EdgeKind;
};

export type Connection = {
  to: string;
  kind: EdgeKind;
};

// spaces and edges from board.json to their own consts
const spaces = rawBoard.spaces as Space[];
const edges = rawBoard.edges as Edge[];
const meta = rawBoard.meta as Meta;

// id -> space
export const spaceById: Record<string, Space> = {};
for (const space of spaces) {
  if (spaceById[space.id]) {
    console.warn(`Duplicate space id: ${space.id}`);
  }
  spaceById[space.id] = space;
}

// id -> list of connections, both directions
export const adjacency: Record<string, Connection[]> = {};

// pre-seed so every node has a list, even isolated ones
for (const space of spaces) {
  adjacency[space.id] = [];
}

for (const edge of edges) {
  if (!spaceById[edge.a]) {
    console.warn(
      `Edge references unknown space: ${edge.a} (${edge.a}–${edge.b})`,
    );
    continue;
  }
  if (!spaceById[edge.b]) {
    console.warn(
      `Edge references unknown space: ${edge.b} (${edge.a}–${edge.b})`,
    );
    continue;
  }
  adjacency[edge.a].push({ to: edge.b, kind: edge.kind });
  adjacency[edge.b].push({ to: edge.a, kind: edge.kind });
}

export { spaces, edges, meta };
