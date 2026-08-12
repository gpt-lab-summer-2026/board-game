// Right-click on a token: everything the ghost can do.
//
// A shape context menu entry is one of only two UI surfaces a mod gets, and it
// is the right one for per-token actions. Each leaf composes a ghost command
// rather than acting directly -- see ghostbridge.ts for why.

import type { LocalId, Section } from "@planarally/mod-api";

import { catalogue } from "./catalogue";
import { sendCommand } from "./ghostbridge";
import { api } from "./main";

interface Named {
    name: string;
    shapeId: string;
}

function characterName(shape: LocalId): string | undefined {
    const globalId = api.getGlobalId(shape);
    if (globalId === undefined) return undefined;
    for (const character of api.systems.characters.getAllCharacters()) {
        if (character.shapeId === globalId) return character.name;
    }
    return undefined;
}

function others(self: string): Named[] {
    return [...api.systems.characters.getAllCharacters()]
        .filter((c) => c.name !== self)
        .map((c) => ({ name: c.name, shapeId: c.shapeId }));
}

/** A submenu of every other character, each running `build(name)`. */
function targetMenu(title: string, self: string, build: (target: string) => string): Section {
    const targets = others(self);
    if (targets.length === 0) {
        return { title: `${title} — nobody else on the board`, disabled: true, action: () => true };
    }
    return {
        title,
        subitems: targets.map((t) => ({
            title: t.name,
            action: async () => sendCommand(build(t.name)),
        })),
    };
}

export function ghostMenu(shape: LocalId): Section[] {
    const self = characterName(shape);
    if (self === undefined) return [];

    const conditions = catalogue.value.conditions ?? [];

    // Flat rather than nested under one "Ghost" heading: Section is capped
    // at three levels, and "Ghost > Melee attack > target" spends all of
    // them before reaching anything clickable.
    return [
        targetMenu("⚔ Melee attack", self, (t) => `${self} melee attack on ${t}`),
        targetMenu("🏹 Ranged attack", self, (t) => `${self} ranged attack on ${t}`),
        targetMenu("✨ Cantrip", self, (t) => `${self} cantrip on ${t}`),
        targetMenu("⚔ Melee, advantage", self, (t) => `${self} melee attack on ${t} with advantage`),
        targetMenu("🏹 Ranged, disadvantage", self, (t) => `${self} ranged attack on ${t} with disadvantage`),
        targetMenu("→ Move to", self, (t) => `${self} moves to ${t}`),
        targetMenu("⟷ Measure to", self, (t) => `measure from ${self} to ${t}`),
        {
            title: "Apply condition",
            subitems: conditions.map((c) => ({
                title: c.name,
                action: async () => sendCommand(`apply ${c.id} to ${self}`),
            })),
        },
        {
            title: "Clear condition",
            subitems: conditions.map((c) => ({
                title: c.name,
                action: async () => sendCommand(`clear ${c.id} from ${self}`),
            })),
        },
        {
            title: "Duplicate this character",
            action: async () => sendCommand(`duplicate ${self}`),
        },
    ];
}
