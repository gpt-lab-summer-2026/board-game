import {
  adjacency,
  spaceById,
} from '../game/boardDataRestructure';
import type { EdgeKind } from '../game/boardDataRestructure';

/**
 * Hop count from `origin` to every space reachable using only `kinds` edges.
 * Spaces with no such route are simply absent from the map.
 */
export function distancesFrom(
  origin: string,
  kinds: readonly EdgeKind[],
): Map<string, number> {
  const dist = new Map<string, number>([[origin, 0]]);
  const queue: string[] = [origin];

  for (let head = 0; head < queue.length; head++) {
    const current = queue[head];
    const currentDist = dist.get(current) as number;
    for (const connection of adjacency[current] ?? []) {
      if (!kinds.includes(connection.kind)) continue;
      if (dist.has(connection.to)) continue;
      dist.set(connection.to, currentDist + 1);
      queue.push(connection.to);
    }
  }
  return dist;
}

/**
 * Of the squares the player may legally land on this turn, pick the one that
 * gets closest to where they said they're heading.
 *
 * This is the whole reason the model only has to name a heading. On this board
 * a roll of 1-3 usually puts *zero named cities* in reach -- you land on an
 * unnamed waypoint like s82 -- so asking the model to choose a destination
 * would leave it nothing to choose most turns. Naming a city that *is*
 * reachable still lands on it exactly, because that candidate scores distance 0.
 *
 * Returns null when no candidate can reach the heading at all by these edge
 * kinds (e.g. heading for an island on foot), which the caller reports rather
 * than moving somewhere arbitrary.
 */
export function chooseDestination(
  candidateIds: readonly string[],
  heading: string,
  kinds: readonly EdgeKind[],
): string | null {
  const dist = distancesFrom(heading, kinds);

  let best: string | null = null;
  let bestDist = Number.POSITIVE_INFINITY;
  let bestIsCity = false;

  for (const id of candidateIds) {
    const d = dist.get(id);
    if (d === undefined) continue; // no route from here to the heading
    const isCity = spaceById[id]?.kind === 'city';
    // Strictly closer wins; equally close prefers an actual city, since that's
    // a named square the player can see they arrived at.
    if (d < bestDist || (d === bestDist && isCity && !bestIsCity)) {
      best = id;
      bestDist = d;
      bestIsCity = isCity;
    }
  }
  return best;
}

/** Human-readable label for any space: city name, else the raw waypoint id. */
export function spaceLabel(id: string): string {
  return spaceById[id]?.name ?? id;
}
