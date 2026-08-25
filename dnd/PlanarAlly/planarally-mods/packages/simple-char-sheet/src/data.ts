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
/**
 * How long a temporary bonus to AC lasts.
 *
 * `rounds` is decremented by the turn tracker; `manual` sticks until someone
 * removes it. Cover is deliberately absent: it depends on where the attacker is
 * standing, so it is computed per attack rather than stored on the defender.
 */
export type AcDuration = { kind: "manual" } | { kind: "rounds"; remaining: number };

export interface AcModifier {
    id: string;
    /** Shown in the AC breakdown: "Shield spell", "Bless", "half cover". */
    source: string;
    value: number;
    duration: AcDuration;
}

/** The AC sum, itemised, so the editor can show where the number came from. */
export interface DerivedAc {
    total: number;
    /** Armour's base, or 10 unarmoured. */
    base: number;
    /** Dexterity's contribution, after the armour's cap. */
    dex: number;
    shield: number;
    /** Sum of the temporary modifiers. */
    modifiers: number;
    armourName: string | null;
    shieldName: string | null;
    /** True when a hand-typed override is in force and the rest is ignored. */
    overridden: boolean;
    /** 10 if the wearer is too weak for their armour, else 0. */
    speedPenalty: number;
    stealthDisadvantage: boolean;
}

/**
 * The 5e skill list, each tied to the ability it keys off.
 *
 * Kept here rather than in the catalogue because, unlike weapons or spells,
 * this is not content a DM edits -- a campaign that renames Athletics is not a
 * campaign this needs to support.
 */
export const SKILLS = [
    { key: "acrobatics", name: "Acrobatics", ability: "dex" },
    { key: "animal-handling", name: "Animal Handling", ability: "wis" },
    { key: "arcana", name: "Arcana", ability: "int" },
    { key: "athletics", name: "Athletics", ability: "str" },
    { key: "deception", name: "Deception", ability: "cha" },
    { key: "history", name: "History", ability: "int" },
    { key: "insight", name: "Insight", ability: "wis" },
    { key: "intimidation", name: "Intimidation", ability: "cha" },
    { key: "investigation", name: "Investigation", ability: "int" },
    { key: "medicine", name: "Medicine", ability: "wis" },
    { key: "nature", name: "Nature", ability: "int" },
    { key: "perception", name: "Perception", ability: "wis" },
    { key: "performance", name: "Performance", ability: "cha" },
    { key: "persuasion", name: "Persuasion", ability: "cha" },
    { key: "religion", name: "Religion", ability: "int" },
    { key: "sleight-of-hand", name: "Sleight of Hand", ability: "dex" },
    { key: "stealth", name: "Stealth", ability: "dex" },
    { key: "survival", name: "Survival", ability: "wis" },
] as const satisfies readonly { key: string; name: string; ability: AbilityKey }[];

export type SkillKey = (typeof SKILLS)[number]["key"];

/** A carried item and how many are left. */
export interface CarriedItem {
    id: string;
    quantity: number;
}

/** One level of spell slots. */
export interface SlotLevel {
    used: number;
    max: number;
}

/** A prepared spell with its numbers already worked out. */
export interface DerivedSpell {
    id: string;
    name: string;
    level: number;
    kind: string;
    range: string;
    castingTime: string;
    /** Attack notation, for spells that need a roll. */
    attack: string | null;
    attackAdvantage: string | null;
    attackDisadvantage: string | null;
    /** Damage with no ability modifier -- levelled spells do not add one. */
    damage: string | null;
    damageType: string | null;
    /** Healing including the casting modifier, e.g. "1d8+3". */
    healing: string | null;
    save: AbilityKey | null;
    saveDc: number | null;
    halfOnSave: boolean;
    area: { shape: string; size: number } | null;
    concentration: boolean;
    acBonus: { value: number; rounds: number | null } | null;
    text: string;
}

export interface DerivedBlock {
    proficiency: number;
    ac: DerivedAc;
    mods: Record<AbilityKey, number>;
    melee: DerivedAttack | null;
    ranged: DerivedAttack | null;
    cantrip: DerivedCantrip | null;
    /** 8 + proficiency + spell ability modifier, or null with no caster ability. */
    spellSaveDc: number | null;
    /** Every saving throw, with proficiency already folded in. */
    saves: Record<AbilityKey, { bonus: number; proficient: boolean }>;
    /** Every skill, likewise. */
    skills: Record<string, { bonus: number; proficient: boolean; ability: AbilityKey }>;
    /** Prepared spells, resolved against this character's numbers. */
    spells: DerivedSpell[];
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
    /**
     * Effective armour class -- an *output*, rewritten by `deriveSheet` on every
     * save. It stays a plain number on the sheet because the AC tracker and the
     * ghost both read it, and neither should have to know how it was arrived at.
     * To change AC, set `acOverride` or equip armour.
     */
    ac: number;
    /** Hand-typed AC that wins over armour and Dexterity. Null derives. */
    acOverride: number | null;
    /** Temporary bonuses and penalties, itemised so they can be removed by name. */
    acModifiers: AcModifier[];
    speed: number;
    equipped: {
        melee: string | null;
        ranged: string | null;
        cantrip: string | null;
        armour: string | null;
        shield: string | null;
    };
    /** Condition ids currently affecting this creature. */
    conditions: string[];
    /** Prepared/known levelled spells, by catalogue id. */
    spells: string[];
    /**
     * Spell slots by level, keyed by the level as a string because this is
     * JSON on the wire and numeric keys do not survive the round trip intact.
     */
    slots: Record<string, SlotLevel>;
    /** Skill keys this character is proficient in. */
    skillProficiencies: string[];
    /**
     * Consumables, with counts. A list rather than a map because the editor
     * renders it in order and a map's key order is not something to rely on.
     */
    inventory: CarriedItem[];
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
        acOverride: null,
        acModifiers: [],
        speed: 30,
        equipped: { melee: null, ranged: null, cantrip: null, armour: null, shield: null },
        conditions: [],
        spells: [],
        slots: {},
        skillProficiencies: [],
        inventory: [],
        spellAbility: null,
        trackerIds: { hp: null, ac: null },
        derived: {
            proficiency: 2,
            ac: {
                total: 10,
                base: 10,
                dex: 0,
                shield: 0,
                modifiers: 0,
                armourName: null,
                shieldName: null,
                overridden: false,
                speedPenalty: 0,
                stealthDisadvantage: false,
            },
            mods: { str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 },
            melee: null,
            ranged: null,
            cantrip: null,
            spellSaveDc: null,
            skills: {},
            spells: [],
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
