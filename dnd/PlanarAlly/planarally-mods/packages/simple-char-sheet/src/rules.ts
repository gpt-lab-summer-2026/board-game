// The 5e arithmetic. Pure functions, no Vue, no DataBlocks -- so it can be read,
// reasoned about and (if it ever matters) tested without a browser.
//
// This is the *only* implementation of these rules in the project. The mod runs
// it on every save and writes the results into `sheet.derived`; the ghost player
// reads those finished strings and rolls them. See data.ts for why.

import type { Cantrip, ClassDef, Weapon } from "./catalogue";
import { catalogue, findCantrip, findClass, findCondition, findWeapon } from "./catalogue";
import type { AbilityKey, CharacterSheet, DerivedAttack, DerivedBlock, DerivedCantrip } from "./data";
import { ABILITIES } from "./data";

/** The familiar (score - 10) / 2, rounded down -- so 8 gives -1, not 0. */
export function abilityMod(score: number): number {
    return Math.floor((score - 10) / 2);
}

export function proficiencyBonus(level: number): number {
    return 2 + Math.floor((clampLevel(level) - 1) / 4);
}

/**
 * The campaign runs to 2nd level, single class.
 *
 * Enforced here rather than only in the UI so a sheet edited elsewhere --
 * by the ghost, or carried in on a preset -- cannot smuggle a level 7
 * wizard past it.
 */
export const MAX_LEVEL = 2;

export function clampLevel(level: number): number {
    if (!Number.isFinite(level)) return 1;
    return Math.min(MAX_LEVEL, Math.max(1, Math.floor(level)));
}

/** "+3" / "-1" / "+0" -- always signed, which is how sheets read. */
export function signed(value: number): string {
    return `${value >= 0 ? "+" : "-"}${Math.abs(value)}`;
}

/** Append a modifier to dice notation, omitting it entirely when zero. */
export function withModifier(dice: string, modifier: number): string {
    return modifier === 0 ? dice : `${dice}${signed(modifier)}`;
}

// Advantage and disadvantage as notation PA's dice parser understands, so the
// ghost can roll them without knowing what they mean: two d20, keep the highest
// or the lowest.
export function d20Roll(modifier: number, bias: "normal" | "advantage" | "disadvantage" = "normal"): string {
    const dice = bias === "normal" ? "1d20" : bias === "advantage" ? "2d20kh1" : "2d20kl1";
    return withModifier(dice, modifier);
}

/**
 * How many damage dice a cantrip rolls at a given level.
 *
 * Cantrips are the one thing in 5e that scales with character level rather than
 * spell slot: one die, then two at 5th, three at 11th, four at 17th.
 */
export function cantripDice(level: number): number {
    const lvl = clampLevel(level);
    if (lvl >= 17) return 4;
    if (lvl >= 11) return 3;
    if (lvl >= 5) return 2;
    return 1;
}

/** Multiply the die count in notation like "1d10" -> "3d10". */
export function scaleDice(dice: string, factor: number): string {
    const match = /^(\d*)d(\d+)$/.exec(dice.trim());
    if (match === null) return dice;
    const count = Number.parseInt(match[1] === "" ? "1" : match[1]!, 10);
    return `${count * factor}d${match[2]}`;
}

/**
 * Saving throw bonuses for all six abilities.
 *
 * Proficiency applies only to the two your class is trained in, which is
 * the whole point of the mechanic -- showing six identical numbers would
 * tell a player nothing.
 */
export function savingThrows(
    abilities: Record<AbilityKey, number>,
    proficiency: number,
    proficientIn: AbilityKey[],
): Record<AbilityKey, { bonus: number; proficient: boolean }> {
    const out = {} as Record<AbilityKey, { bonus: number; proficient: boolean }>;
    const trained = new Set(proficientIn);
    for (const { key } of ABILITIES) {
        const proficient = trained.has(key);
        out[key] = {
            bonus: abilityMod(abilities[key]) + (proficient ? proficiency : 0),
            proficient,
        };
    }
    return out;
}

export function spellSaveDc(proficiency: number, abilityModifier: number): number {
    return 8 + proficiency + abilityModifier;
}

/**
 * Which ability a weapon attacks with.
 *
 * Ranged is DEX. Melee is STR, except that finesse weapons may use either --
 * and since nothing is lost by picking the better one, that's what a player
 * would do anyway.
 */
export function attackAbility(weapon: Weapon, abilities: Record<AbilityKey, number>): AbilityKey {
    if (weapon.kind === "ranged") return "dex";
    if (weapon.finesse === true) return abilities.dex > abilities.str ? "dex" : "str";
    return "str";
}

/**
 * Resolve an `applies` reference into something self-contained.
 *
 * The DC is computed here and stored, so the ghost can adjudicate the save
 * without knowing how a save DC is built -- same reason the attack notation
 * is stored rather than the ingredients.
 */
function deriveApplies(
    applies: { condition: string; save?: AbilityKey } | undefined,
    proficiency: number,
    abilityModifier: number,
): DerivedAttack["applies"] {
    if (applies === undefined) return null;
    const condition = findCondition(applies.condition);
    if (condition === undefined) return null;
    return {
        condition: condition.id,
        name: condition.name,
        save: applies.save ?? null,
        dc: applies.save === undefined ? null : spellSaveDc(proficiency, abilityModifier),
    };
}

export function deriveAttack(
    weapon: Weapon | undefined,
    abilities: Record<AbilityKey, number>,
    proficiency: number,
): DerivedAttack | null {
    if (weapon === undefined) return null;

    const ability = attackAbility(weapon, abilities);
    const mod = abilityMod(abilities[ability]);

    const bonus = mod + proficiency;
    return {
        weapon: weapon.name,
        // Proficiency is assumed. Tracking per-weapon proficiency would mean a
        // checkbox per weapon on every sheet, which is a lot of UI for a rule
        // that almost never bites at a table using the default catalogue.
        attack: d20Roll(bonus),
        attackAdvantage: d20Roll(bonus, "advantage"),
        attackDisadvantage: d20Roll(bonus, "disadvantage"),
        damage: withModifier(weapon.damage, mod),
        ability,
        applies: deriveApplies(weapon.applies, proficiency, mod),
    };
}

/**
 * Which ability the character casts with: their own override if set, otherwise
 * the class's. Null means they have no way to cast, and the cantrip row is
 * suppressed rather than silently computed off a zero modifier.
 */
export function castingAbility(sheet: CharacterSheet): AbilityKey | null {
    // No per-sheet override any more. A fighter is not a caster, and an
    // ability picker on their sheet only invited them to become one by
    // accident. Casting follows the class, full stop.
    return findClass(sheet.classId)?.spellcastingAbility ?? null;
}

export function canCast(sheet: CharacterSheet): boolean {
    return castingAbility(sheet) !== null;
}

/** Cantrips this character's class can actually learn. */
export function availableCantrips(sheet: CharacterSheet): Cantrip[] {
    const classId = sheet.classId;
    if (classId === null || !canCast(sheet)) return [];
    return catalogue.value.cantrips.filter((c) => (c.classes ?? []).includes(classId));
}

export function deriveCantrip(
    cantrip: Cantrip | undefined,
    sheet: CharacterSheet,
    proficiency: number,
): DerivedCantrip | null {
    if (cantrip === undefined) return null;

    const ability = castingAbility(sheet);
    if (ability === null) return null;

    const mod = abilityMod(sheet.abilities[ability]);
    const damage = withModifier(scaleDice(cantrip.damage, cantripDice(sheet.level)), 0);
    const isAttack = cantrip.kind === "attack";
    const bonus = mod + proficiency;

    return {
        name: cantrip.name,
        kind: cantrip.kind,
        // Cantrip damage gets no ability modifier in 5e -- the scaling dice are
        // the progression. Easy to get wrong by copying the weapon path.
        damage,
        damageType: cantrip.damageType,
        range: cantrip.range,
        attack: isAttack ? d20Roll(bonus) : null,
        attackAdvantage: isAttack ? d20Roll(bonus, "advantage") : null,
        attackDisadvantage: isAttack ? d20Roll(bonus, "disadvantage") : null,
        save: cantrip.save ?? null,
        saveDc: cantrip.kind === "save" ? spellSaveDc(proficiency, mod) : null,
        applies: deriveApplies(cantrip.applies, proficiency, mod),
        // A spell attack is a ranged attack, so it takes disadvantage with a
        // hostile creature within 5 feet -- except a melee spell attack, which
        // is delivered at touch range by design.
        closeRangeDisadvantage: isAttack && cantrip.melee !== true,
    };
}

export interface WeaponAction {
    id: string;
    name: string;
    /** Where it comes from, so the sheet can be honest about what is homebrew. */
    source: "5e" | "house";
    text: string;
    /** Condition it inflicts, if any. */
    condition?: string;
    /** Contested or saved against this ability; null means it just lands. */
    save?: AbilityKey;
}

/**
 * What you can *do* with a weapon, beyond hitting with it.
 *
 * Derived from damage type and properties rather than listed per weapon --
 * "lacerate is available to most all swords" is a rule about slashing, not a
 * fact about one blade, and writing it out per entry would mean editing every
 * sword the day the rule changes.
 *
 * Grapple, Shove and Disarm are real 5e options available with any melee
 * attack. The damage-type ones are house rules for this campaign and are
 * labelled as such, because a player should be able to tell which is which.
 */
export function weaponActions(weapon: Weapon | undefined): WeaponAction[] {
    if (weapon === undefined) return [];
    const actions: WeaponAction[] = [];
    const props = (weapon.properties ?? []).join(" ").toLowerCase();

    if (weapon.kind === "melee") {
        actions.push(
            {
                id: "grapple",
                name: "Grapple",
                source: "5e",
                text: "Replace one attack with a contest against the target's Athletics or Acrobatics. On a win it is grappled and its speed drops to 0.",
                condition: "grappled",
                save: "str",
            },
            {
                id: "shove",
                name: "Shove",
                source: "5e",
                text: "Replace one attack to knock the target prone, or push it 5 feet away.",
                condition: "prone",
                save: "str",
            },
            {
                id: "disarm",
                name: "Disarm",
                source: "5e",
                text: "Replace one attack with a contest to knock the target's weapon from its grip.",
                save: "str",
            },
        );
    }

    switch (weapon.damageType) {
        case "slashing":
            actions.push({
                id: "lacerate",
                name: "Lacerate",
                source: "house",
                text: "A deliberately ragged cut. The target bleeds until someone spends an action to staunch it.",
                condition: "bleeding",
                save: "con",
            });
            break;
        case "bludgeoning":
            actions.push({
                id: "daze",
                name: "Daze",
                source: "house",
                text: "A blow to the head. The target is stunned until the end of its next turn.",
                condition: "stunned",
                save: "con",
            });
            break;
        case "piercing":
            actions.push({
                id: "pin",
                name: "Pin",
                source: "house",
                text: "Drive the point through cloth or hide and into the ground. The target is restrained until it breaks free.",
                condition: "restrained",
                save: "str",
            });
            break;
        default:
            break;
    }

    if (props.includes("versatile")) {
        actions.push({
            id: "two-handed",
            name: "Two-handed grip",
            source: "5e",
            text: `Wield it in both hands for the larger damage die (${weapon.properties?.find((p) => p.startsWith("versatile")) ?? "versatile"}).`,
        });
    }
    if (props.includes("thrown")) {
        actions.push({
            id: "throw",
            name: "Throw",
            source: "5e",
            text: "Make a ranged attack with it instead of a melee one, using the same modifier.",
        });
    }
    if (props.includes("light")) {
        actions.push({
            id: "offhand",
            name: "Off-hand attack",
            source: "5e",
            text: "A bonus-action attack with a second light weapon. No ability modifier on the damage.",
        });
    }
    if (props.includes("heavy") || props.includes("two-handed")) {
        actions.push({
            id: "heavy-swing",
            name: "Reckless swing",
            source: "house",
            text: "Attack with disadvantage for an extra damage die. Commit before you roll.",
        });
    }
    if (props.includes("loading")) {
        actions.push({
            id: "loading",
            name: "Loading",
            source: "5e",
            text: "Only one attack per action with this weapon, however many you would otherwise get.",
        });
    }
    return actions;
}

export function deriveSheet(sheet: CharacterSheet): DerivedBlock {
    const proficiency = proficiencyBonus(sheet.level);

    const mods = {} as Record<AbilityKey, number>;
    for (const { key } of ABILITIES) mods[key] = abilityMod(sheet.abilities[key]);

    const ability = castingAbility(sheet);

    return {
        proficiency,
        mods,
        melee: deriveAttack(findWeapon(sheet.equipped.melee), sheet.abilities, proficiency),
        ranged: deriveAttack(findWeapon(sheet.equipped.ranged), sheet.abilities, proficiency),
        cantrip: deriveCantrip(findCantrip(sheet.equipped.cantrip), sheet, proficiency),
        spellSaveDc: ability === null ? null : spellSaveDc(proficiency, mods[ability]),
        saves: savingThrows(sheet.abilities, proficiency, findClass(sheet.classId)?.savingThrows ?? []),
    };
}

/**
 * Level-1 max HP: full hit die plus CON modifier.
 *
 * Only ever *offered* in the UI, never applied automatically -- a DM who has
 * typed a monster's HP by hand should not have it overwritten because they
 * later picked a class.
 */
export function suggestedMaxHp(sheet: CharacterSheet): number | undefined {
    const klass: ClassDef | undefined = findClass(sheet.classId);
    if (klass === undefined) return undefined;
    const level = clampLevel(sheet.level);
    const con = abilityMod(sheet.abilities.con);
    // Levels past the first use the die's average, rounded up, as 5e's fixed
    // progression does.
    const perLevel = Math.ceil(klass.hitDie / 2) + 1;
    return Math.max(1, klass.hitDie + con + (level - 1) * (perLevel + con));
}
