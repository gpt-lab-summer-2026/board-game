// The data this mod stores, and how.
//
// DataBlocks are PA's server-side storage for mods. They come in three scopes --
// User, Room and Shape -- and are keyed by (mod tag, scope, name), with the data
// held as the result of `JSON.stringify`. They are deleted with whatever they
// hang off, so a Shape DataBlock dies with its token.
//
// This mod uses all three ideas in two places:
//
//   shape / "sheet"      one character's stats            (this file)
//   room  / "catalogue"  weapons, races, backgrounds...   (catalogue.ts)
//   room  / "presets"    reusable stat blocks             (presets.ts)
//
// A DataBlock's `.data` is fully mutable and is *not* written back on its own:
// changes only reach the server on an explicit `sync()`. It can also be loaded
// by several clients at once, and a sync pushes the new data to all of them,
// which is why the UI reads through `reactiveData` rather than `data`.

// ---------------------------------------------------------------------------
// Free-form stats -- the original mod's data model, kept for the "Extra" section
// ---------------------------------------------------------------------------

interface Stat<T extends string, V> {
    name: string;
    type: T;
    value: V;
}

export type NumberStat = Stat<"number", number>;
export type StringStat = Stat<"string", string>;
export type CheckStat = Stat<"check", boolean>;
export type StatType = NumberStat | StringStat | CheckStat;

/** The shape of the pre-0.3.0 sheet: a flat list of ad-hoc stats. */
export type CharData = StatType[];

// ---------------------------------------------------------------------------
// The character sheet
// ---------------------------------------------------------------------------

export type AbilityKey = "str" | "dex" | "con" | "int" | "wis" | "cha";

export const ABILITIES: { key: AbilityKey; label: string; long: string }[] = [
    { key: "str", label: "STR", long: "Strength" },
    { key: "dex", label: "DEX", long: "Dexterity" },
    { key: "con", label: "CON", long: "Constitution" },
    { key: "int", label: "INT", long: "Intelligence" },
    { key: "wis", label: "WIS", long: "Wisdom" },
    { key: "cha", label: "CHA", long: "Charisma" },
];

export interface DerivedAttack {
    weapon: string;
    /** Dice notation, e.g. "1d20+5". Ready to hand to a dice roller as-is. */
    attack: string;
    /** The same roll with advantage / disadvantage: "2d20kh1+5" / "2d20kl1+5". */
    attackAdvantage: string;
    attackDisadvantage: string;
    damage: string;
    /** Which ability the bonus came from, so the UI can explain the number. */
    ability: AbilityKey;
    /** Condition inflicted on a hit, resolved from the catalogue so the
     *  ghost never has to look it up again. */
    applies: { condition: string; name: string; save: AbilityKey | null; dc: number | null } | null;
}

export interface DerivedCantrip {
    name: string;
    kind: "attack" | "save";
    /** Scaled for level; empty string is never produced. */
    damage: string;
    damageType: string;
    range: string;
    /** Present when kind is "attack". */
    attack: string | null;
    attackAdvantage: string | null;
    attackDisadvantage: string | null;
    /** Present when kind is "save". */
    save: AbilityKey | null;
    saveDc: number | null;
    applies: { condition: string; name: string; save: AbilityKey | null; dc: number | null } | null;
    /**
     * Whether the "hostile creature within 5 feet" disadvantage applies. False
     * for melee spell attacks like Shocking Grasp, which are supposed to be
     * delivered at touch range.
     */
    closeRangeDisadvantage: boolean;
}

// Written by the mod on every save and never edited by hand.
//
// This exists so the rules live in exactly one place. The ghost player has to
// roll attacks on a player's behalf, and the alternative -- reimplementing 5e
// modifiers in Python -- means two copies of the same arithmetic drifting
// apart, where the first symptom is a voice-rolled attack quietly using the
// wrong bonus. Storing the finished notation keeps the ghost dumb: it reads
// `derived.melee.attack` and rolls the string.
export interface DerivedBlock {
    proficiency: number;
    mods: Record<AbilityKey, number>;
    melee: DerivedAttack | null;
    ranged: DerivedAttack | null;
    cantrip: DerivedCantrip | null;
    /** 8 + proficiency + spell ability modifier, or null with no caster ability. */
    spellSaveDc: number | null;
    /** Every saving throw, with proficiency already folded in. */
    saves: Record<AbilityKey, { bonus: number; proficient: boolean }>;
}

// A `type` rather than an `interface` on purpose: DataBlock's generic is
// constrained to `Record<string, unknown> | unknown[]`, and only type aliases
// get TypeScript's implicit index signature. An interface here fails to
// compile with a fairly opaque "index signature is missing" error.
export type CharacterSheet = {
    version: 1;
    description: string;
    raceId: string | null;
    backgroundId: string | null;
    classId: string | null;
    level: number;
    abilities: Record<AbilityKey, number>;
    hp: { current: number; max: number; temp: number };
    ac: number;
    speed: number;
    equipped: { melee: string | null; ranged: string | null; cantrip: string | null };
    /** Condition ids currently affecting this creature. */
    conditions: string[];
    /**
     * Which ability powers this character's spells. Null means "use the
     * class's", which is the usual case; setting it explicitly is what lets a
     * creature with no caster class still cast something.
     */
    spellAbility: AbilityKey | null;
    /** PA tracker uuids, so repeated saves update rather than pile up. */
    trackerIds: { hp: string | null; ac: string | null };
    derived: DerivedBlock;
    custom: StatType[];
};

/** Everything worth reusing across characters: no current HP, no tracker ids. */
export type SheetPreset = Omit<CharacterSheet, "trackerIds" | "derived">;

export const SHEET_BLOCK = "sheet";
/** The pre-0.3.0 block. Still on disk; read once, never written. */
export const LEGACY_BLOCK = "data";

export function emptySheet(): CharacterSheet {
    return {
        version: 1,
        description: "",
        raceId: null,
        backgroundId: null,
        classId: null,
        level: 1,
        abilities: { str: 10, dex: 10, con: 10, int: 10, wis: 10, cha: 10 },
        hp: { current: 0, max: 0, temp: 0 },
        ac: 10,
        speed: 30,
        equipped: { melee: null, ranged: null, cantrip: null },
        conditions: [],
        spellAbility: null,
        trackerIds: { hp: null, ac: null },
        derived: {
            proficiency: 2,
            mods: { str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 },
            melee: null,
            ranged: null,
            cantrip: null,
            spellSaveDc: null,
            saves: {
                str: { bonus: 0, proficient: false },
                dex: { bonus: 0, proficient: false },
                con: { bonus: 0, proficient: false },
                int: { bonus: 0, proficient: false },
                wis: { bonus: 0, proficient: false },
                cha: { bonus: 0, proficient: false },
            },
        },
        custom: [],
    };
}

// ---------------------------------------------------------------------------
// Migration
// ---------------------------------------------------------------------------

const LEGACY_ABILITY_NAMES: Record<string, AbilityKey> = {
    strength: "str",
    dexterity: "dex",
    constitution: "con",
    intelligence: "int",
    wisdom: "wis",
    charisma: "cha",
    str: "str",
    dex: "dex",
    con: "con",
    int: "int",
    wis: "wis",
    cha: "cha",
};

const LEGACY_SCALARS: Record<string, "ac" | "speed" | "level"> = {
    ac: "ac",
    "armor class": "ac",
    "armour class": "ac",
    speed: "speed",
    level: "level",
};

/**
 * Fold a pre-0.3.0 flat stat list into a structured sheet.
 *
 * Deliberately lossless: anything not recognised as an ability or a known
 * scalar is kept verbatim in `custom`, so a sheet full of homebrew rows
 * survives the upgrade instead of being silently dropped. The legacy block is
 * only ever read -- it stays on disk as a fallback if this mapping is wrong.
 */
export function importLegacySheet(legacy: CharData): CharacterSheet {
    const sheet = emptySheet();

    for (const stat of legacy) {
        const name = stat.name.trim().toLowerCase();

        const ability = LEGACY_ABILITY_NAMES[name];
        if (ability !== undefined && stat.type === "number") {
            sheet.abilities[ability] = stat.value;
            continue;
        }

        const scalar = LEGACY_SCALARS[name];
        if (scalar !== undefined && stat.type === "number") {
            sheet[scalar] = stat.value;
            continue;
        }

        if ((name === "hp" || name === "hit points") && stat.type === "number") {
            sheet.hp.max = stat.value;
            sheet.hp.current = stat.value;
            continue;
        }

        if (name === "description" && stat.type === "string") {
            sheet.description = stat.value;
            continue;
        }

        sheet.custom.push(stat);
    }

    return sheet;
}
