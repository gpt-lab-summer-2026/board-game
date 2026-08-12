// Applying a spell template's condition.
//
// The spell tool works out who a template caught and emits `spell:cast`. It
// deliberately does not apply anything itself -- conditions are this mod's
// concept, and a copy of the rules in the core client is how the two end up
// disagreeing. This is the other half of that seam.

import type { LocalId } from "@planarally/mod-api";

import { findCondition } from "./catalogue";
import type { CharacterSheet } from "./data";
import { SHEET_BLOCK } from "./data";
import { api } from "./main";

async function applyTo(shape: LocalId, conditionId: string): Promise<boolean> {
    const globalId = api.getGlobalId(shape);
    if (globalId === undefined) return false;

    // Only characters have sheets. A spell over a wall is not an error.
    if (api.getShape(shape)?.character === undefined) return false;

    const block = await api.getOrLoadDataBlock<CharacterSheet>({
        category: "shape",
        shape: globalId,
        name: SHEET_BLOCK,
    });
    if (block === undefined) return false;

    const sheet = block.reactiveData.value;
    sheet.conditions ??= [];
    if (sheet.conditions.includes(conditionId)) return false;

    sheet.conditions.push(conditionId);
    block.sync();
    return true;
}

interface SpellCast {
    shapes: LocalId[];
    condition?: string;
}

export function registerSpellHook(): void {
    api.eventBus.on<SpellCast>("spell:cast", (payload) => {
        const conditionId = payload.condition;
        if (conditionId === undefined || findCondition(conditionId) === undefined) return;

        // Fire and forget: the tool has already closed, and making the caster
        // wait on a round-trip per target would stall the cast.
        void Promise.all(payload.shapes.map((id) => applyTo(id, conditionId)));
    });
}
