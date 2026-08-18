// Loading and saving one character's sheet.
//
// PA ships a `useShapeDataBlock` hook that does most of this, but it can only
// load the one block it is told about, and this mod has to look in two places:
// the 0.3.0 `sheet` block, and -- if that doesn't exist yet -- the pre-0.3.0
// `data` block, so an existing character keeps its stats. Hence a local
// composable with the same shape (data / load / save / write) as PA's.

import type { DataBlock, GlobalId, LocalId } from "@planarally/mod-api";
import { ref, shallowReadonly, watch, type Ref } from "vue";

import type { CharData, CharacterSheet } from "./data";
import { LEGACY_BLOCK, SHEET_BLOCK, emptySheet, importLegacySheet } from "./data";
import { api } from "./main";
import { deriveSheet } from "./rules";
import { adoptTrackers, readBackFromTrackers, syncTrackers } from "./trackers";

/**
 * Fill in fields a sheet written by an older build doesn't have.
 *
 * A stored sheet is whatever shape it was when it was saved. Reading a missing
 * nested key gives `undefined`, and `v-model` on `undefined.cantrip` throws --
 * so every field the schema gains has to be tolerated here. Cheap, and it means
 * adding a field later never needs a bespoke migration.
 */
function fillDefaults(sheet: CharacterSheet): boolean {
    const base = emptySheet();
    let changed = false;

    // AC became a derived value in v0.12.0. A sheet written before that has a
    // number somebody typed and no `acOverride`, so adopt it as the override:
    // the character keeps exactly the AC the DM last saw, and nothing silently
    // changes because armour was introduced. Clearing the field in the editor
    // is the deliberate act that opts a character into deriving instead.
    //
    // This runs before the generic pass below, which would otherwise fill
    // `acOverride` with the default `null` and lose the old value.
    if (sheet.acOverride === undefined) {
        sheet.acOverride = typeof sheet.ac === "number" ? sheet.ac : null;
        changed = true;
    }

    for (const [key, value] of Object.entries(base) as [keyof CharacterSheet, unknown][]) {
        if (sheet[key] === undefined) {
            (sheet as Record<string, unknown>)[key] = value;
            changed = true;
        }
    }
    // The nested objects need the same treatment; a v0.3.0 sheet has
    // `equipped` but no `equipped.cantrip`.
    for (const key of ["equipped", "hp", "trackerIds", "abilities", "derived"] as const) {
        for (const [nested, value] of Object.entries(base[key]) as [string, unknown][]) {
            const target = sheet[key] as Record<string, unknown>;
            if (target[nested] === undefined) {
                target[nested] = value;
                changed = true;
            }
        }
    }
    return changed;
}

async function loadBlock(shape: GlobalId): Promise<DataBlock<CharacterSheet> | undefined> {
    const repr = { category: "shape", shape, name: SHEET_BLOCK } as const;

    // Probing without `defaultData` returns undefined when the block does not
    // exist on the server, and records the attempt so the follow-up call below
    // does not make a second round-trip.
    const existing = await api.getOrLoadDataBlock<CharacterSheet>(repr);
    if (existing !== undefined) {
        if (fillDefaults(existing.reactiveData.value)) existing.sync();
        return existing;
    }

    const legacy = await api.getOrLoadDataBlock<CharData>({
        category: "shape",
        shape,
        name: LEGACY_BLOCK,
    });
    const initial = legacy === undefined ? emptySheet() : importLegacySheet(legacy.data);

    // Created locally only. The row is written on the first `sync()`, so merely
    // opening a character's tab does not litter the database with empty sheets
    // -- and the legacy block is left untouched as a fallback either way.
    return await api.getOrLoadDataBlock<CharacterSheet>(repr, { defaultData: () => initial });
}

export function useSheet(): {
    data: Readonly<Ref<CharacterSheet>>;
    load: (shape: GlobalId, localId: LocalId) => Promise<void>;
    save: () => void;
    write: (value: CharacterSheet) => void;
} {
    let block: DataBlock<CharacterSheet> | undefined;
    let shapeId: LocalId | undefined;
    const internal = ref(emptySheet()) as Ref<CharacterSheet>;

    async function load(shape: GlobalId, localId: LocalId): Promise<void> {
        block = undefined;
        shapeId = localId;

        const loaded = await loadBlock(shape);
        if (loaded === undefined) return;

        block = loaded;
        internal.value = loaded.reactiveData.value;
        // A remote save replaces the ref rather than mutating it.
        watch(loaded.reactiveData, (value) => {
            internal.value = value;
        });

        // Claim any HP/AC tracker the token already had before reading values
        // off it -- otherwise adoption would immediately overwrite them.
        const adopted = adoptTrackers(localId, internal.value);
        // The tracker is the live number during play; the sheet catches up.
        const readBack = readBackFromTrackers(localId, internal.value);
        if (adopted || readBack) save();
    }

    function write(value: CharacterSheet): void {
        block?.updateData(value);
    }

    function save(): void {
        if (block === undefined) return;

        // Derived values are recomputed here rather than in the template, so
        // that whatever is on the server is always internally consistent --
        // the ghost reads `derived` without knowing anything about 5e.
        internal.value.derived = deriveSheet(internal.value);
        if (shapeId !== undefined) syncTrackers(shapeId, internal.value);

        block.sync();
    }

    return { data: shallowReadonly(internal), load, save, write };
}
