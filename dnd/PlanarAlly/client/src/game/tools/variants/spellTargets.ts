/*
 * Who a spell template actually catches.
 *
 * Two questions, deliberately separate:
 *
 *   1. whose token centre falls inside the template shape;
 *   2. of those, who the caster can actually see.
 *
 * The second is optional because both answers are legitimate at a table -- a
 * fireball fills a volume whether or not you can see into it, while a spell
 * that "targets a creature you can see" does not. Making it a toggle rather
 * than baking one rule in is the honest choice.
 *
 * Visibility reuses PlanarAlly's own vision computation rather than a
 * hand-rolled ray cast, so what the spell thinks is visible and what the fog
 * layer draws cannot disagree.
 */
import type { GlobalPoint } from "../../../core/geometry";
import type { LocalId } from "../../../core/id";
import type { IShape } from "../../interfaces/shape";
import type { FloorId } from "../../models/floor";
import { floorSystem } from "../../systems/floors";
import { floorState } from "../../systems/floors/state";
import { LayerName } from "../../models/floor";
import { getProperties } from "../../systems/properties/state";
import { TriangulationTarget } from "../../vision/state";
import { computeVisibility } from "../../vision/te";

export interface SpellTarget {
    id: LocalId;
    name: string;
    visible: boolean;
}

/** Ray-cast point-in-polygon. The visibility polygon is arbitrary, not convex. */
function inPolygon(point: GlobalPoint, polygon: [number, number][]): boolean {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
        const [xi, yi] = polygon[i]!;
        const [xj, yj] = polygon[j]!;
        const crosses = yi > point.y !== yj > point.y;
        if (crosses && point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi) {
            inside = !inside;
        }
    }
    return inside;
}

function tokensOnFloor(floor: FloorId): IShape[] {
    const target = floorState.raw.floors.find((f) => f.id === floor);
    if (target === undefined) return [];
    const layer = floorSystem.getLayer(target, LayerName.Tokens);
    return layer === undefined ? [] : [...layer.getShapes({ onlyInView: false })];
}

/**
 * Tokens caught by `template`, annotated with whether `from` can see them.
 *
 * `from` is the caster's position; pass undefined to skip the visibility pass
 * entirely (a template dropped on the map with nobody casting it).
 */
export function spellTargets(template: IShape, from: GlobalPoint | undefined): SpellTarget[] {
    const floor = template.floorId;
    if (floor === undefined) return [];

    let polygon: [number, number][] | undefined;
    if (from !== undefined) {
        try {
            const { visibility } = computeVisibility(from, TriangulationTarget.VISION, floor);
            polygon = visibility as [number, number][];
        } catch {
            // Vision can throw when the triangulation is mid-rebuild. Falling
            // back to "everything is visible" is the safe direction: it never
            // silently drops a target the caster could actually hit.
            polygon = undefined;
        }
    }

    const out: SpellTarget[] = [];
    for (const shape of tokensOnFloor(floor)) {
        if (shape.id === template.id) continue;
        const centre = shape.center;
        if (!template.contains(centre)) continue;

        out.push({
            id: shape.id,
            name: getProperties(shape.id)?.name ?? "?",
            visible: polygon === undefined || inPolygon(centre, polygon),
        });
    }
    return out;
}
