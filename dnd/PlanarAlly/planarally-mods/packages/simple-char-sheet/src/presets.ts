// Reusable stat blocks, shared by every character in the campaign.
//
// The sheet itself lives in a *Shape* DataBlock (see data.ts), which means it is
// bound to one specific token and dies with it. That is right for "this
// goblin's current HP" and wrong for "what a goblin looks like". PA's own
// template mechanism doesn't fill the gap either: templates are attached to the
// *asset* they were saved from, so a template made from one piece of art is
// never offered for another, and they carry no mod DataBlocks regardless.
//
// So presets get their own storage: a single Room DataBlock holding a
// name -> stats map. Room scope is deliberate -- a preset is a property of the
// campaign, not of a token or of whoever happened to type it in. The server
// applies no access rules to DataBlocks beyond room membership, so any player
// can read and write these; that matches how the rest of this mod behaves.

import type { DataBlock } from "@planarally/mod-api";
import { ref, watch, type Ref } from "vue";

import type { CharData, CharacterSheet, SheetPreset } from "./data";
import { importLegacySheet } from "./data";
import { api } from "./main";

// Name -> stat block. A preset holds everything reusable: abilities, race,
// class, equipment, description. It deliberately omits `trackerIds` (those
// belong to one token and reusing them would have two characters fighting over
// the same tracker row) and `derived` (recomputed on save from the rest).
export type PresetLibrary = Record<string, SheetPreset>;

const BLOCK_NAME = "presets";

let block: DataBlock<PresetLibrary> | undefined;
let pending: Promise<DataBlock<PresetLibrary> | undefined> | undefined;

// Mirrors the block's contents so the UI has something to render before (or
// without) the block existing, and so remote saves by other clients show up.
// Same pattern as PA's own `useShapeDataBlock` hook.
const library = ref<PresetLibrary>({});

export const presetLibrary: Readonly<Ref<PresetLibrary>> = library;

export function ensurePresets(): Promise<DataBlock<PresetLibrary> | undefined> {
    // Memoised, and that matters: `getOrLoadDataBlock` only de-duplicates once
    // its round-trip to the server has finished, so two callers racing on mount
    // would both start a load and the loser would be told the block already
    // exists and handed `undefined`.
    pending ??= load();
    return pending;
}

async function load(): Promise<DataBlock<PresetLibrary> | undefined> {
    // No `createOnServer`: with only `defaultData` the block is created locally
    // and `sync()` writes it out the first time someone actually saves a
    // preset, so a campaign that never touches presets never grows a row.
    const dataBlock = await api.getOrLoadDataBlock<PresetLibrary>(
        { category: "room", name: BLOCK_NAME },
        { defaultData: () => ({}) },
    );
    if (dataBlock !== undefined) {
        block = dataBlock;
        if (migrateLegacyEntries(dataBlock.reactiveData.value)) dataBlock.sync();
        library.value = dataBlock.reactiveData.value;
        // A remote save replaces the whole ref rather than mutating it.
        watch(dataBlock.reactiveData, (value) => {
            if (migrateLegacyEntries(value)) dataBlock.sync();
            library.value = value;
        });
    }
    return dataBlock;
}

/**
 * Upgrade presets saved by 0.2.0, which stored a flat `StatType[]`.
 *
 * Without this, applying such a preset would spread an array into an object and
 * write `{"0": {...}, "1": {...}}` over a character's sheet -- silent, and
 * destructive. Done in place and synced, so it happens once.
 */
function migrateLegacyEntries(entries: PresetLibrary): boolean {
    let changed = false;
    for (const [name, value] of Object.entries(entries)) {
        if (!Array.isArray(value)) continue;
        const { trackerIds: _t, derived: _d, ...preset } = importLegacySheet(value as unknown as CharData);
        entries[name] = preset;
        changed = true;
    }
    return changed;
}

// Presets and sheets must never share array instances: if they did, typing a
// new Strength on one goblin would silently rewrite the preset every other
// goblin loads from. The data is plain JSON, so a round-trip is both a deep
// copy and a way to shed the Vue proxy that wraps the stored copy.
function detach<T>(value: T): T {
    return JSON.parse(JSON.stringify(value)) as T;
}

/** Strip the parts of a sheet that belong to one specific token. */
export function toPreset(sheet: CharacterSheet): SheetPreset {
    const { trackerIds: _trackerIds, derived: _derived, ...preset } = detach(sheet);
    return preset;
}

export function getPreset(name: string): SheetPreset | undefined {
    const stats = library.value[name];
    return stats === undefined ? undefined : detach(stats);
}

export async function savePreset(name: string, stats: SheetPreset): Promise<boolean> {
    const dataBlock = block ?? (await ensurePresets());
    if (dataBlock === undefined) return false;

    // Mutating through `reactiveData` rather than `data` -- the proxy writes
    // through to the raw object that `sync()` serialises, while the reverse is
    // not true and would leave every other open sheet showing stale presets.
    dataBlock.reactiveData.value[name] = detach(stats);
    dataBlock.sync();
    return true;
}

export async function deletePreset(name: string): Promise<boolean> {
    const dataBlock = block ?? (await ensurePresets());
    if (dataBlock === undefined || !(name in dataBlock.reactiveData.value)) return false;

    delete dataBlock.reactiveData.value[name];
    dataBlock.sync();
    return true;
}
