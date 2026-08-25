// The 5e arithmetic. Pure functions, no Vue, no DataBlocks -- so it can be read,
// reasoned about and (if it ever matters) tested without a browser.
//
// This is the *only* implementation of these rules in the project. The mod runs
// it on every save and writes the results into `sheet.derived`; the ghost player
// reads those finished strings and rolls them. See data.ts for why.
import { catalogue, findArmour, findCantrip, findClass, findCondition, findSpell, findWeapon } from "./catalogue.js";
import { ABILITIES, SKILLS } from "./data.js";
/** The familiar (score - 10) / 2, rounded down -- so 8 gives -1, not 0. */
export function abilityMod(score) {
    return Math.floor((score - 10) / 2);
}
export function proficiencyBonus(level) {
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
export function clampLevel(level) {
    if (!Number.isFinite(level))
        return 1;
    return Math.min(MAX_LEVEL, Math.max(1, Math.floor(level)));
}
/** "+3" / "-1" / "+0" -- always signed, which is how sheets read. */
export function signed(value) {
    return `${value >= 0 ? "+" : "-"}${Math.abs(value)}`;
}
/** Append a modifier to dice notation, omitting it entirely when zero. */
export function withModifier(dice, modifier) {
    return modifier === 0 ? dice : `${dice}${signed(modifier)}`;
}
// Advantage and disadvantage as notation PA's dice parser understands, so the
// ghost can roll them without knowing what they mean: two d20, keep the highest
// or the lowest.
export function d20Roll(modifier, bias = "normal") {
    const dice = bias === "normal" ? "1d20" : bias === "advantage" ? "2d20kh1" : "2d20kl1";
    return withModifier(dice, modifier);
}
/**
 * How many damage dice a cantrip rolls at a given level.
 *
 * Cantrips are the one thing in 5e that scales with character level rather than
 * spell slot: one die, then two at 5th, three at 11th, four at 17th.
 */
export function cantripDice(level) {
    const lvl = clampLevel(level);
    if (lvl >= 17)
        return 4;
    if (lvl >= 11)
        return 3;
    if (lvl >= 5)
        return 2;
    return 1;
}
/** Multiply the die count in notation like "1d10" -> "3d10". */
export function scaleDice(dice, factor) {
    const match = /^(\d*)d(\d+)$/.exec(dice.trim());
    if (match === null)
        return dice;
    const count = Number.parseInt(match[1] === "" ? "1" : match[1], 10);
    return `${count * factor}d${match[2]}`;
}
/**
 * Saving throw bonuses for all six abilities.
 *
 * Proficiency applies only to the two your class is trained in, which is
 * the whole point of the mechanic -- showing six identical numbers would
 * tell a player nothing.
 */
export function savingThrows(abilities, proficiency, proficientIn) {
    const out = {};
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
export function spellSaveDc(proficiency, abilityModifier) {
    return 8 + proficiency + abilityModifier;
}
/**
 * Which ability a weapon attacks with.
 *
 * Ranged is DEX. Melee is STR, except that finesse weapons may use either --
 * and since nothing is lost by picking the better one, that's what a player
 * would do anyway.
 */
export function attackAbility(weapon, abilities) {
    if (weapon.kind === "ranged")
        return "dex";
    if (weapon.finesse === true)
        return abilities.dex > abilities.str ? "dex" : "str";
    return "str";
}
/**
 * Resolve an `applies` reference into something self-contained.
 *
 * The DC is computed here and stored, so the ghost can adjudicate the save
 * without knowing how a save DC is built -- same reason the attack notation
 * is stored rather than the ingredients.
 */
function deriveApplies(applies, proficiency, abilityModifier) {
    if (applies === undefined)
        return null;
    const condition = findCondition(applies.condition);
    if (condition === undefined)
        return null;
    return {
        condition: condition.id,
        name: condition.name,
        save: applies.save ?? null,
        dc: applies.save === undefined ? null : spellSaveDc(proficiency, abilityModifier),
    };
}
export function deriveAttack(weapon, abilities, proficiency) {
    if (weapon === undefined)
        return null;
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
export function castingAbility(sheet) {
    // No per-sheet override any more. A fighter is not a caster, and an
    // ability picker on their sheet only invited them to become one by
    // accident. Casting follows the class, full stop.
    return findClass(sheet.classId)?.spellcastingAbility ?? null;
}
export function canCast(sheet) {
    return castingAbility(sheet) !== null;
}
/** Cantrips this character's class can actually learn. */
export function availableCantrips(sheet) {
    const classId = sheet.classId;
    if (classId === null || !canCast(sheet))
        return [];
    return catalogue.value.cantrips.filter((c) => (c.classes ?? []).includes(classId));
}
export function deriveCantrip(cantrip, sheet, proficiency) {
    if (cantrip === undefined)
        return null;
    const ability = castingAbility(sheet);
    if (ability === null)
        return null;
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
export function weaponActions(weapon) {
    if (weapon === undefined)
        return [];
    const actions = [];
    const props = (weapon.properties ?? []).join(" ").toLowerCase();
    if (weapon.kind === "melee") {
        actions.push({
            id: "grapple",
            name: "Grapple",
            source: "5e",
            text: "Replace one attack with a contest against the target's Athletics or Acrobatics. On a win it is grappled and its speed drops to 0.",
            condition: "grappled",
            save: "str",
        }, {
            id: "shove",
            name: "Shove",
            source: "5e",
            text: "Replace one attack to knock the target prone, or push it 5 feet away.",
            condition: "prone",
            save: "str",
        }, {
            id: "disarm",
            name: "Disarm",
            source: "5e",
            text: "Replace one attack with a contest to knock the target's weapon from its grip.",
            save: "str",
        });
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
/**
 * Armour class from gear, Dexterity and whatever is temporarily helping.
 *
 * The Dexterity cap is the part worth getting right, and the part a stored
 * number never expressed: light armour passes the whole modifier through, medium
 * stops at +2, and heavy passes none at all -- which is why a plate-wearing
 * fighter and a leather-clad rogue can land on the same AC by opposite routes.
 *
 * An override short-circuits everything. Monsters are usually written as "AC 15"
 * with no statement of what that 15 is made of, and forcing a DM to reverse
 * engineer an armour entry to type a number would be a step backwards.
 */
export function deriveAc(sheet) {
    const armour = findArmour(sheet.equipped.armour);
    const shield = findArmour(sheet.equipped.shield);
    const dexMod = abilityMod(sheet.abilities.dex);
    const base = armour?.baseAc ?? 10;
    // `?? null` rather than `?? 0`: unarmoured is uncapped, not capped at zero.
    const cap = armour === undefined ? null : armour.dexCap;
    const dex = cap === null ? dexMod : Math.min(dexMod, cap);
    const shieldBonus = shield?.baseAc ?? 0;
    let modifiers = 0;
    for (const mod of sheet.acModifiers ?? [])
        modifiers += mod.value;
    // Too weak for your plate: 5e docks 10 feet of speed but leaves AC alone.
    const speedPenalty = armour?.strength !== undefined && sheet.abilities.str < armour.strength ? 10 : 0;
    const overridden = sheet.acOverride !== null && sheet.acOverride !== undefined;
    const derivedTotal = base + dex + shieldBonus + modifiers;
    return {
        // Modifiers still apply over an override: "AC 15" plus half cover is 17,
        // and a DM who typed 15 did not mean to opt out of cover.
        total: overridden ? sheet.acOverride + modifiers : derivedTotal,
        base,
        dex,
        shield: shieldBonus,
        modifiers,
        armourName: armour?.name ?? null,
        shieldName: shield?.name ?? null,
        overridden,
        speedPenalty,
        stealthDisadvantage: armour?.stealthDisadvantage === true,
    };
}
/**
 * Level-1 slots for a full caster, which is all this supports.
 *
 * Wizard and Cleric are the only spellcasting classes in the catalogue and both
 * progress identically at these levels: two first-level slots at 1, three at 2.
 * A half-caster would need its own row; there isn't one, so there isn't a table.
 */
export function spellSlotsFor(klass, level) {
    if (klass?.spellcastingAbility === undefined)
        return {};
    const max = clampLevel(level) >= 2 ? 3 : 2;
    return { "1": { used: 0, max } };
}
/**
 * Merge a fresh slot table with what the character has already spent.
 *
 * Levelling up must not silently refill the pool -- gaining a third slot in the
 * middle of a fight should give you one more, not undo the two you burned.
 */
export function reconcileSlots(current, fresh) {
    const out = {};
    for (const [level, slot] of Object.entries(fresh)) {
        const used = current?.[level]?.used ?? 0;
        out[level] = { max: slot.max, used: Math.min(used, slot.max) };
    }
    return out;
}
export function skillBonuses(abilities, proficiency, proficient) {
    const known = new Set(proficient);
    const out = {};
    for (const skill of SKILLS) {
        const isProficient = known.has(skill.key);
        out[skill.key] = {
            ability: skill.ability,
            proficient: isProficient,
            bonus: abilityMod(abilities[skill.ability]) + (isProficient ? proficiency : 0),
        };
    }
    return out;
}
/**
 * A prepared spell, resolved against this character.
 *
 * Levelled spell damage takes no ability modifier -- the slot is the cost and
 * the dice are the effect -- but *healing* does, which is the asymmetry most
 * easily got wrong by copying either the weapon or the cantrip path.
 */
export function deriveSpell(spell, sheet, proficiency) {
    const ability = castingAbility(sheet);
    if (ability === null)
        return null;
    const mod = abilityMod(sheet.abilities[ability]);
    const bonus = mod + proficiency;
    const isAttack = spell.kind === "attack";
    return {
        id: spell.id,
        name: spell.name,
        level: spell.level,
        kind: spell.kind,
        range: spell.range,
        castingTime: spell.castingTime ?? "action",
        attack: isAttack ? d20Roll(bonus) : null,
        attackAdvantage: isAttack ? d20Roll(bonus, "advantage") : null,
        attackDisadvantage: isAttack ? d20Roll(bonus, "disadvantage") : null,
        damage: spell.damage ?? null,
        damageType: spell.damageType ?? null,
        healing: spell.healing === undefined ? null : withModifier(spell.healing, mod),
        save: spell.save ?? null,
        saveDc: spell.save === undefined ? null : spellSaveDc(proficiency, mod),
        halfOnSave: spell.halfOnSave === true,
        area: spell.area ?? null,
        concentration: spell.concentration === true,
        acBonus: spell.acBonus ?? null,
        text: spell.text,
    };
}
export function deriveSheet(sheet) {
    const proficiency = proficiencyBonus(sheet.level);
    const mods = {};
    for (const { key } of ABILITIES)
        mods[key] = abilityMod(sheet.abilities[key]);
    const ability = castingAbility(sheet);
    const ac = deriveAc(sheet);
    // Slots follow class and level, so they are reconciled here rather than
    // being another thing the editor has to remember to update. Spent slots
    // survive: see reconcileSlots.
    sheet.slots = reconcileSlots(sheet.slots, spellSlotsFor(findClass(sheet.classId), sheet.level));
    // `sheet.ac` is the one number the AC tracker and the ghost read, so it is
    // kept in step here rather than at every call site that can change AC.
    sheet.ac = ac.total;
    return {
        proficiency,
        ac,
        mods,
        melee: deriveAttack(findWeapon(sheet.equipped.melee), sheet.abilities, proficiency),
        ranged: deriveAttack(findWeapon(sheet.equipped.ranged), sheet.abilities, proficiency),
        cantrip: deriveCantrip(findCantrip(sheet.equipped.cantrip), sheet, proficiency),
        spellSaveDc: ability === null ? null : spellSaveDc(proficiency, mods[ability]),
        saves: savingThrows(sheet.abilities, proficiency, findClass(sheet.classId)?.savingThrows ?? []),
        skills: skillBonuses(sheet.abilities, proficiency, sheet.skillProficiencies ?? []),
        spells: (sheet.spells ?? [])
            .map((id) => findSpell(id))
            .filter((s) => s !== undefined)
            .map((s) => deriveSpell(s, sheet, proficiency))
            .filter((s) => s !== null),
    };
}
/**
 * Level-1 max HP: full hit die plus CON modifier.
 *
 * Only ever *offered* in the UI, never applied automatically -- a DM who has
 * typed a monster's HP by hand should not have it overwritten because they
 * later picked a class.
 */
export function suggestedMaxHp(sheet) {
    const klass = findClass(sheet.classId);
    if (klass === undefined)
        return undefined;
    const level = clampLevel(sheet.level);
    const con = abilityMod(sheet.abilities.con);
    // Levels past the first use the die's average, rounded up, as 5e's fixed
    // progression does.
    const perLevel = Math.ceil(klass.hitDie / 2) + 1;
    return Math.max(1, klass.hitDie + con + (level - 1) * (perLevel + con));
}
