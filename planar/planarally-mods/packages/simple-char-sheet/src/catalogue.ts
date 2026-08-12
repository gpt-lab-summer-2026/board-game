// The campaign's list of weapons, races, backgrounds and classes.
//
// Lives in a Room DataBlock rather than in this file, seeded from the defaults
// below the first time anything asks for it. Two reasons that's worth the extra
// machinery over a plain const:
//
//  - the DM can add a weapon or reword a passive mid-session, without a mod
//    rebuild / re-upload / relink / browser reload cycle;
//  - the ghost player reads the same block over the socket, so voice commands
//    like "attack with the longsword" resolve against the campaign's actual
//    weapon list instead of a second copy of it in Python that has to be kept
//    in step.
//
// The default content is 5e SRD-flavoured. The SRD is CC-BY-4.0: fine here,
// but it would need attribution if this mod were ever distributed.

import type { DataBlock } from "@planarally/mod-api";
import { ref, watch, type Ref } from "vue";

import type { AbilityKey } from "./data";
import { api } from "./main";

export type WeaponKind = "melee" | "ranged";

export interface Weapon {
    id: string;
    name: string;
    kind: WeaponKind;
    /** Dice notation without the ability modifier, e.g. "1d8". */
    damage: string;
    damageType: string;
    /** Melee weapons flagged finesse may use DEX instead of STR. */
    finesse?: boolean;
    /** Normal/long range in feet, ranged weapons only. */
    range?: string;
    properties?: string[];
    /**
     * A condition this weapon inflicts on a hit.
     *
     * Applying it as part of the attack rather than as a second command is
     * the point: at a table nobody says "I hit" and then separately "and it
     * is bleeding" -- the effect is part of the blow. `save` makes it
     * resistible; without one it simply lands.
     */
    applies?: { condition: string; save?: AbilityKey };
    /**
     * Claws, bite, hooves -- part of the creature rather than carried gear.
     * Listed separately in the picker so a bear isn't rummaging through a
     * weapon rack, but not restricted by class: a DM may well want a bear that
     * throws a javelin.
     */
    natural?: boolean;
}

/**
 * A cantrip.
 *
 * Modelled on the ranged weapon rules, as asked: an attack roll against AC,
 * damage on a hit, and -- because a spell attack is a ranged attack --
 * disadvantage when a hostile creature is within 5 feet. Save-based cantrips
 * exist too and roll no attack at all, so `kind` distinguishes them rather than
 * pretending every cantrip is an attack.
 */
export interface Cantrip {
    id: string;
    name: string;
    /** Class ids that can learn it. A wizard should not be offered
     *  Sacred Flame, and a fighter should not be offered anything. */
    classes: string[];
    kind: "attack" | "save";
    /** Dice at level 1. Cantrips scale at 5/11/17; see rules.ts. */
    damage: string;
    damageType: string;
    /** Range in feet, or "touch". */
    range: string;
    /** Melee spell attacks (touch range) don't take the close-range penalty. */
    melee?: boolean;
    /** For `kind: "save"`, which ability the target rolls. */
    save?: AbilityKey;
    /** A condition the cantrip inflicts. */
    applies?: { condition: string; save?: AbilityKey };
    text: string;
}

/**
 * A condition a creature can be under.
 *
 * PlanarAlly has no concept of these at all -- it tracks `is_defeated` and
 * nothing else -- so the whole vocabulary is defined here. `impliesDefeated`
 * is the one hook into PA's own state: an unconscious creature should show
 * the defeated marker without anyone having to set it twice.
 */
export interface Condition {
    id: string;
    name: string;
    text: string;
    /** Short label for the token badge. */
    short: string;
    impliesDefeated?: boolean;
}

export interface Passive {
    name: string;
    text: string;
}

export interface Trait {
    id: string;
    name: string;
    passive: Passive;
}

export interface ClassDef extends Trait {
    hitDie: number;
    /** What this class gains at 2nd level. The campaign stops there. */
    level2?: Passive;
    primaryAbility: AbilityKey;
    savingThrows: AbilityKey[];
    /**
     * Which ability powers this class's spells. Absent for non-casters, which
     * is not the same as "cannot cast": the sheet can override it, so a bear
     * with a strange gift is a matter of picking an ability, not of editing
     * the class.
     */
    spellcastingAbility?: AbilityKey;
}

/**
 * Bump when the defaults gain content that existing campaigns should receive.
 * v2 added natural weapons, the Beast class and cantrips.
 * v3 added level-2 class features and per-class spell lists.
 * v4 added conditions.
 * v5 added weapon/cantrip `applies`, plus bleeding and slowed.
 * v6 dropped the Lacerating blade: weapon actions are derived from damage
 *    type in rules.ts, so every sword gets Lacerate without an entry.
 */
export const CATALOGUE_VERSION = 6;

// A `type`, not an `interface` -- see the note on CharacterSheet in data.ts.
export type Catalogue = {
    version: number;
    weapons: Weapon[];
    races: Trait[];
    backgrounds: Trait[];
    classes: ClassDef[];
    cantrips: Cantrip[];
    conditions: Condition[];
};

const BLOCK_NAME = "catalogue";

export function defaultCatalogue(): Catalogue {
    return {
        version: CATALOGUE_VERSION,
        weapons: [
            { id: "longsword", name: "Longsword", kind: "melee", damage: "1d8", damageType: "slashing", properties: ["versatile (1d10)"] },
            { id: "dagger", name: "Dagger", kind: "melee", damage: "1d4", damageType: "piercing", finesse: true, properties: ["light", "thrown (20/60)"] },
            { id: "greataxe", name: "Greataxe", kind: "melee", damage: "1d12", damageType: "slashing", properties: ["heavy", "two-handed"] },
            { id: "rapier", name: "Rapier", kind: "melee", damage: "1d8", damageType: "piercing", finesse: true },
            { id: "quarterstaff", name: "Quarterstaff", kind: "melee", damage: "1d6", damageType: "bludgeoning", properties: ["versatile (1d8)"] },

            { id: "shortbow", name: "Shortbow", kind: "ranged", damage: "1d6", damageType: "piercing", range: "80/320", properties: ["two-handed"] },
            { id: "light-crossbow", name: "Light crossbow", kind: "ranged", damage: "1d8", damageType: "piercing", range: "80/320", properties: ["loading", "two-handed"] },
            { id: "sling", name: "Sling", kind: "ranged", damage: "1d4", damageType: "bludgeoning", range: "30/120" },
            { id: "javelin", name: "Javelin", kind: "ranged", damage: "1d6", damageType: "piercing", range: "30/120", properties: ["thrown"] },

            // Natural weapons, for creatures rather than adventurers. The
            // numbers are a brown bear's.
            { id: "claws", name: "Claws", kind: "melee", damage: "2d6", damageType: "slashing", natural: true },
            { id: "bite", name: "Bite", kind: "melee", damage: "1d8", damageType: "piercing", natural: true },
            { id: "hooves", name: "Hooves", kind: "melee", damage: "1d6", damageType: "bludgeoning", natural: true },
        ],
        races: [
            { id: "human", name: "Human", passive: { name: "Versatile", text: "+1 to every ability score." } },
            { id: "dwarf", name: "Dwarf", passive: { name: "Dwarven Resilience", text: "Darkvision 60 ft. Advantage on saves against poison, and resistance to poison damage." } },
            { id: "elf", name: "Elf", passive: { name: "Fey Ancestry", text: "Darkvision 60 ft. Advantage on saves against being charmed, and magic cannot put you to sleep." } },
            { id: "halfling", name: "Halfling", passive: { name: "Lucky", text: "When you roll a 1 on an attack, ability check or save, reroll and use the new result." } },
            { id: "half-orc", name: "Half-Orc", passive: { name: "Relentless Endurance", text: "When dropped to 0 hit points without being killed outright, drop to 1 instead. Once per long rest." } },
        ],
        backgrounds: [
            { id: "soldier", name: "Soldier", passive: { name: "Military Rank", text: "Soldiers loyal to your former organisation recognise your authority and defer to it." } },
            { id: "acolyte", name: "Acolyte", passive: { name: "Shelter of the Faithful", text: "You and your companions can expect free healing and care at temples of your faith." } },
            { id: "criminal", name: "Criminal", passive: { name: "Criminal Contact", text: "You have a reliable contact in the underworld and know how to get messages to them." } },
            { id: "sage", name: "Sage", passive: { name: "Researcher", text: "When you don't know something, you usually know where and from whom to find it out." } },
            { id: "folk-hero", name: "Folk Hero", passive: { name: "Rustic Hospitality", text: "Commoners will shelter and hide you, short of risking their lives." } },
        ],
        classes: [
            { id: "fighter", name: "Fighter", hitDie: 10, primaryAbility: "str", savingThrows: ["str", "con"], passive: { name: "Second Wind", text: "As a bonus action, regain 1d10 + level hit points. Once per short rest." }, level2: { name: "Action Surge", text: "On your turn you can take one additional action. Once per short rest." } },
            { id: "rogue", name: "Rogue", hitDie: 8, primaryAbility: "dex", savingThrows: ["dex", "int"], passive: { name: "Sneak Attack", text: "Once per turn, deal an extra 1d6 damage to a target you have advantage against." }, level2: { name: "Cunning Action", text: "A bonus action each turn to Dash, Disengage or Hide." } },
            { id: "wizard", name: "Wizard", hitDie: 6, primaryAbility: "int", savingThrows: ["int", "wis"], spellcastingAbility: "int", passive: { name: "Arcane Recovery", text: "Once per day on a short rest, recover spell slots totalling half your level, rounded up." }, level2: { name: "Arcane Tradition", text: "Choose a school of magic; it grants features now and at higher levels." } },
            { id: "cleric", name: "Cleric", hitDie: 8, primaryAbility: "wis", savingThrows: ["wis", "cha"], spellcastingAbility: "wis", passive: { name: "Divine Domain", text: "Your chosen domain grants extra spells and a domain feature at 1st level." }, level2: { name: "Channel Divinity", text: "Turn Undead, plus one effect from your domain. Once per short rest." } },
            { id: "barbarian", name: "Barbarian", hitDie: 12, primaryAbility: "str", savingThrows: ["str", "con"], passive: { name: "Rage", text: "Advantage on Strength checks and saves, bonus melee damage, and resistance to physical damage." }, level2: { name: "Reckless Attack", text: "Advantage on melee Strength attacks this turn; attacks against you have it too." } },

            // For animal companions and monsters: a statline with no gear.
            { id: "beast", name: "Beast", hitDie: 10, primaryAbility: "str", savingThrows: ["str", "con"], passive: { name: "Keen Smell", text: "Advantage on Wisdom (Perception) checks that rely on smell. Fights with natural weapons and carries no equipment." }, level2: { name: "Pack Tactics", text: "Advantage on an attack if an ally is within 5 feet of the target." } },
        ],
        conditions: [
            { id: "bleeding", name: "Bleeding", short: "BLD", text: "Takes 1d4 damage at the start of each of its turns until someone spends an action to staunch it." },
            { id: "slowed", name: "Slowed", short: "SLOW", text: "Speed reduced by 10 feet until the end of the attacker's next turn." },
            { id: "blinded", name: "Blinded", short: "BLND", text: "Can't see and automatically fails sight checks. Attacks against it have advantage; its own have disadvantage." },
            { id: "charmed", name: "Charmed", short: "CHRM", text: "Can't attack the charmer, who has advantage on social checks against it." },
            { id: "frightened", name: "Frightened", short: "FEAR", text: "Disadvantage while the source is in sight, and can't willingly move closer to it." },
            { id: "grappled", name: "Grappled", short: "GRAP", text: "Speed is 0 and cannot benefit from any bonus to speed." },
            { id: "poisoned", name: "Poisoned", short: "PSN", text: "Disadvantage on attack rolls and ability checks." },
            { id: "prone", name: "Prone", short: "PRNE", text: "Disadvantage on attacks. Attacks within 5 ft have advantage against it; further away, disadvantage." },
            { id: "restrained", name: "Restrained", short: "RSTR", text: "Speed 0. Attacks against it have advantage, its own have disadvantage, and DEX saves have disadvantage." },
            { id: "stunned", name: "Stunned", short: "STUN", text: "Incapacitated, can't move, and fails STR and DEX saves. Attacks against it have advantage." },
            { id: "unconscious", name: "Unconscious", short: "UNC", text: "Incapacitated, prone, and unaware. Attacks within 5 ft are critical hits.", impliesDefeated: true },
        ],
        cantrips: [
            { id: "fire-bolt", name: "Fire Bolt", classes: ["wizard"], kind: "attack", damage: "1d10", damageType: "fire", range: "120", text: "A mote of fire hurled at a target. Flammable objects not being worn or carried are ignited." },
            { id: "eldritch-blast", name: "Eldritch Blast", classes: ["wizard"], kind: "attack", damage: "1d10", damageType: "force", range: "120", text: "A beam of crackling energy." },
            { id: "ray-of-frost", name: "Ray of Frost", classes: ["wizard"], kind: "attack", damage: "1d8", damageType: "cold", range: "60", applies: { condition: "slowed" }, text: "On a hit, the target's speed is reduced by 10 feet until your next turn." },
            { id: "shocking-grasp", name: "Shocking Grasp", classes: ["wizard"], kind: "attack", damage: "1d8", damageType: "lightning", range: "touch", melee: true, text: "A melee spell attack. On a hit the target can't take reactions until its next turn. Advantage if it wears metal armour." },
            { id: "sacred-flame", name: "Sacred Flame", classes: ["cleric"], kind: "save", damage: "1d8", damageType: "radiant", range: "60", save: "dex", applies: { condition: "blinded", save: "con" }, text: "No attack roll: the target makes a Dexterity save, taking damage on a failure. Cover gives no benefit." },
        ],
    };
}

let block: DataBlock<Catalogue> | undefined;
let pending: Promise<DataBlock<Catalogue> | undefined> | undefined;

const current = ref<Catalogue>(defaultCatalogue());

export const catalogue: Readonly<Ref<Catalogue>> = current;

export function ensureCatalogue(): Promise<DataBlock<Catalogue> | undefined> {
    // Memoised for the same reason as the preset library: getOrLoadDataBlock
    // only de-duplicates after its round-trip, so two callers racing on mount
    // would both issue a load and the loser would be handed `undefined`.
    pending ??= load();
    return pending;
}

async function load(): Promise<DataBlock<Catalogue> | undefined> {
    const dataBlock = await api.getOrLoadDataBlock<Catalogue>(
        { category: "room", name: BLOCK_NAME },
        { defaultData: defaultCatalogue },
    );
    if (dataBlock !== undefined) {
        block = dataBlock;
        if (migrate(dataBlock.reactiveData.value)) dataBlock.sync();
        current.value = dataBlock.reactiveData.value;
        watch(dataBlock.reactiveData, (value) => {
            if (migrate(value)) dataBlock.sync();
            current.value = value;
        });
    }
    return dataBlock;
}

/**
 * Bring a campaign's stored catalogue up to the current defaults.
 *
 * Additive only, and keyed on id: content the DM added or edited is left alone,
 * and entries they deliberately deleted stay deleted on later loads because the
 * version has already been bumped. Without this, a campaign that had opened the
 * character tab under v1 would have a `cantrips` key that simply isn't there,
 * and the Spellcasting section would iterate `undefined`.
 */
function migrate(cat: Catalogue): boolean {
    if ((cat.version ?? 1) >= CATALOGUE_VERSION) return false;
    const defaults = defaultCatalogue();

    cat.weapons ??= [];
    cat.races ??= [];
    cat.backgrounds ??= [];
    cat.classes ??= [];
    cat.cantrips ??= [];
    cat.conditions ??= [];

    addMissing(cat.weapons, defaults.weapons);
    addMissing(cat.classes, defaults.classes);
    addMissing(cat.cantrips, defaults.cantrips);
    addMissing(cat.conditions, defaults.conditions);

    // v1 shipped Wizard and Cleric without a spellcasting ability, so cantrips
    // would have found no ability to cast with.
    for (const klass of cat.classes) {
        if (klass.spellcastingAbility !== undefined) continue;
        const fresh = defaults.classes.find((c) => c.id === klass.id);
        if (fresh?.spellcastingAbility !== undefined) klass.spellcastingAbility = fresh.spellcastingAbility;
    }

    cat.version = CATALOGUE_VERSION;
    return true;
}

function addMissing<T extends { id: string }>(existing: T[], defaults: T[]): void {
    const known = new Set(existing.map((e) => e.id));
    for (const entry of defaults) if (!known.has(entry.id)) existing.push(entry);
}

export function saveCatalogue(): void {
    // First call also creates the row on the server; `sync()` handles that.
    block?.sync();
}

// ---- lookups ---------------------------------------------------------------
//
// All tolerant of a missing id: a sheet can outlive the catalogue entry it
// points at (someone deletes a weapon), and that should blank the attack row,
// not break the panel.

export function findWeapon(id: string | null): Weapon | undefined {
    return id === null ? undefined : current.value.weapons.find((w) => w.id === id);
}

export function weaponsOfKind(kind: WeaponKind): Weapon[] {
    return current.value.weapons.filter((w) => w.kind === kind);
}

/** Split by carried vs natural, so the picker can group them. */
export function weaponGroups(kind: WeaponKind): { carried: Weapon[]; natural: Weapon[] } {
    const all = weaponsOfKind(kind);
    return {
        carried: all.filter((w) => w.natural !== true),
        natural: all.filter((w) => w.natural === true),
    };
}

export function findCondition(id: string): Condition | undefined {
    return current.value.conditions.find((c) => c.id === id);
}

export function findCantrip(id: string | null): Cantrip | undefined {
    return id === null ? undefined : current.value.cantrips.find((c) => c.id === id);
}

export function findRace(id: string | null): Trait | undefined {
    return id === null ? undefined : current.value.races.find((r) => r.id === id);
}

export function findBackground(id: string | null): Trait | undefined {
    return id === null ? undefined : current.value.backgrounds.find((b) => b.id === id);
}

export function findClass(id: string | null): ClassDef | undefined {
    return id === null ? undefined : current.value.classes.find((c) => c.id === id);
}
