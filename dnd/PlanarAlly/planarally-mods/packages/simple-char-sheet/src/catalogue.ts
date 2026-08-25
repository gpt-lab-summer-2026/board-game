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
/**
 * Armour weights, which differ only in how much Dexterity they let through.
 * A shield is not a weight in 5e, but it sits in the same table here because
 * it is the other thing that occupies an armour slot and adds to AC.
 */
export type ArmourWeight = "light" | "medium" | "heavy" | "shield";

export interface Armour {
    id: string;
    name: string;
    weight: ArmourWeight;
    /** Base AC before Dexterity. For a shield, the bonus it adds instead. */
    baseAc: number;
    /**
     * How much of the Dexterity modifier reaches AC.
     *
     * `null` is uncapped (light armour and no armour), `0` lets none through
     * (heavy), and a number caps it (medium, at 2). Storing the cap rather than
     * branching on `weight` means a homebrew breastplate that allows +3 is a
     * catalogue edit and not a code change.
     */
    dexCap: number | null;
    /** Minimum Strength score; below it, speed drops by 10 feet. */
    strength?: number;
    stealthDisadvantage?: boolean;
    /** Scales, thick hide, chitin -- worn by the creature, not put on. */
    natural?: boolean;
}

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
/**
 * How a level-1 spell resolves.
 *
 * Cantrips get their own type because they never consume a slot and their dice
 * scale with character level; a levelled spell instead spends from a pool and
 * scales by being cast from a higher slot. Keeping them apart avoids a single
 * type where half the fields are meaningless in either direction.
 */
export type SpellKind = "attack" | "save" | "auto" | "heal" | "buff";

export type AreaShape = "cone" | "cube" | "sphere" | "line";

export interface Spell {
    id: string;
    name: string;
    /** Slot level. Only 1 exists so far; the field is here so 2 is a data edit. */
    level: number;
    classes: string[];
    kind: SpellKind;
    /** Damage dice before any modifier. */
    damage?: string;
    damageType?: string;
    /** Healing dice; the casting ability modifier is added on top. */
    healing?: string;
    range: string;
    /** For `kind: "save"`, the ability the target rolls. */
    save?: AbilityKey;
    /** Area damage usually still does half on a successful save. */
    halfOnSave?: boolean;
    area?: { shape: AreaShape; size: number };
    /**
     * A temporary armour class change, in the same shape the sheet stores.
     * `rounds: null` means it lasts until dismissed, which is how the editor
     * renders a concentration effect with no fixed timer.
     */
    acBonus?: { value: number; rounds: number | null };
    concentration?: boolean;
    duration?: string;
    /** Not every spell costs an action. */
    castingTime?: "action" | "bonus" | "reaction";
    applies?: { condition: string; save?: AbilityKey };
    text: string;
}

/**
 * Something a character carries and can use up.
 *
 * Separate from weapons and armour because the defining property is the
 * *charge*: a potion that has been drunk is gone, and the interesting state is
 * how many are left rather than what its statistics are.
 */
export type ItemKind = "potion" | "grenade" | "utility";

export interface Item {
    id: string;
    name: string;
    kind: ItemKind;
    /** Healing dice; the drinker's ability modifier is NOT added. */
    healing?: string;
    /** Damage dice for a thrown item. */
    damage?: string;
    damageType?: string;
    /** Thrown range in feet. */
    range?: number;
    /** Radius in feet for anything that goes off in an area. */
    area?: number;
    /** Ability the target rolls to avoid it, if any. */
    save?: AbilityKey;
    /** A condition it inflicts on everything caught in it. */
    applies?: { condition: string; save?: AbilityKey };
    /** Costs a bonus action rather than an action. */
    bonusAction?: boolean;
    text: string;
}

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
 * v7 added armour and shields, so AC derives from gear and Dexterity instead
 *    of being a number somebody typed.
 * v8 added levelled spells and slots for wizard and cleric.
 * v9 added consumable items: potions, grenades and utility drops.
 * v10 added Ice Knife.
 */
export const CATALOGUE_VERSION = 10;

// A `type`, not an `interface` -- see the note on CharacterSheet in data.ts.
export type Catalogue = {
    version: number;
    weapons: Weapon[];
    armour: Armour[];
    races: Trait[];
    backgrounds: Trait[];
    classes: ClassDef[];
    cantrips: Cantrip[];
    spells: Spell[];
    items: Item[];
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
        armour: [
            { id: "padded", name: "Padded", weight: "light", baseAc: 11, dexCap: null, stealthDisadvantage: true },
            { id: "leather", name: "Leather", weight: "light", baseAc: 11, dexCap: null },
            { id: "studded-leather", name: "Studded leather", weight: "light", baseAc: 12, dexCap: null },

            { id: "hide", name: "Hide", weight: "medium", baseAc: 12, dexCap: 2 },
            { id: "chain-shirt", name: "Chain shirt", weight: "medium", baseAc: 13, dexCap: 2 },
            { id: "scale-mail", name: "Scale mail", weight: "medium", baseAc: 14, dexCap: 2, stealthDisadvantage: true },
            { id: "half-plate", name: "Half plate", weight: "medium", baseAc: 15, dexCap: 2, stealthDisadvantage: true },

            { id: "ring-mail", name: "Ring mail", weight: "heavy", baseAc: 14, dexCap: 0, stealthDisadvantage: true },
            { id: "chain-mail", name: "Chain mail", weight: "heavy", baseAc: 16, dexCap: 0, strength: 13, stealthDisadvantage: true },
            { id: "splint", name: "Splint", weight: "heavy", baseAc: 17, dexCap: 0, strength: 15, stealthDisadvantage: true },
            { id: "plate", name: "Plate", weight: "heavy", baseAc: 18, dexCap: 0, strength: 15, stealthDisadvantage: true },

            { id: "shield", name: "Shield", weight: "shield", baseAc: 2, dexCap: null },

            // For the Beast class and monsters: armour that cannot be removed.
            { id: "thick-hide", name: "Thick hide", weight: "medium", baseAc: 12, dexCap: 2, natural: true },
            { id: "scaled-hide", name: "Scaled hide", weight: "heavy", baseAc: 15, dexCap: 0, natural: true },
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
        items: [
            {
                id: "healing-potion", name: "Potion of Healing", kind: "potion",
                healing: "2d4+2",
                text: "Restores 2d4+2 hit points. Drinking one takes an action; the roll gets no ability modifier.",
            },
            {
                id: "greater-healing-potion", name: "Potion of Greater Healing", kind: "potion",
                healing: "4d4+4",
                text: "Restores 4d4+4 hit points.",
            },
            {
                id: "smokepowder-bomb", name: "Smokepowder Bomb", kind: "grenade",
                damage: "3d6", damageType: "fire", range: 60, area: 10, save: "dex",
                text: "Thrown. Everything within 10 feet makes a Dexterity save, taking 3d6 fire on a failure and half on a success.",
            },
            {
                id: "smoke-flask", name: "Smoke Flask", kind: "grenade",
                range: 40, area: 15, applies: { condition: "blinded" },
                text: "Bursts into a 15 foot cloud. Anything inside is blinded until it leaves.",
            },
            {
                id: "alchemists-fire", name: "Alchemist's Fire", kind: "grenade",
                damage: "1d4", damageType: "fire", range: 20, save: "dex",
                applies: { condition: "bleeding", save: "dex" },
                text: "A ranged attack. On a hit the target burns for 1d4 at the start of each of its turns until someone puts it out.",
            },
            {
                id: "caltrops", name: "Caltrops", kind: "utility",
                range: 10, area: 5, save: "dex", applies: { condition: "slowed", save: "dex" },
                text: "Scattered over a 5 foot square. Anything entering makes a Dexterity save or has its speed cut until it is healed.",
            },
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
        spells: [
            // -- Wizard ------------------------------------------------------
            {
                id: "magic-missile", name: "Magic Missile", level: 1, classes: ["wizard"], kind: "auto",
                damage: "3d4+3", damageType: "force", range: "120",
                text: "Three darts of force, each hitting for 1d4+1. No attack roll and no save: the darts simply strike.",
            },
            {
                id: "burning-hands", name: "Burning Hands", level: 1, classes: ["wizard"], kind: "save",
                damage: "3d6", damageType: "fire", range: "self", save: "dex", halfOnSave: true,
                area: { shape: "cone", size: 15 },
                text: "A cone of flame. Each creature in it makes a Dexterity save for half. Unattended flammable objects catch fire.",
            },
            {
                id: "thunderwave", name: "Thunderwave", level: 1, classes: ["wizard"], kind: "save",
                damage: "2d8", damageType: "thunder", range: "self", save: "con", halfOnSave: true,
                area: { shape: "cube", size: 15 },
                text: "A wave of force. On a failed Constitution save a creature is also pushed 10 feet away.",
            },
            {
                id: "chromatic-orb", name: "Chromatic Orb", level: 1, classes: ["wizard"], kind: "attack",
                damage: "3d8", damageType: "chosen", range: "90",
                text: "A hurled orb of one chosen energy type: acid, cold, fire, lightning, poison or thunder.",
            },
            {
                id: "ice-knife", name: "Ice Knife", level: 1, classes: ["wizard"], kind: "save",
                damage: "2d6", damageType: "cold", range: "60", save: "dex",
                area: { shape: "sphere", size: 5 },
                text: "A shard of ice strikes one creature for 1d10 piercing, then bursts: everything within 5 feet makes a Dexterity save against 2d6 cold.",
            },
            {
                id: "shield-spell", name: "Shield", level: 1, classes: ["wizard"], kind: "buff",
                range: "self", castingTime: "reaction", acBonus: { value: 5, rounds: 1 },
                duration: "until the start of your next turn",
                text: "A reaction, cast when you are hit: +5 AC, which can turn the triggering hit into a miss.",
            },

            // -- Cleric ------------------------------------------------------
            {
                id: "cure-wounds", name: "Cure Wounds", level: 1, classes: ["cleric"], kind: "heal",
                healing: "1d8", range: "touch",
                text: "A touch restores 1d8 plus your spellcasting modifier. No effect on constructs or undead.",
            },
            {
                id: "healing-word", name: "Healing Word", level: 1, classes: ["cleric"], kind: "heal",
                healing: "1d4", range: "60", castingTime: "bonus",
                text: "A bonus action at range: 1d4 plus your spellcasting modifier. The usual way to get somebody off death saves.",
            },
            {
                id: "guiding-bolt", name: "Guiding Bolt", level: 1, classes: ["cleric"], kind: "attack",
                damage: "4d6", damageType: "radiant", range: "120",
                text: "A ranged spell attack. On a hit the next attack roll against the target has advantage.",
            },
            {
                id: "bless", name: "Bless", level: 1, classes: ["cleric"], kind: "buff",
                range: "30", concentration: true, duration: "1 minute",
                text: "Up to three creatures add 1d4 to every attack roll and saving throw while you concentrate.",
            },
            {
                id: "shield-of-faith", name: "Shield of Faith", level: 1, classes: ["cleric"], kind: "buff",
                range: "60", concentration: true, duration: "10 minutes",
                acBonus: { value: 2, rounds: null },
                text: "A shimmering field grants a creature +2 AC while you concentrate.",
            },
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
        if (!dataBlock.existsOnServer) {
            // A brand-new catalogue is created locally only, and `migrate` has
            // nothing to do to freshly minted defaults -- so nothing ever
            // triggered a write and the row was never created. The ghost, which
            // reads this over the socket, then saw a campaign with no weapons,
            // no conditions and no items however many times the tab was opened.
            dataBlock.sync();
        } else if (migrate(dataBlock.reactiveData.value)) {
            dataBlock.sync();
        }
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

    // An *absent* key means the catalogue predates that content, so it gets the
    // defaults. An empty array means the DM deleted everything in it, and that
    // stays deleted -- which is why this is `??=` on the defaults rather than a
    // length check. Races and backgrounds have no `addMissing` pass below, on
    // purpose: they are the two lists a DM is most likely to curate wholesale,
    // so re-adding individual entries would fight them. Without this line a
    // catalogue that never had the key would simply have none.
    cat.weapons ??= defaults.weapons;
    cat.armour ??= defaults.armour;
    cat.races ??= defaults.races;
    cat.backgrounds ??= defaults.backgrounds;
    cat.classes ??= defaults.classes;
    cat.cantrips ??= defaults.cantrips;
    cat.spells ??= defaults.spells;
    cat.items ??= defaults.items;
    cat.conditions ??= defaults.conditions;

    addMissing(cat.weapons, defaults.weapons);
    addMissing(cat.armour, defaults.armour);
    addMissing(cat.classes, defaults.classes);
    addMissing(cat.cantrips, defaults.cantrips);
    addMissing(cat.spells, defaults.spells);
    addMissing(cat.items, defaults.items);
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

export function findItem(id: string | null): Item | undefined {
    return id === null ? undefined : current.value.items.find((i) => i.id === id);
}

export function findSpell(id: string | null): Spell | undefined {
    return id === null ? undefined : current.value.spells.find((s) => s.id === id);
}

/** Every levelled spell a class can cast, for the prepared-spell picker. */
export function spellsForClass(classId: string | null): Spell[] {
    if (classId === null) return [];
    return current.value.spells.filter((s) => s.classes.includes(classId));
}

export function findArmour(id: string | null): Armour | undefined {
    return id === null ? undefined : current.value.armour.find((a) => a.id === id);
}

/** Body armour, i.e. everything that is not a shield. */
export function bodyArmour(): Armour[] {
    return current.value.armour.filter((a) => a.weight !== "shield");
}

export function shields(): Armour[] {
    return current.value.armour.filter((a) => a.weight === "shield");
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
