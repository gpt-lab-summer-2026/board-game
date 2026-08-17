/**
 * Walking the board's shapes, floor by floor and layer by layer.
 *
 * Both the Sides panel and the Layer panel need "every shape, and where it
 * lives", and the walk is fiddlier than it looks: the reactive floor list holds
 * plain descriptors, layers hang off the floor *system*, and a shape only has a
 * GlobalId once the server has acknowledged it. Doing that twice invites the two
 * panels to disagree about what is on the board.
 */
import type { GlobalId, LocalId } from "../../core/id";
import { getGlobalId } from "../id";
import type { ILayer } from "../interfaces/layer";
import type { IShape } from "../interfaces/shape";
import type { FloorId, LayerName } from "../models/floor";
import { floorSystem } from "../systems/floors";
import { floorState } from "../systems/floors/state";
import { getProperties } from "../systems/properties/state";

export interface ShapeEntry {
    id: GlobalId;
    localId: LocalId;
    name: string;
    shape: IShape;
    layer: ILayer;
    layerName: LayerName;
    floorId: FloorId;
    floorName: string;
}

export interface CollectOptions {
    /** Restrict to one floor. Omit for every floor. */
    floorId?: FloorId;
    /** Restrict to specific layers. Omit for every layer the floor has. */
    layers?: LayerName[];
    /** Drop shapes with no name - scenery and drawing scratch, mostly. */
    namedOnly?: boolean;
}

export function collectShapes(options: CollectOptions = {}): ShapeEntry[] {
    const entries: ShapeEntry[] = [];

    for (const summary of floorState.reactive.floors) {
        if (options.floorId !== undefined && summary.id !== options.floorId) continue;

        const floor = floorSystem.getFloor({ id: summary.id }, false);
        if (floor === undefined) continue;

        const layers = floorSystem.getLayers(floor);
        for (const layer of layers) {
            if (options.layers !== undefined && !options.layers.includes(layer.name)) continue;

            // Bottom-to-top, matching render order: index 0 is drawn first.
            for (const shape of layer.getShapes({ onlyInView: false })) {
                const id = getGlobalId(shape.id);
                if (id === undefined) continue; // not yet acknowledged by the server

                const name = getProperties(shape.id)?.name ?? "";
                if (options.namedOnly === true && name === "") continue;

                entries.push({
                    id,
                    localId: shape.id,
                    name,
                    shape,
                    layer,
                    layerName: layer.name,
                    floorId: summary.id,
                    floorName: summary.name,
                });
            }
        }
    }

    return entries;
}
