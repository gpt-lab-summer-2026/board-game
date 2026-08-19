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
export const ABILITIES = [
    { key: "str", label: "STR", long: "Strength" },
    { key: "dex", label: "DEX", long: "Dexterity" },
    { key: "con", label: "CON", long: "Constitution" },
    { key: "int", label: "INT", long: "Intelligence" },
    { key: "wis", label: "WIS", long: "Wisdom" },
    { key: "cha", label: "CHA", long: "Charisma" },
];
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
];
export const SHEET_BLOCK = "sheet";
/** The pre-0.3.0 block. Still on disk; read once, never written. */
export const LEGACY_BLOCK = "data";
export function emptySheet() {
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
const LEGACY_ABILITY_NAMES = {
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
const LEGACY_SCALARS = {
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
export function importLegacySheet(legacy) {
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
