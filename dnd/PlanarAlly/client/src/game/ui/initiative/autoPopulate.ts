/**
 * Rolling a layer of tokens into initiative.
 *
 * Initiative was entirely manual: add each token from its context menu, then
 * type a number for every one of them. With eight combatants that is the slowest
 * minute of the fight, every fight.
 *
 * The dexterity modifier is read from the character sheet mod's DataBlock rather
 * than recomputed here. The mod owns the 5e arithmetic and writes the finished
 * modifiers into `derived.mods` -- ghost/sheet.py leans on the same rule, and for
 * the same reason: two implementations drift, and the symptom would be a token
 * quietly rolling initiative on the wrong modifier.
 */
import type { GlobalId } from "../../../core/id";
import { getOrLoadDataBlock } from "../../dataBlock";

/** The simple-char-sheet mod's DataBlock namespace. */
const SHEET_SOURCE = "scc";
const SHEET_NAME = "sheet";

/**
 * Only the parts of the sheet this file touches.
 *
 * The mod is a separate package and cannot be imported from the core client, so
 * this is a structural echo of `CharacterSheet` in
 * planarally-mods/packages/simple-char-sheet/src/data.ts. Everything is optional:
 * a sheet written by an older version of the mod may predate `derived`.
 */
interface SheetShape {
    abilities?: Partial<Record<"str" | "dex" | "con" | "int" | "wis" | "cha", number>>;
    derived?: {
        mods?: Partial<Record<"str" | "dex" | "con" | "int" | "wis" | "cha", number>>;
    };
}

export function rollD20(): number {
    return Math.floor(Math.random() * 20) + 1;
}

/**
 * The initiative modifier for a token: its DEX mod, or 0 when it has no sheet.
 *
 * A monster dropped on the board without a sheet rolls a flat d20, which is what
 * you would do at the table anyway rather than stopping to stat it out.
 */
export async function initiativeModifier(shape: GlobalId): Promise<number> {
    let sheet: SheetShape | undefined;
    try {
        const block = await getOrLoadDataBlock<never, SheetShape>({
            source: SHEET_SOURCE,
            category: "shape",
            name: SHEET_NAME,
            shape,
        });
        sheet = block?.data;
    } catch {
        // No sheet, an unmigrated room, or the mod is not installed.
        return 0;
    }
    if (sheet === undefined) return 0;

    const derived = sheet.derived?.mods?.dex;
    if (derived !== undefined) return derived;

    // Pre-`derived` sheet. Falling back to the score keeps old rooms working;
    // this is the one place the mod's arithmetic is mirrored, and only for a
    // value the mod would otherwise have written itself.
    const score = sheet.abilities?.dex;
    return score === undefined ? 0 : Math.floor((score - 10) / 2);
}
