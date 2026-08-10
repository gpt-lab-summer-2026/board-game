import { adjacency, spaceById } from './boardDataRestructure';
import type { EdgeKind } from './boardDataRestructure';

/**
 * All nodes reachable from `start` using only the given route kinds,
 * never revisiting a node within a single path. A destination is valid
 * either after using every one of the `steps` moves, or earlier if it
 * lands on a city (red circle) - per the rules, you may always stop
 * early at a city without using the rest of the roll.
 *
 * Returns destination id -> path (including start, ending at destination).
 */
export function findMoves(
  start: string,
  steps: number,
  kinds: EdgeKind[] = ['land'],
): Map<string, string[]> {
  const results = new Map<string, string[]>();

  function explore(
    current: string,
    path: string[],
    remaining: number,
  ) {
    const isEarlyStop = path.length > 1 && remaining > 0;
    if (
      (isEarlyStop &&
        spaceById[current]?.kind === 'city') ||
      remaining === 0
    ) {
      // first path found to a given destination wins
      if (!results.has(current)) {
        results.set(current, path);
      }
      if (remaining === 0) return;
    }

    for (const connection of adjacency[current] ?? []) {
      if (!kinds.includes(connection.kind)) continue;
      if (path.includes(connection.to)) continue; // no revisiting
      explore(
        connection.to,
        [...path, connection.to],
        remaining - 1,
      );
    }
  }

  explore(start, [start], steps);
  return results;
}
