<script setup lang="ts">
/*
 * Layer panel: what is on the board, and where in the stack.
 *
 * The canvas shows you a picture, never the structure behind it -- which layer a
 * token sits on, or what is buried under that map image. The right-click menu
 * can send a shape to the front or the back, but there is no way to see the
 * order, so fixing a stack meant clicking blind and hoping.
 *
 * Listed TOP FIRST, like every other layers panel in the world: the row at the
 * top of the list is the thing drawn on top. Internally index 0 is the *bottom*
 * of a layer, so every drag index is flipped on the way in and out (see
 * `toStackIndex`). Getting that backwards silently inverts the board.
 */
import type { SortableEvent } from "sortablejs";
import { computed, ref } from "vue";
import { type DraggableEvent, VueDraggable } from "vue-draggable-plus";

import type { LocalId } from "../../core/id";
import { SyncMode } from "../../core/models/types";
import type { ILayer } from "../interfaces/layer";
import { LayerName } from "../models/floor";
import { floorSystem } from "../systems/floors";
import { floorState } from "../systems/floors/state";
import { selectedSystem } from "../systems/selected";
import { selectedState } from "../systems/selected/state";
import { uiState } from "../systems/ui/state";
import { uiSystem } from "../systems/ui";
import { setCenterPosition } from "../position";
import { moveLayer } from "../temp";

import type { ShapeEntry } from "./shapeInventory";
import { collectShapes } from "./shapeInventory";

const visible = computed(() => uiState.reactive.showLayers);

/**
 * Layers worth listing.
 *
 * `grid` and the two fow layers are machinery, not content -- they hold no user
 * shapes and listing them is noise.
 */
const LISTED: LayerName[] = [LayerName.Dm, LayerName.Tokens, LayerName.Draw, LayerName.Map];

// Bumped after every mutation to re-run the shape walk: layer contents are not
// reactive (see the comment in floors/state.ts), so nothing else would.
const revision = ref(0);

const currentFloorId = computed(() => floorState.reactive.floors[floorState.reactive.floorIndex]?.id);

interface LayerGroup {
    name: LayerName;
    layer: ILayer;
    /** Top-first, i.e. reverse render order. */
    entries: ShapeEntry[];
}

const groups = computed<LayerGroup[]>(() => {
    void revision.value;
    void floorState.reactive.floorIndex;

    const floorId = currentFloorId.value;
    if (floorId === undefined) return [];

    const byLayer = new Map<LayerName, ShapeEntry[]>();
    for (const entry of collectShapes({ floorId, layers: LISTED })) {
        const bucket = byLayer.get(entry.layerName);
        if (bucket === undefined) byLayer.set(entry.layerName, [entry]);
        else bucket.push(entry);
    }

    const floor = floorSystem.getFloor({ id: floorId }, false);
    if (floor === undefined) return [];

    const result: LayerGroup[] = [];
    for (const name of LISTED) {
        const layer = floorSystem.getLayer(floor, name);
        if (layer === undefined) continue;
        result.push({ name, layer, entries: (byLayer.get(name) ?? []).slice().reverse() });
    }
    return result;
});

const selected = computed(() => selectedState.reactive.selected);

function isSelected(id: LocalId): boolean {
    return selected.value.has(id);
}

/** Select a shape and bring the camera to it, the same way markers jump. */
function locate(entry: ShapeEntry): void {
    selectedSystem.set(entry.localId);
    setCenterPosition(entry.shape.center);
    floorSystem.selectFloor({ id: entry.floorId }, true);
}

/** Panel position (top-first) -> layer index (bottom-first). */
function toStackIndex(layer: ILayer, panelIndex: number): number {
    return layer.size({ onlyInView: false }) - 1 - panelIndex;
}

function onReorder(group: LayerGroup, event: SortableEvent): void {
    const { oldIndex, newIndex } = event;
    if (oldIndex === undefined || newIndex === undefined || oldIndex === newIndex) return;

    const entry = group.entries[oldIndex];
    if (entry === undefined) return;

    group.layer.moveShapeOrder(entry.shape, toStackIndex(group.layer, newIndex), SyncMode.FULL_SYNC);
    revision.value++;
}

/**
 * Dropping a row onto a different layer's list.
 *
 * vue-draggable-plus fires `add` on the receiving list; the shape still belongs
 * to its old layer at that point, so the move goes through the same path the
 * context menu uses rather than being poked into the array by hand.
 */
function onAdd(group: LayerGroup, event: SortableEvent): void {
    const entry = (event as DraggableEvent<ShapeEntry>).data;
    if (entry === undefined) return;

    moveLayer([entry.shape], group.layer, true);

    if (event.newIndex !== undefined) {
        group.layer.moveShapeOrder(entry.shape, toStackIndex(group.layer, event.newIndex), SyncMode.FULL_SYNC);
    }
    revision.value++;
}

function sendToBack(group: LayerGroup, entry: ShapeEntry): void {
    group.layer.moveShapeOrder(entry.shape, 0, SyncMode.FULL_SYNC);
    revision.value++;
}

function bringToFront(group: LayerGroup, entry: ShapeEntry): void {
    group.layer.moveShapeOrder(entry.shape, group.layer.size({ onlyInView: false }) - 1, SyncMode.FULL_SYNC);
    revision.value++;
}
</script>

<template>
    <div v-if="visible" id="layer-panel">
        <header>
            <span>Layers</span>
            <button title="Refresh" @click="revision++">&#8635;</button>
            <button title="Close" @click="uiSystem.toggleLayers()">&times;</button>
        </header>

        <div class="body">
            <div v-for="group of groups" :key="group.name" class="layer">
                <div class="layer-header">
                    <span class="layer-name">{{ group.name }}</span>
                    <span class="count">{{ group.entries.length }}</span>
                </div>

                <VueDraggable
                    v-model="group.entries"
                    :group="{ name: 'layer-shapes' }"
                    :animation="120"
                    class="shape-list"
                    @update="(e: SortableEvent) => onReorder(group, e)"
                    @add="(e: SortableEvent) => onAdd(group, e)"
                >
                    <div
                        v-for="entry of group.entries"
                        :key="entry.id"
                        class="shape-row"
                        :class="{ selected: isSelected(entry.localId) }"
                        @click="locate(entry)"
                    >
                        <span class="drag-handle">&#8942;&#8942;</span>
                        <span class="shape-name">{{ entry.name === "" ? "(unnamed)" : entry.name }}</span>
                        <button title="Bring to front" @click.stop="bringToFront(group, entry)">&uarr;</button>
                        <button title="Send to back" @click.stop="sendToBack(group, entry)">&darr;</button>
                    </div>
                </VueDraggable>

                <div v-if="group.entries.length === 0" class="empty">empty</div>
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
#layer-panel {
    position: absolute;
    top: 6rem;
    right: 1.5rem;
    width: 20rem;
    max-height: 70vh;
    display: flex;
    flex-direction: column;
    background-color: white;
    border: solid 1px var(--pa-secondary-light, #7c253e);
    border-radius: 0.5rem;
    box-shadow: 0 0 1rem rgb(0 0 0 / 40%);
    pointer-events: auto;
    z-index: 100;

    header {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.5rem 0.75rem;
        font-weight: bold;
        border-bottom: solid 1px rgb(0 0 0 / 15%);

        span {
            flex: 1;
        }

        button {
            border: none;
            background: none;
            font-size: 1.1rem;
            cursor: pointer;
        }
    }

    .body {
        overflow-y: auto;
        padding: 0.5rem 0.75rem 0.75rem;
    }

    .layer {
        margin-bottom: 0.75rem;
    }

    .layer-header {
        display: flex;
        justify-content: space-between;
        font-weight: bold;
        text-transform: uppercase;
        font-size: 0.75rem;
        opacity: 0.7;
        border-bottom: solid 1px rgb(0 0 0 / 10%);
        margin-bottom: 0.25rem;
    }

    .shape-list {
        min-height: 0.75rem;
    }

    .shape-row {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.15rem 0.25rem;
        border-radius: 0.25rem;
        cursor: pointer;

        &:hover {
            background-color: rgb(0 0 0 / 6%);
        }

        &.selected {
            background-color: var(--pa-secondary-light, #7c253e);
            color: white;
        }

        button {
            border: none;
            background: none;
            cursor: pointer;
            color: inherit;
            opacity: 0.6;

            &:hover {
                opacity: 1;
            }
        }
    }

    .drag-handle {
        cursor: grab;
        opacity: 0.4;
        letter-spacing: -0.15em;
    }

    .shape-name {
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .empty {
        font-size: 0.8rem;
        font-style: italic;
        opacity: 0.6;
    }
}
</style>
