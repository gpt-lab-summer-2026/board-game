/**
 * Sides: who is with whom.
 *
 * Stored in a room DataBlock rather than on the shapes themselves, for two
 * reasons. A shape field would need a schema migration, which would collide with
 * upstream's save numbering the next time we merge; and the ghost already reads
 * DataBlocks over the same socket events the browser uses (see ghost/sheet.py),
 * so putting sides here means the voice layer can ask "is this a player
 * character?" without a second source of truth.
 */
import type { GlobalId } from "../../../core/id";
import { registerSystem } from "../../../core/systems";
import type { System } from "../../../core/systems/models";
import { getOrLoadDataBlock } from "../../dataBlock";
import type { DataBlock } from "../../dataBlock/db";

import { factionState } from "./state";
import type { Disposition, Faction, FactionData, FactionId } from "./types";
import { defaultFactionData } from "./types";

const { mutableReactive: $ } = factionState;

const DB_REPR = { source: "pa-factions", category: "room", name: "factions" } as const;

let block: DataBlock<never, FactionData> | undefined;

class FactionSystem implements System {
    clear(): void {
        block = undefined;
        $.data = defaultFactionData();
        $.loaded = false;
    }

    /** Pull the room's sides down. Safe to call more than once. */
    async load(): Promise<void> {
        if (block !== undefined) return;
        block = await getOrLoadDataBlock<never, FactionData>(DB_REPR, {
            createOnServer: true,
            defaultData: defaultFactionData,
            // Someone else's edit arriving over the socket.
            updateCallback: (data) => {
                $.data = data;
                $.loaded = true;
            },
        });
        if (block !== undefined) {
            $.data = block.data;
            $.loaded = true;
        }
    }

    /**
     * Push local edits to the server.
     *
     * Every mutator below funnels through here rather than emitting a
     * fine-grained event per change: the whole block is a few hundred bytes, and
     * one save path means the panel cannot get half-applied on other clients.
     */
    private save(): void {
        if (block === undefined) {
            // The server sends CLEAR on every location load, which runs
            // clearSystems() and drops this block. The panel is already mounted
            // by then, so its onMounted load never runs again and every
            // subsequent save returned here silently -- which is exactly what
            // "the Sides tab doesn't save between loads" looked like from the
            // outside. Reload and write, rather than discarding the edit.
            void this.load().then(() => {
                if (block === undefined) return;
                block.updateData($.data as FactionData);
                block.sync();
            });
            return;
        }
        block.updateData($.data as FactionData);
        block.sync();
    }

    setFaction(shape: GlobalId, faction: FactionId | undefined): void {
        if (faction === undefined) {
            const { [shape]: _dropped, ...rest } = $.data.members;
            $.data = { ...$.data, members: rest };
        } else {
            $.data = { ...$.data, members: { ...$.data.members, [shape]: faction } };
        }
        this.save();
    }

    setProvoked(shape: GlobalId, provoked: boolean): void {
        const current = new Set($.data.provoked);
        if (provoked) current.add(shape);
        else current.delete(shape);
        $.data = { ...$.data, provoked: [...current] };
        this.save();
    }

    addFaction(name: string, disposition: Disposition, colour: string): FactionId {
        // Slug plus a counter: ids end up readable in the DataBlock, which
        // matters when debugging what the ghost saw.
        const base = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "faction";
        let id = base;
        let n = 2;
        while ($.data.factions.some((f) => f.id === id)) id = `${base}-${n++}`;

        $.data = { ...$.data, factions: [...$.data.factions, { id, name, colour, disposition }] };
        this.save();
        return id;
    }

    updateFaction(id: FactionId, patch: Partial<Omit<Faction, "id">>): void {
        $.data = {
            ...$.data,
            factions: $.data.factions.map((f) => (f.id === id ? { ...f, ...patch } : f)),
        };
        this.save();
    }

    removeFaction(id: FactionId): void {
        const members = Object.fromEntries(Object.entries($.data.members).filter(([, f]) => f !== id));
        $.data = {
            ...$.data,
            factions: $.data.factions.filter((f) => f.id !== id),
            members: members as Record<GlobalId, FactionId>,
        };
        this.save();
    }
}

export const factionSystem = new FactionSystem();
registerSystem("factions", factionSystem, false, factionState);

// -- queries ------------------------------------------------------------------
//
// Plain functions rather than methods: these are read by the initiative and
// death-save paths, which have no business holding a system reference.

export function getFaction(shape: GlobalId): Faction | undefined {
    const id = factionState.raw.data.members[shape];
    return id === undefined ? undefined : factionState.raw.data.factions.find((f) => f.id === id);
}

export function isProvoked(shape: GlobalId): boolean {
    return factionState.raw.data.provoked.includes(shape);
}

/**
 * The effective stance of a shape towards the party.
 *
 * A provoked neutral reads as hostile, which is the whole point of the flag --
 * `hamta` attacked by a player should be a valid target for "attack the nearest
 * enemy" without permanently joining the goblins.
 */
export function getDisposition(shape: GlobalId): Disposition | undefined {
    const faction = getFaction(shape);
    if (faction === undefined) return undefined;
    if (faction.disposition !== "party" && isProvoked(shape)) return "hostile";
    return faction.disposition;
}

/** Used by the death-save flow: only party members roll saves, monsters just drop. */
export function isPlayerCharacter(shape: GlobalId): boolean {
    return getFaction(shape)?.disposition === "party";
}

export function areHostile(a: GlobalId, b: GlobalId): boolean {
    const da = getDisposition(a);
    const db = getDisposition(b);
    if (da === undefined || db === undefined) return false;
    const sideA = da === "party" || da === "friendly";
    const sideB = db === "party" || db === "friendly";
    if (da === "neutral" || db === "neutral") return false;
    return sideA !== sideB;
}
