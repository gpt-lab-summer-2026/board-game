import { ref, watch, shallowReadonly, defineComponent, computed, onMounted, resolveComponent, createElementBlock, openBlock, createCommentVNode, createElementVNode, withDirectives, Fragment, renderList, toDisplayString, vModelSelect, vModelText, unref, createVNode, createTextVNode, normalizeClass, vModelCheckbox } from "vue";
const CATALOGUE_VERSION = 5;
const BLOCK_NAME$1 = "catalogue";
function defaultCatalogue() {
  return {
    version: CATALOGUE_VERSION,
    weapons: [
      { id: "longsword", name: "Longsword", kind: "melee", damage: "1d8", damageType: "slashing", properties: ["versatile (1d10)"] },
      { id: "dagger", name: "Dagger", kind: "melee", damage: "1d4", damageType: "piercing", finesse: true, properties: ["light", "thrown (20/60)"] },
      { id: "greataxe", name: "Greataxe", kind: "melee", damage: "1d12", damageType: "slashing", properties: ["heavy", "two-handed"] },
      { id: "lacerate", name: "Lacerating blade", kind: "melee", damage: "1d8", damageType: "slashing", applies: { condition: "bleeding" }, properties: ["cruel"] },
      { id: "rapier", name: "Rapier", kind: "melee", damage: "1d8", damageType: "piercing", finesse: true },
      { id: "quarterstaff", name: "Quarterstaff", kind: "melee", damage: "1d6", damageType: "bludgeoning", properties: ["versatile (1d8)"] },
      { id: "shortbow", name: "Shortbow", kind: "ranged", damage: "1d6", damageType: "piercing", range: "80/320", properties: ["two-handed"] },
      { id: "light-crossbow", name: "Light crossbow", kind: "ranged", damage: "1d8", damageType: "piercing", range: "80/320", properties: ["loading", "two-handed"] },
      { id: "sling", name: "Sling", kind: "ranged", damage: "1d4", damageType: "bludgeoning", range: "30/120" },
      { id: "javelin", name: "Javelin", kind: "ranged", damage: "1d6", damageType: "piercing", range: "30/120", properties: ["thrown"] },
      // Natural weapons, for creatures rather than adventurers. The
      // numbers are a brown bear's.
      { id: "claws", name: "Claws", kind: "melee", damage: "2d6", damageType: "slashing", natural: true, applies: { condition: "bleeding" } },
      { id: "bite", name: "Bite", kind: "melee", damage: "1d8", damageType: "piercing", natural: true },
      { id: "hooves", name: "Hooves", kind: "melee", damage: "1d6", damageType: "bludgeoning", natural: true }
    ],
    races: [
      { id: "human", name: "Human", passive: { name: "Versatile", text: "+1 to every ability score." } },
      { id: "dwarf", name: "Dwarf", passive: { name: "Dwarven Resilience", text: "Darkvision 60 ft. Advantage on saves against poison, and resistance to poison damage." } },
      { id: "elf", name: "Elf", passive: { name: "Fey Ancestry", text: "Darkvision 60 ft. Advantage on saves against being charmed, and magic cannot put you to sleep." } },
      { id: "halfling", name: "Halfling", passive: { name: "Lucky", text: "When you roll a 1 on an attack, ability check or save, reroll and use the new result." } },
      { id: "half-orc", name: "Half-Orc", passive: { name: "Relentless Endurance", text: "When dropped to 0 hit points without being killed outright, drop to 1 instead. Once per long rest." } }
    ],
    backgrounds: [
      { id: "soldier", name: "Soldier", passive: { name: "Military Rank", text: "Soldiers loyal to your former organisation recognise your authority and defer to it." } },
      { id: "acolyte", name: "Acolyte", passive: { name: "Shelter of the Faithful", text: "You and your companions can expect free healing and care at temples of your faith." } },
      { id: "criminal", name: "Criminal", passive: { name: "Criminal Contact", text: "You have a reliable contact in the underworld and know how to get messages to them." } },
      { id: "sage", name: "Sage", passive: { name: "Researcher", text: "When you don't know something, you usually know where and from whom to find it out." } },
      { id: "folk-hero", name: "Folk Hero", passive: { name: "Rustic Hospitality", text: "Commoners will shelter and hide you, short of risking their lives." } }
    ],
    classes: [
      { id: "fighter", name: "Fighter", hitDie: 10, primaryAbility: "str", savingThrows: ["str", "con"], passive: { name: "Second Wind", text: "As a bonus action, regain 1d10 + level hit points. Once per short rest." }, level2: { name: "Action Surge", text: "On your turn you can take one additional action. Once per short rest." } },
      { id: "rogue", name: "Rogue", hitDie: 8, primaryAbility: "dex", savingThrows: ["dex", "int"], passive: { name: "Sneak Attack", text: "Once per turn, deal an extra 1d6 damage to a target you have advantage against." }, level2: { name: "Cunning Action", text: "A bonus action each turn to Dash, Disengage or Hide." } },
      { id: "wizard", name: "Wizard", hitDie: 6, primaryAbility: "int", savingThrows: ["int", "wis"], spellcastingAbility: "int", passive: { name: "Arcane Recovery", text: "Once per day on a short rest, recover spell slots totalling half your level, rounded up." }, level2: { name: "Arcane Tradition", text: "Choose a school of magic; it grants features now and at higher levels." } },
      { id: "cleric", name: "Cleric", hitDie: 8, primaryAbility: "wis", savingThrows: ["wis", "cha"], spellcastingAbility: "wis", passive: { name: "Divine Domain", text: "Your chosen domain grants extra spells and a domain feature at 1st level." }, level2: { name: "Channel Divinity", text: "Turn Undead, plus one effect from your domain. Once per short rest." } },
      { id: "barbarian", name: "Barbarian", hitDie: 12, primaryAbility: "str", savingThrows: ["str", "con"], passive: { name: "Rage", text: "Advantage on Strength checks and saves, bonus melee damage, and resistance to physical damage." }, level2: { name: "Reckless Attack", text: "Advantage on melee Strength attacks this turn; attacks against you have it too." } },
      // For animal companions and monsters: a statline with no gear.
      { id: "beast", name: "Beast", hitDie: 10, primaryAbility: "str", savingThrows: ["str", "con"], passive: { name: "Keen Smell", text: "Advantage on Wisdom (Perception) checks that rely on smell. Fights with natural weapons and carries no equipment." }, level2: { name: "Pack Tactics", text: "Advantage on an attack if an ally is within 5 feet of the target." } }
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
      { id: "unconscious", name: "Unconscious", short: "UNC", text: "Incapacitated, prone, and unaware. Attacks within 5 ft are critical hits.", impliesDefeated: true }
    ],
    cantrips: [
      { id: "fire-bolt", name: "Fire Bolt", classes: ["wizard"], kind: "attack", damage: "1d10", damageType: "fire", range: "120", text: "A mote of fire hurled at a target. Flammable objects not being worn or carried are ignited." },
      { id: "eldritch-blast", name: "Eldritch Blast", classes: ["wizard"], kind: "attack", damage: "1d10", damageType: "force", range: "120", text: "A beam of crackling energy." },
      { id: "ray-of-frost", name: "Ray of Frost", classes: ["wizard"], kind: "attack", damage: "1d8", damageType: "cold", range: "60", applies: { condition: "slowed" }, text: "On a hit, the target's speed is reduced by 10 feet until your next turn." },
      { id: "shocking-grasp", name: "Shocking Grasp", classes: ["wizard"], kind: "attack", damage: "1d8", damageType: "lightning", range: "touch", melee: true, text: "A melee spell attack. On a hit the target can't take reactions until its next turn. Advantage if it wears metal armour." },
      { id: "sacred-flame", name: "Sacred Flame", classes: ["cleric"], kind: "save", damage: "1d8", damageType: "radiant", range: "60", save: "dex", applies: { condition: "blinded", save: "con" }, text: "No attack roll: the target makes a Dexterity save, taking damage on a failure. Cover gives no benefit." }
    ]
  };
}
let pending$1;
const current = ref(defaultCatalogue());
const catalogue = current;
function ensureCatalogue() {
  pending$1 ?? (pending$1 = load$1());
  return pending$1;
}
async function load$1() {
  const dataBlock = await api.getOrLoadDataBlock(
    { category: "room", name: BLOCK_NAME$1 },
    { defaultData: defaultCatalogue }
  );
  if (dataBlock !== void 0) {
    if (migrate(dataBlock.reactiveData.value)) dataBlock.sync();
    current.value = dataBlock.reactiveData.value;
    watch(dataBlock.reactiveData, (value) => {
      if (migrate(value)) dataBlock.sync();
      current.value = value;
    });
  }
  return dataBlock;
}
function migrate(cat) {
  if ((cat.version ?? 1) >= CATALOGUE_VERSION) return false;
  const defaults = defaultCatalogue();
  cat.weapons ?? (cat.weapons = []);
  cat.races ?? (cat.races = []);
  cat.backgrounds ?? (cat.backgrounds = []);
  cat.classes ?? (cat.classes = []);
  cat.cantrips ?? (cat.cantrips = []);
  cat.conditions ?? (cat.conditions = []);
  addMissing(cat.weapons, defaults.weapons);
  addMissing(cat.classes, defaults.classes);
  addMissing(cat.cantrips, defaults.cantrips);
  addMissing(cat.conditions, defaults.conditions);
  for (const klass of cat.classes) {
    if (klass.spellcastingAbility !== void 0) continue;
    const fresh = defaults.classes.find((c) => c.id === klass.id);
    if ((fresh == null ? void 0 : fresh.spellcastingAbility) !== void 0) klass.spellcastingAbility = fresh.spellcastingAbility;
  }
  cat.version = CATALOGUE_VERSION;
  return true;
}
function addMissing(existing, defaults) {
  const known = new Set(existing.map((e) => e.id));
  for (const entry of defaults) if (!known.has(entry.id)) existing.push(entry);
}
function findWeapon(id) {
  return id === null ? void 0 : current.value.weapons.find((w) => w.id === id);
}
function weaponsOfKind(kind) {
  return current.value.weapons.filter((w) => w.kind === kind);
}
function weaponGroups(kind) {
  const all = weaponsOfKind(kind);
  return {
    carried: all.filter((w) => w.natural !== true),
    natural: all.filter((w) => w.natural === true)
  };
}
function findCondition(id) {
  return current.value.conditions.find((c) => c.id === id);
}
function findCantrip(id) {
  return id === null ? void 0 : current.value.cantrips.find((c) => c.id === id);
}
function findRace(id) {
  return id === null ? void 0 : current.value.races.find((r) => r.id === id);
}
function findBackground(id) {
  return id === null ? void 0 : current.value.backgrounds.find((b) => b.id === id);
}
function findClass(id) {
  return id === null ? void 0 : current.value.classes.find((c) => c.id === id);
}
const ABILITIES = [
  { key: "str", label: "STR", long: "Strength" },
  { key: "dex", label: "DEX", long: "Dexterity" },
  { key: "con", label: "CON", long: "Constitution" },
  { key: "int", label: "INT", long: "Intelligence" },
  { key: "wis", label: "WIS", long: "Wisdom" },
  { key: "cha", label: "CHA", long: "Charisma" }
];
const SHEET_BLOCK = "sheet";
const LEGACY_BLOCK = "data";
function emptySheet() {
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
        cha: { bonus: 0, proficient: false }
      }
    },
    custom: []
  };
}
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
  cha: "cha"
};
const LEGACY_SCALARS = {
  ac: "ac",
  "armor class": "ac",
  "armour class": "ac",
  speed: "speed",
  level: "level"
};
function importLegacySheet(legacy) {
  const sheet = emptySheet();
  for (const stat of legacy) {
    const name = stat.name.trim().toLowerCase();
    const ability = LEGACY_ABILITY_NAMES[name];
    if (ability !== void 0 && stat.type === "number") {
      sheet.abilities[ability] = stat.value;
      continue;
    }
    const scalar = LEGACY_SCALARS[name];
    if (scalar !== void 0 && stat.type === "number") {
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
const BLOCK_NAME = "presets";
let block;
let pending;
const library = ref({});
const presetLibrary = library;
function ensurePresets() {
  pending ?? (pending = load());
  return pending;
}
async function load() {
  const dataBlock = await api.getOrLoadDataBlock(
    { category: "room", name: BLOCK_NAME },
    { defaultData: () => ({}) }
  );
  if (dataBlock !== void 0) {
    block = dataBlock;
    if (migrateLegacyEntries(dataBlock.reactiveData.value)) dataBlock.sync();
    library.value = dataBlock.reactiveData.value;
    watch(dataBlock.reactiveData, (value) => {
      if (migrateLegacyEntries(value)) dataBlock.sync();
      library.value = value;
    });
  }
  return dataBlock;
}
function migrateLegacyEntries(entries) {
  let changed = false;
  for (const [name, value] of Object.entries(entries)) {
    if (!Array.isArray(value)) continue;
    const { trackerIds: _t, derived: _d, ...preset } = importLegacySheet(value);
    entries[name] = preset;
    changed = true;
  }
  return changed;
}
function detach(value) {
  return JSON.parse(JSON.stringify(value));
}
function toPreset(sheet) {
  const { trackerIds: _trackerIds, derived: _derived, ...preset } = detach(sheet);
  return preset;
}
function getPreset(name) {
  const stats = library.value[name];
  return stats === void 0 ? void 0 : detach(stats);
}
async function savePreset(name, stats) {
  const dataBlock = block ?? await ensurePresets();
  if (dataBlock === void 0) return false;
  dataBlock.reactiveData.value[name] = detach(stats);
  dataBlock.sync();
  return true;
}
async function deletePreset(name) {
  const dataBlock = block ?? await ensurePresets();
  if (dataBlock === void 0 || !(name in dataBlock.reactiveData.value)) return false;
  delete dataBlock.reactiveData.value[name];
  dataBlock.sync();
  return true;
}
function abilityMod(score) {
  return Math.floor((score - 10) / 2);
}
function proficiencyBonus(level) {
  return 2 + Math.floor((clampLevel(level) - 1) / 4);
}
const MAX_LEVEL = 2;
function clampLevel(level) {
  if (!Number.isFinite(level)) return 1;
  return Math.min(MAX_LEVEL, Math.max(1, Math.floor(level)));
}
function signed(value) {
  return `${value >= 0 ? "+" : "-"}${Math.abs(value)}`;
}
function withModifier(dice, modifier) {
  return modifier === 0 ? dice : `${dice}${signed(modifier)}`;
}
function d20Roll(modifier, bias = "normal") {
  const dice = bias === "normal" ? "1d20" : bias === "advantage" ? "2d20kh1" : "2d20kl1";
  return withModifier(dice, modifier);
}
function cantripDice(level) {
  const lvl = clampLevel(level);
  if (lvl >= 17) return 4;
  if (lvl >= 11) return 3;
  if (lvl >= 5) return 2;
  return 1;
}
function scaleDice(dice, factor) {
  const match = /^(\d*)d(\d+)$/.exec(dice.trim());
  if (match === null) return dice;
  const count = Number.parseInt(match[1] === "" ? "1" : match[1], 10);
  return `${count * factor}d${match[2]}`;
}
function savingThrows(abilities, proficiency, proficientIn) {
  const out = {};
  const trained = new Set(proficientIn);
  for (const { key } of ABILITIES) {
    const proficient = trained.has(key);
    out[key] = {
      bonus: abilityMod(abilities[key]) + (proficient ? proficiency : 0),
      proficient
    };
  }
  return out;
}
function spellSaveDc(proficiency, abilityModifier) {
  return 8 + proficiency + abilityModifier;
}
function attackAbility(weapon, abilities) {
  if (weapon.kind === "ranged") return "dex";
  if (weapon.finesse === true) return abilities.dex > abilities.str ? "dex" : "str";
  return "str";
}
function deriveApplies(applies, proficiency, abilityModifier) {
  if (applies === void 0) return null;
  const condition = findCondition(applies.condition);
  if (condition === void 0) return null;
  return {
    condition: condition.id,
    name: condition.name,
    save: applies.save ?? null,
    dc: applies.save === void 0 ? null : spellSaveDc(proficiency, abilityModifier)
  };
}
function deriveAttack(weapon, abilities, proficiency) {
  if (weapon === void 0) return null;
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
    applies: deriveApplies(weapon.applies, proficiency, mod)
  };
}
function castingAbility(sheet) {
  var _a;
  return ((_a = findClass(sheet.classId)) == null ? void 0 : _a.spellcastingAbility) ?? null;
}
function canCast(sheet) {
  return castingAbility(sheet) !== null;
}
function availableCantrips(sheet) {
  const classId = sheet.classId;
  if (classId === null || !canCast(sheet)) return [];
  return catalogue.value.cantrips.filter((c) => (c.classes ?? []).includes(classId));
}
function deriveCantrip(cantrip, sheet, proficiency) {
  if (cantrip === void 0) return null;
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
    closeRangeDisadvantage: isAttack && cantrip.melee !== true
  };
}
function deriveSheet(sheet) {
  var _a;
  const proficiency = proficiencyBonus(sheet.level);
  const mods = {};
  for (const { key } of ABILITIES) mods[key] = abilityMod(sheet.abilities[key]);
  const ability = castingAbility(sheet);
  return {
    proficiency,
    mods,
    melee: deriveAttack(findWeapon(sheet.equipped.melee), sheet.abilities, proficiency),
    ranged: deriveAttack(findWeapon(sheet.equipped.ranged), sheet.abilities, proficiency),
    cantrip: deriveCantrip(findCantrip(sheet.equipped.cantrip), sheet, proficiency),
    spellSaveDc: ability === null ? null : spellSaveDc(proficiency, mods[ability]),
    saves: savingThrows(sheet.abilities, proficiency, ((_a = findClass(sheet.classId)) == null ? void 0 : _a.savingThrows) ?? [])
  };
}
function suggestedMaxHp(sheet) {
  const klass = findClass(sheet.classId);
  if (klass === void 0) return void 0;
  const level = clampLevel(sheet.level);
  const con = abilityMod(sheet.abilities.con);
  const perLevel = Math.ceil(klass.hitDie / 2) + 1;
  return Math.max(1, klass.hitDie + con + (level - 1) * (perLevel + con));
}
const SYNC = { ui: true, server: true };
const HP_COLOUR = "#ff7052";
const AC_COLOUR = "#82c8a0";
function newTrackerId() {
  var _a, _b;
  const uuid = ((_b = (_a = globalThis.crypto) == null ? void 0 : _a.randomUUID) == null ? void 0 : _b.call(_a)) ?? `scc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return uuid;
}
function upsert(shape, id, tracker) {
  const trackers = api.systems.trackers;
  if (id !== null && trackers.get(shape, id) !== void 0) {
    trackers.update(shape, id, tracker, SYNC);
    return id;
  }
  const uuid = newTrackerId();
  trackers.add(shape, { ...tracker, uuid }, SYNC);
  return uuid;
}
function syncTrackers(shape, sheet) {
  const before = `${sheet.trackerIds.hp}/${sheet.trackerIds.ac}`;
  sheet.trackerIds.hp = upsert(shape, sheet.trackerIds.hp, {
    name: "HP",
    value: sheet.hp.current + sheet.hp.temp,
    maxvalue: sheet.hp.max,
    visible: true,
    // The only one drawn on the token; two overlapping bars is noise.
    draw: true,
    primaryColor: HP_COLOUR,
    secondaryColor: "#000000"
  });
  sheet.trackerIds.ac = upsert(shape, sheet.trackerIds.ac, {
    name: "AC",
    value: sheet.ac,
    maxvalue: sheet.ac,
    visible: true,
    draw: false,
    primaryColor: AC_COLOUR,
    secondaryColor: "#000000"
  });
  return `${sheet.trackerIds.hp}/${sheet.trackerIds.ac}` !== before;
}
function adoptTrackers(shape, sheet) {
  let changed = false;
  for (const [key, name] of [
    ["hp", "HP"],
    ["ac", "AC"]
  ]) {
    if (sheet.trackerIds[key] !== null) continue;
    const existing = api.systems.trackers.getAll(shape).find((t) => t.name.trim().toUpperCase() === name);
    if (existing !== void 0) {
      sheet.trackerIds[key] = existing.uuid;
      changed = true;
    }
  }
  return changed;
}
function readBackFromTrackers(shape, sheet) {
  let changed = false;
  const trackers = api.systems.trackers;
  const hpId = sheet.trackerIds.hp;
  if (hpId !== null) {
    const tracker = trackers.get(shape, hpId);
    if (tracker !== void 0) {
      const current2 = tracker.value - sheet.hp.temp;
      if (current2 !== sheet.hp.current || tracker.maxvalue !== sheet.hp.max) {
        sheet.hp.current = current2;
        sheet.hp.max = tracker.maxvalue;
        changed = true;
      }
    }
  }
  const acId = sheet.trackerIds.ac;
  if (acId !== null) {
    const tracker = trackers.get(shape, acId);
    if (tracker !== void 0 && tracker.value !== sheet.ac) {
      sheet.ac = tracker.value;
      changed = true;
    }
  }
  return changed;
}
function fillDefaults(sheet) {
  const base = emptySheet();
  let changed = false;
  for (const [key, value] of Object.entries(base)) {
    if (sheet[key] === void 0) {
      sheet[key] = value;
      changed = true;
    }
  }
  for (const key of ["equipped", "hp", "trackerIds", "abilities", "derived"]) {
    for (const [nested, value] of Object.entries(base[key])) {
      const target = sheet[key];
      if (target[nested] === void 0) {
        target[nested] = value;
        changed = true;
      }
    }
  }
  return changed;
}
async function loadBlock(shape) {
  const repr = { category: "shape", shape, name: SHEET_BLOCK };
  const existing = await api.getOrLoadDataBlock(repr);
  if (existing !== void 0) {
    if (fillDefaults(existing.reactiveData.value)) existing.sync();
    return existing;
  }
  const legacy = await api.getOrLoadDataBlock({
    category: "shape",
    shape,
    name: LEGACY_BLOCK
  });
  const initial = legacy === void 0 ? emptySheet() : importLegacySheet(legacy.data);
  return await api.getOrLoadDataBlock(repr, { defaultData: () => initial });
}
function useSheet() {
  let block2;
  let shapeId;
  const internal = ref(emptySheet());
  async function load2(shape, localId) {
    block2 = void 0;
    shapeId = localId;
    const loaded = await loadBlock(shape);
    if (loaded === void 0) return;
    block2 = loaded;
    internal.value = loaded.reactiveData.value;
    watch(loaded.reactiveData, (value) => {
      internal.value = value;
    });
    const adopted = adoptTrackers(localId, internal.value);
    const readBack = readBackFromTrackers(localId, internal.value);
    if (adopted || readBack) save();
  }
  function write(value) {
    block2 == null ? void 0 : block2.updateData(value);
  }
  function save() {
    if (block2 === void 0) return;
    internal.value.derived = deriveSheet(internal.value);
    if (shapeId !== void 0) syncTrackers(shapeId, internal.value);
    block2.sync();
  }
  return { data: shallowReadonly(internal), load: load2, save, write };
}
const _hoisted_1 = { id: "scc" };
const _hoisted_2 = {
  key: 0,
  class: "starter"
};
const _hoisted_3 = { class: "inline" };
const _hoisted_4 = ["value"];
const _hoisted_5 = ["disabled"];
const _hoisted_6 = { class: "grid" };
const _hoisted_7 = ["value"];
const _hoisted_8 = ["value"];
const _hoisted_9 = ["value"];
const _hoisted_10 = { class: "inline" };
const _hoisted_11 = ["max"];
const _hoisted_12 = { class: "muted" };
const _hoisted_13 = {
  key: 1,
  class: "muted"
};
const _hoisted_14 = { class: "muted small next-up" };
const _hoisted_15 = {
  key: 0,
  class: "passives"
};
const _hoisted_16 = { class: "muted" };
const _hoisted_17 = { class: "abilities" };
const _hoisted_18 = ["for", "title"];
const _hoisted_19 = ["id", "onUpdate:modelValue"];
const _hoisted_20 = { class: "mod" };
const _hoisted_21 = { class: "conditions" };
const _hoisted_22 = ["aria-pressed", "title", "onClick"];
const _hoisted_23 = {
  key: 0,
  class: "passives"
};
const _hoisted_24 = {
  key: 1,
  class: "muted small"
};
const _hoisted_25 = { class: "abilities" };
const _hoisted_26 = ["title"];
const _hoisted_27 = { class: "mod" };
const _hoisted_28 = { class: "prof" };
const _hoisted_29 = { class: "grid" };
const _hoisted_30 = { class: "inline" };
const _hoisted_31 = { class: "inline" };
const _hoisted_32 = { class: "attacks" };
const _hoisted_33 = { label: "Weapons" };
const _hoisted_34 = ["value"];
const _hoisted_35 = { label: "Natural" };
const _hoisted_36 = ["value"];
const _hoisted_37 = { key: 0 };
const _hoisted_38 = {
  key: 1,
  class: "muted"
};
const _hoisted_39 = { key: 0 };
const _hoisted_40 = {
  key: 1,
  class: "muted"
};
const _hoisted_41 = { label: "Weapons" };
const _hoisted_42 = ["value"];
const _hoisted_43 = {
  key: 0,
  label: "Natural"
};
const _hoisted_44 = ["value"];
const _hoisted_45 = { key: 0 };
const _hoisted_46 = {
  key: 1,
  class: "muted"
};
const _hoisted_47 = { key: 0 };
const _hoisted_48 = {
  key: 1,
  class: "muted"
};
const _hoisted_49 = { key: 1 };
const _hoisted_50 = { class: "grid" };
const _hoisted_51 = { class: "inline" };
const _hoisted_52 = ["value"];
const _hoisted_53 = { class: "muted" };
const _hoisted_54 = {
  key: 0,
  class: "attacks"
};
const _hoisted_55 = { scope: "row" };
const _hoisted_56 = { key: 0 };
const _hoisted_57 = { key: 1 };
const _hoisted_58 = { class: "muted" };
const _hoisted_59 = {
  key: 1,
  class: "warn small"
};
const _hoisted_60 = {
  key: 2,
  class: "muted small"
};
const _hoisted_61 = {
  key: 3,
  class: "muted small"
};
const _hoisted_62 = { key: 2 };
const _hoisted_63 = { class: "grid" };
const _hoisted_64 = { class: "inline" };
const _hoisted_65 = ["value"];
const _hoisted_66 = {
  class: "inline",
  role: "group",
  "aria-labelledby": "scc-token-flags-label"
};
const _hoisted_67 = ["checked"];
const _hoisted_68 = ["checked"];
const _hoisted_69 = ["checked"];
const _hoisted_70 = { class: "grid" };
const _hoisted_71 = ["for"];
const _hoisted_72 = { class: "inline" };
const _hoisted_73 = ["id", "onUpdate:modelValue"];
const _hoisted_74 = ["id", "onUpdate:modelValue"];
const _hoisted_75 = ["id", "onUpdate:modelValue"];
const _hoisted_76 = ["title", "onClick"];
const _hoisted_77 = { class: "inline" };
const _hoisted_78 = ["disabled"];
const _hoisted_79 = { class: "grid" };
const _hoisted_80 = { class: "inline" };
const _hoisted_81 = ["value"];
const _hoisted_82 = ["disabled"];
const _hoisted_83 = ["disabled"];
const _hoisted_84 = { class: "inline" };
const _hoisted_85 = ["disabled"];
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "CharTab",
  setup(__props) {
    const SYNC2 = { ui: true, server: true };
    const { data, load: load2, save, write } = useSheet();
    const localId = computed(() => {
      var _a;
      const charId = api.systemsState.characters.reactive.activeCharacterId;
      if (charId === void 0) return void 0;
      return (_a = api.systems.characters.getShape(charId)) == null ? void 0 : _a.id;
    });
    watch(
      () => api.systemsState.characters.reactive.activeCharacterId,
      async (charId) => {
        var _a;
        if (charId === void 0) return;
        const shapeId = api.systems.characters.getShapeId(charId);
        const local = (_a = api.systems.characters.getShape(charId)) == null ? void 0 : _a.id;
        if (shapeId !== void 0 && local !== void 0) await load2(shapeId, local);
      },
      // Without `immediate` the component would mount against an already-selected
      // character and never load it, because a watcher is lazy by default.
      { immediate: true }
    );
    onMounted(() => {
      void ensureCatalogue();
      void ensurePresets();
    });
    const race = computed(() => findRace(data.value.raceId));
    const background = computed(() => findBackground(data.value.backgroundId));
    const klass = computed(() => findClass(data.value.classId));
    const passives = computed(
      () => [race.value, background.value, klass.value].filter((t) => t !== void 0).map((t) => ({ source: t.name, ...t.passive }))
    );
    const meleeWeapons = computed(() => weaponGroups("melee"));
    const rangedWeapons = computed(() => weaponGroups("ranged"));
    const spellAbility = computed(() => castingAbility(data.value));
    const cantrip = computed(() => findCantrip(data.value.equipped.cantrip));
    const isCaster = computed(() => canCast(data.value));
    const cantripChoices = computed(() => availableCantrips(data.value));
    const activeConditions = computed(
      () => data.value.conditions.map(findCondition).filter((c) => c !== void 0)
    );
    function toggleCondition(id) {
      const list = data.value.conditions;
      const at = list.indexOf(id);
      if (at === -1) list.push(id);
      else list.splice(at, 1);
      const condition = findCondition(id);
      if ((condition == null ? void 0 : condition.impliesDefeated) === true && localId.value !== void 0) {
        api.systems.properties.setIsDefeated(localId.value, at === -1, SYNC2);
      }
      save();
    }
    const canLevelUp = computed(() => data.value.classId !== null && data.value.level < MAX_LEVEL);
    const nextFeature = computed(() => {
      var _a;
      return canLevelUp.value ? (_a = klass.value) == null ? void 0 : _a.level2 : void 0;
    });
    function levelUp() {
      if (!canLevelUp.value) return;
      data.value.level = data.value.level + 1;
      const klassDef = klass.value;
      if (klassDef) {
        const gain = Math.max(1, Math.ceil(klassDef.hitDie / 2) + 1 + abilityMod(data.value.abilities.con));
        data.value.hp.max += gain;
        data.value.hp.current += gain;
      }
      save();
    }
    const derived = computed(() => data.value.derived);
    const hpSuggestion = computed(() => {
      const suggested = suggestedMaxHp(data.value);
      return suggested === void 0 || suggested === data.value.hp.max ? void 0 : suggested;
    });
    function applyHpSuggestion() {
      const suggested = hpSuggestion.value;
      if (suggested === void 0) return;
      data.value.hp.max = suggested;
      if (data.value.hp.current === 0 || data.value.hp.current > suggested) {
        data.value.hp.current = suggested;
      }
      save();
    }
    const properties = computed(() => {
      const id = localId.value;
      return id === void 0 ? void 0 : api.systemsState.properties.reactive.data.get(id);
    });
    const tokenName = ref("");
    watch(properties, (props) => tokenName.value = (props == null ? void 0 : props.name) ?? "", { immediate: true });
    function commitTokenName() {
      const id = localId.value;
      if (id === void 0 || tokenName.value.length === 0) return;
      api.systems.properties.setName(id, tokenName.value, SYNC2);
    }
    function setNameVisible(visible) {
      if (localId.value !== void 0) api.systems.properties.setNameVisible(localId.value, visible, SYNC2);
    }
    function setLocked(locked) {
      if (localId.value !== void 0) api.systems.properties.setLocked(localId.value, locked, SYNC2);
    }
    function setDefeated(defeated) {
      if (localId.value !== void 0) api.systems.properties.setIsDefeated(localId.value, defeated, SYNC2);
    }
    function setSize(value) {
      if (localId.value !== void 0) api.systems.properties.setSize(localId.value, { x: value, y: value }, SYNC2);
    }
    const extraOptions = ["Text", "Number", "Checkbox"];
    const selectedOption = ref(extraOptions[0]);
    const selectedName = ref("");
    function addOption() {
      const name = selectedName.value.trim();
      if (name.length === 0 || data.value.custom.some((s) => s.name === name)) return;
      let stat;
      if (selectedOption.value === "Checkbox") stat = { name, type: "check", value: false };
      else if (selectedOption.value === "Number") stat = { name, type: "number", value: 0 };
      else stat = { name, type: "string", value: "" };
      data.value.custom.push(stat);
      selectedName.value = "";
      save();
    }
    function removeOption(name) {
      data.value.custom = data.value.custom.filter((s) => s.name !== name);
      save();
    }
    const isBlank = computed(
      () => data.value.classId === null && data.value.raceId === null && data.value.level === 1 && data.value.hp.max === 0 && data.value.custom.length === 0 && Object.values(data.value.abilities).every((v) => v === 10)
    );
    const selectedPreset = ref("");
    const presetName = ref("");
    const presetNames = computed(() => Object.keys(presetLibrary.value).sort());
    function applyPreset() {
      const preset = getPreset(selectedPreset.value);
      if (preset === void 0) return;
      write({ ...preset, trackerIds: data.value.trackerIds, derived: data.value.derived });
      save();
    }
    async function storePreset() {
      const name = presetName.value.trim();
      if (name.length === 0) return;
      if (await savePreset(name, toPreset(data.value))) {
        selectedPreset.value = name;
        presetName.value = "";
      }
    }
    async function removePreset() {
      if (await deletePreset(selectedPreset.value)) selectedPreset.value = "";
    }
    return (_ctx, _cache) => {
      var _a, _b, _c, _d;
      const _component_font_awesome_icon = resolveComponent("font-awesome-icon");
      return openBlock(), createElementBlock("div", _hoisted_1, [
        isBlank.value && presetNames.value.length > 0 ? (openBlock(), createElementBlock("section", _hoisted_2, [
          _cache[42] || (_cache[42] = createElementVNode("h3", null, "Start from a preset", -1)),
          createElementVNode("div", _hoisted_3, [
            withDirectives(createElementVNode("select", {
              "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => selectedPreset.value = $event)
            }, [
              _cache[40] || (_cache[40] = createElementVNode("option", { value: "" }, "—", -1)),
              (openBlock(true), createElementBlock(Fragment, null, renderList(presetNames.value, (name) => {
                return openBlock(), createElementBlock("option", {
                  key: name,
                  value: name
                }, toDisplayString(name), 9, _hoisted_4);
              }), 128))
            ], 512), [
              [vModelSelect, selectedPreset.value]
            ]),
            createElementVNode("button", {
              type: "button",
              disabled: selectedPreset.value.length === 0,
              onClick: applyPreset
            }, " Use this preset ", 8, _hoisted_5),
            _cache[41] || (_cache[41] = createElementVNode("span", { class: "muted small" }, "or just fill the sheet in below", -1))
          ])
        ])) : createCommentVNode("", true),
        createElementVNode("section", null, [
          _cache[54] || (_cache[54] = createElementVNode("h3", null, "Identity", -1)),
          createElementVNode("div", _hoisted_6, [
            _cache[49] || (_cache[49] = createElementVNode("label", { for: "scc-token-name" }, "Token name", -1)),
            withDirectives(createElementVNode("input", {
              id: "scc-token-name",
              "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => tokenName.value = $event),
              type: "text",
              onChange: commitTokenName
            }, null, 544), [
              [vModelText, tokenName.value]
            ]),
            _cache[50] || (_cache[50] = createElementVNode("label", { for: "scc-race" }, "Race", -1)),
            withDirectives(createElementVNode("select", {
              id: "scc-race",
              "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => unref(data).raceId = $event),
              onChange: _cache[3] || (_cache[3] = //@ts-ignore
              (...args) => unref(save) && unref(save)(...args))
            }, [
              _cache[43] || (_cache[43] = createElementVNode("option", { value: null }, "—", -1)),
              (openBlock(true), createElementBlock(Fragment, null, renderList(unref(catalogue).races, (r) => {
                return openBlock(), createElementBlock("option", {
                  key: r.id,
                  value: r.id
                }, toDisplayString(r.name), 9, _hoisted_7);
              }), 128))
            ], 544), [
              [vModelSelect, unref(data).raceId]
            ]),
            _cache[51] || (_cache[51] = createElementVNode("label", { for: "scc-background" }, "Background", -1)),
            withDirectives(createElementVNode("select", {
              id: "scc-background",
              "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => unref(data).backgroundId = $event),
              onChange: _cache[5] || (_cache[5] = //@ts-ignore
              (...args) => unref(save) && unref(save)(...args))
            }, [
              _cache[44] || (_cache[44] = createElementVNode("option", { value: null }, "—", -1)),
              (openBlock(true), createElementBlock(Fragment, null, renderList(unref(catalogue).backgrounds, (b) => {
                return openBlock(), createElementBlock("option", {
                  key: b.id,
                  value: b.id
                }, toDisplayString(b.name), 9, _hoisted_8);
              }), 128))
            ], 544), [
              [vModelSelect, unref(data).backgroundId]
            ]),
            _cache[52] || (_cache[52] = createElementVNode("label", { for: "scc-class" }, "Class", -1)),
            withDirectives(createElementVNode("select", {
              id: "scc-class",
              "onUpdate:modelValue": _cache[6] || (_cache[6] = ($event) => unref(data).classId = $event),
              onChange: _cache[7] || (_cache[7] = //@ts-ignore
              (...args) => unref(save) && unref(save)(...args))
            }, [
              _cache[45] || (_cache[45] = createElementVNode("option", { value: null }, "—", -1)),
              (openBlock(true), createElementBlock(Fragment, null, renderList(unref(catalogue).classes, (c) => {
                return openBlock(), createElementBlock("option", {
                  key: c.id,
                  value: c.id
                }, toDisplayString(c.name) + " (d" + toDisplayString(c.hitDie) + ") ", 9, _hoisted_9);
              }), 128))
            ], 544), [
              [vModelSelect, unref(data).classId]
            ]),
            _cache[53] || (_cache[53] = createElementVNode("label", { for: "scc-level" }, "Level", -1)),
            createElementVNode("div", _hoisted_10, [
              withDirectives(createElementVNode("input", {
                id: "scc-level",
                "onUpdate:modelValue": _cache[8] || (_cache[8] = ($event) => unref(data).level = $event),
                type: "number",
                min: "1",
                max: unref(MAX_LEVEL),
                onChange: _cache[9] || (_cache[9] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 40, _hoisted_11), [
                [
                  vModelText,
                  unref(data).level,
                  void 0,
                  { number: true }
                ]
              ]),
              createElementVNode("span", _hoisted_12, "proficiency " + toDisplayString(unref(signed)(derived.value.proficiency)), 1),
              canLevelUp.value ? (openBlock(), createElementBlock("button", {
                key: 0,
                type: "button",
                class: "levelup",
                onClick: levelUp
              }, [
                createVNode(_component_font_awesome_icon, { icon: "arrow-up" }),
                _cache[46] || (_cache[46] = createTextVNode(" Level up "))
              ])) : unref(data).level >= unref(MAX_LEVEL) ? (openBlock(), createElementBlock("span", _hoisted_13, "max for this campaign")) : createCommentVNode("", true)
            ]),
            nextFeature.value ? (openBlock(), createElementBlock(Fragment, { key: 0 }, [
              _cache[48] || (_cache[48] = createElementVNode("span", null, null, -1)),
              createElementVNode("p", _hoisted_14, [
                _cache[47] || (_cache[47] = createTextVNode(" Next level: ")),
                createElementVNode("strong", null, toDisplayString(nextFeature.value.name), 1),
                createTextVNode(" — " + toDisplayString(nextFeature.value.text), 1)
              ])
            ], 64)) : createCommentVNode("", true)
          ]),
          passives.value.length > 0 ? (openBlock(), createElementBlock("ul", _hoisted_15, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(passives.value, (p) => {
              return openBlock(), createElementBlock("li", {
                key: p.source + p.name
              }, [
                createElementVNode("strong", null, toDisplayString(p.name), 1),
                createElementVNode("span", _hoisted_16, " · " + toDisplayString(p.source), 1),
                createElementVNode("div", null, toDisplayString(p.text), 1)
              ]);
            }), 128))
          ])) : createCommentVNode("", true)
        ]),
        createElementVNode("section", null, [
          _cache[55] || (_cache[55] = createElementVNode("h3", null, "Abilities", -1)),
          createElementVNode("div", _hoisted_17, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(unref(ABILITIES), (a) => {
              return openBlock(), createElementBlock("div", {
                key: a.key,
                class: "ability"
              }, [
                createElementVNode("label", {
                  for: "scc-" + a.key,
                  title: a.long
                }, toDisplayString(a.label), 9, _hoisted_18),
                withDirectives(createElementVNode("input", {
                  id: "scc-" + a.key,
                  "onUpdate:modelValue": ($event) => unref(data).abilities[a.key] = $event,
                  type: "number",
                  min: "1",
                  max: "30",
                  onChange: _cache[10] || (_cache[10] = //@ts-ignore
                  (...args) => unref(save) && unref(save)(...args))
                }, null, 40, _hoisted_19), [
                  [
                    vModelText,
                    unref(data).abilities[a.key],
                    void 0,
                    { number: true }
                  ]
                ]),
                createElementVNode("span", _hoisted_20, toDisplayString(unref(signed)(unref(abilityMod)(unref(data).abilities[a.key]))), 1)
              ]);
            }), 128))
          ])
        ]),
        createElementVNode("section", null, [
          _cache[56] || (_cache[56] = createElementVNode("h3", null, "Conditions", -1)),
          createElementVNode("div", _hoisted_21, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(unref(catalogue).conditions, (c) => {
              return openBlock(), createElementBlock("button", {
                key: c.id,
                type: "button",
                class: normalizeClass(["chip", { on: unref(data).conditions.includes(c.id) }]),
                "aria-pressed": unref(data).conditions.includes(c.id),
                title: c.text,
                onClick: ($event) => toggleCondition(c.id)
              }, toDisplayString(c.name), 11, _hoisted_22);
            }), 128))
          ]),
          activeConditions.value.length > 0 ? (openBlock(), createElementBlock("ul", _hoisted_23, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(activeConditions.value, (c) => {
              return openBlock(), createElementBlock("li", {
                key: c.id
              }, [
                createElementVNode("strong", null, toDisplayString(c.name), 1),
                createElementVNode("div", null, toDisplayString(c.text), 1)
              ]);
            }), 128))
          ])) : (openBlock(), createElementBlock("p", _hoisted_24, "None. Click one to apply it."))
        ]),
        createElementVNode("section", null, [
          _cache[57] || (_cache[57] = createElementVNode("h3", null, "Saving throws", -1)),
          createElementVNode("div", _hoisted_25, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(unref(ABILITIES), (a) => {
              return openBlock(), createElementBlock("div", {
                key: a.key,
                class: normalizeClass(["ability", { trained: derived.value.saves[a.key].proficient }])
              }, [
                createElementVNode("span", {
                  class: "lbl",
                  title: a.long
                }, toDisplayString(a.label), 9, _hoisted_26),
                createElementVNode("span", _hoisted_27, toDisplayString(unref(signed)(derived.value.saves[a.key].bonus)), 1),
                createElementVNode("span", _hoisted_28, toDisplayString(derived.value.saves[a.key].proficient ? "proficient" : " "), 1)
              ], 2);
            }), 128))
          ])
        ]),
        createElementVNode("section", null, [
          _cache[69] || (_cache[69] = createElementVNode("h3", null, "Combat", -1)),
          createElementVNode("div", _hoisted_29, [
            _cache[62] || (_cache[62] = createElementVNode("label", { for: "scc-hp" }, "Hit points", -1)),
            createElementVNode("div", _hoisted_30, [
              withDirectives(createElementVNode("input", {
                id: "scc-hp",
                "onUpdate:modelValue": _cache[11] || (_cache[11] = ($event) => unref(data).hp.current = $event),
                type: "number",
                onChange: _cache[12] || (_cache[12] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 544), [
                [
                  vModelText,
                  unref(data).hp.current,
                  void 0,
                  { number: true }
                ]
              ]),
              _cache[58] || (_cache[58] = createElementVNode("span", { class: "muted" }, "/", -1)),
              withDirectives(createElementVNode("input", {
                "onUpdate:modelValue": _cache[13] || (_cache[13] = ($event) => unref(data).hp.max = $event),
                type: "number",
                min: "0",
                onChange: _cache[14] || (_cache[14] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 544), [
                [
                  vModelText,
                  unref(data).hp.max,
                  void 0,
                  { number: true }
                ]
              ]),
              _cache[59] || (_cache[59] = createElementVNode("span", { class: "muted" }, "temp", -1)),
              withDirectives(createElementVNode("input", {
                "onUpdate:modelValue": _cache[15] || (_cache[15] = ($event) => unref(data).hp.temp = $event),
                type: "number",
                min: "0",
                onChange: _cache[16] || (_cache[16] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 544), [
                [
                  vModelText,
                  unref(data).hp.temp,
                  void 0,
                  { number: true }
                ]
              ]),
              hpSuggestion.value !== void 0 ? (openBlock(), createElementBlock("button", {
                key: 0,
                type: "button",
                onClick: applyHpSuggestion
              }, " use " + toDisplayString(hpSuggestion.value), 1)) : createCommentVNode("", true)
            ]),
            _cache[63] || (_cache[63] = createElementVNode("label", { for: "scc-ac" }, "Armour class", -1)),
            createElementVNode("div", _hoisted_31, [
              withDirectives(createElementVNode("input", {
                id: "scc-ac",
                "onUpdate:modelValue": _cache[17] || (_cache[17] = ($event) => unref(data).ac = $event),
                type: "number",
                min: "0",
                onChange: _cache[18] || (_cache[18] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 544), [
                [
                  vModelText,
                  unref(data).ac,
                  void 0,
                  { number: true }
                ]
              ]),
              _cache[60] || (_cache[60] = createElementVNode("label", {
                for: "scc-speed",
                class: "muted"
              }, "speed", -1)),
              withDirectives(createElementVNode("input", {
                id: "scc-speed",
                "onUpdate:modelValue": _cache[19] || (_cache[19] = ($event) => unref(data).speed = $event),
                type: "number",
                min: "0",
                onChange: _cache[20] || (_cache[20] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 544), [
                [
                  vModelText,
                  unref(data).speed,
                  void 0,
                  { number: true }
                ]
              ]),
              _cache[61] || (_cache[61] = createElementVNode("span", { class: "muted" }, "ft", -1))
            ])
          ]),
          createElementVNode("table", _hoisted_32, [
            _cache[68] || (_cache[68] = createElementVNode("thead", null, [
              createElementVNode("tr", null, [
                createElementVNode("th", null, "Attack"),
                createElementVNode("th", null, "Weapon"),
                createElementVNode("th", null, "To hit"),
                createElementVNode("th", null, "Damage")
              ])
            ], -1)),
            createElementVNode("tbody", null, [
              createElementVNode("tr", null, [
                _cache[65] || (_cache[65] = createElementVNode("th", { scope: "row" }, "Melee", -1)),
                createElementVNode("td", null, [
                  withDirectives(createElementVNode("select", {
                    "onUpdate:modelValue": _cache[21] || (_cache[21] = ($event) => unref(data).equipped.melee = $event),
                    onChange: _cache[22] || (_cache[22] = //@ts-ignore
                    (...args) => unref(save) && unref(save)(...args))
                  }, [
                    _cache[64] || (_cache[64] = createElementVNode("option", { value: null }, "—", -1)),
                    createElementVNode("optgroup", _hoisted_33, [
                      (openBlock(true), createElementBlock(Fragment, null, renderList(meleeWeapons.value.carried, (w) => {
                        return openBlock(), createElementBlock("option", {
                          key: w.id,
                          value: w.id
                        }, toDisplayString(w.name), 9, _hoisted_34);
                      }), 128))
                    ]),
                    createElementVNode("optgroup", _hoisted_35, [
                      (openBlock(true), createElementBlock(Fragment, null, renderList(meleeWeapons.value.natural, (w) => {
                        return openBlock(), createElementBlock("option", {
                          key: w.id,
                          value: w.id
                        }, toDisplayString(w.name), 9, _hoisted_36);
                      }), 128))
                    ])
                  ], 544), [
                    [vModelSelect, unref(data).equipped.melee]
                  ])
                ]),
                createElementVNode("td", null, [
                  derived.value.melee ? (openBlock(), createElementBlock("code", _hoisted_37, toDisplayString(derived.value.melee.attack), 1)) : (openBlock(), createElementBlock("span", _hoisted_38, "—"))
                ]),
                createElementVNode("td", null, [
                  derived.value.melee ? (openBlock(), createElementBlock("code", _hoisted_39, toDisplayString(derived.value.melee.damage), 1)) : (openBlock(), createElementBlock("span", _hoisted_40, "—"))
                ])
              ]),
              createElementVNode("tr", null, [
                _cache[67] || (_cache[67] = createElementVNode("th", { scope: "row" }, "Ranged", -1)),
                createElementVNode("td", null, [
                  withDirectives(createElementVNode("select", {
                    "onUpdate:modelValue": _cache[23] || (_cache[23] = ($event) => unref(data).equipped.ranged = $event),
                    onChange: _cache[24] || (_cache[24] = //@ts-ignore
                    (...args) => unref(save) && unref(save)(...args))
                  }, [
                    _cache[66] || (_cache[66] = createElementVNode("option", { value: null }, "—", -1)),
                    createElementVNode("optgroup", _hoisted_41, [
                      (openBlock(true), createElementBlock(Fragment, null, renderList(rangedWeapons.value.carried, (w) => {
                        return openBlock(), createElementBlock("option", {
                          key: w.id,
                          value: w.id
                        }, toDisplayString(w.name), 9, _hoisted_42);
                      }), 128))
                    ]),
                    rangedWeapons.value.natural.length > 0 ? (openBlock(), createElementBlock("optgroup", _hoisted_43, [
                      (openBlock(true), createElementBlock(Fragment, null, renderList(rangedWeapons.value.natural, (w) => {
                        return openBlock(), createElementBlock("option", {
                          key: w.id,
                          value: w.id
                        }, toDisplayString(w.name), 9, _hoisted_44);
                      }), 128))
                    ])) : createCommentVNode("", true)
                  ], 544), [
                    [vModelSelect, unref(data).equipped.ranged]
                  ])
                ]),
                createElementVNode("td", null, [
                  derived.value.ranged ? (openBlock(), createElementBlock("code", _hoisted_45, toDisplayString(derived.value.ranged.attack), 1)) : (openBlock(), createElementBlock("span", _hoisted_46, "—"))
                ]),
                createElementVNode("td", null, [
                  derived.value.ranged ? (openBlock(), createElementBlock("code", _hoisted_47, toDisplayString(derived.value.ranged.damage), 1)) : (openBlock(), createElementBlock("span", _hoisted_48, "—"))
                ])
              ])
            ])
          ]),
          _cache[70] || (_cache[70] = createElementVNode("p", { class: "muted small" }, " Attack rows are computed from ability scores, level and the equipped weapon. The ghost player rolls these exact numbers, and can roll any of them with advantage or disadvantage. ", -1))
        ]),
        isCaster.value ? (openBlock(), createElementBlock("section", _hoisted_49, [
          _cache[79] || (_cache[79] = createElementVNode("h3", null, "Spellcasting", -1)),
          createElementVNode("div", _hoisted_50, [
            _cache[72] || (_cache[72] = createElementVNode("label", { for: "scc-cantrip" }, "Cantrip", -1)),
            createElementVNode("div", _hoisted_51, [
              withDirectives(createElementVNode("select", {
                id: "scc-cantrip",
                "onUpdate:modelValue": _cache[25] || (_cache[25] = ($event) => unref(data).equipped.cantrip = $event),
                onChange: _cache[26] || (_cache[26] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, [
                _cache[71] || (_cache[71] = createElementVNode("option", { value: null }, "—", -1)),
                (openBlock(true), createElementBlock(Fragment, null, renderList(cantripChoices.value, (c) => {
                  return openBlock(), createElementBlock("option", {
                    key: c.id,
                    value: c.id
                  }, toDisplayString(c.name), 9, _hoisted_52);
                }), 128))
              ], 544), [
                [vModelSelect, unref(data).equipped.cantrip]
              ]),
              createElementVNode("span", _hoisted_53, toDisplayString((_a = klass.value) == null ? void 0 : _a.name) + " list · casts with " + toDisplayString((_b = spellAbility.value) == null ? void 0 : _b.toUpperCase()) + " · save DC " + toDisplayString(derived.value.spellSaveDc), 1)
            ])
          ]),
          derived.value.cantrip ? (openBlock(), createElementBlock("table", _hoisted_54, [
            createElementVNode("thead", null, [
              createElementVNode("tr", null, [
                _cache[73] || (_cache[73] = createElementVNode("th", null, "Cantrip", -1)),
                _cache[74] || (_cache[74] = createElementVNode("th", null, "Range", -1)),
                createElementVNode("th", null, toDisplayString(derived.value.cantrip.kind === "attack" ? "To hit" : "Save"), 1),
                _cache[75] || (_cache[75] = createElementVNode("th", null, "Damage", -1))
              ])
            ]),
            createElementVNode("tbody", null, [
              createElementVNode("tr", null, [
                createElementVNode("th", _hoisted_55, toDisplayString(derived.value.cantrip.name), 1),
                createElementVNode("td", null, toDisplayString(derived.value.cantrip.range) + toDisplayString(derived.value.cantrip.range === "touch" ? "" : " ft"), 1),
                createElementVNode("td", null, [
                  derived.value.cantrip.attack ? (openBlock(), createElementBlock("code", _hoisted_56, toDisplayString(derived.value.cantrip.attack), 1)) : (openBlock(), createElementBlock("span", _hoisted_57, "DC " + toDisplayString(derived.value.cantrip.saveDc) + " " + toDisplayString((_c = derived.value.cantrip.save) == null ? void 0 : _c.toUpperCase()), 1))
                ]),
                createElementVNode("td", null, [
                  createElementVNode("code", null, toDisplayString(derived.value.cantrip.damage), 1),
                  createElementVNode("span", _hoisted_58, toDisplayString(derived.value.cantrip.damageType), 1)
                ])
              ])
            ])
          ])) : createCommentVNode("", true),
          ((_d = derived.value.cantrip) == null ? void 0 : _d.closeRangeDisadvantage) ? (openBlock(), createElementBlock("p", _hoisted_59, [
            _cache[76] || (_cache[76] = createTextVNode(" Ranged spell attack: ")),
            _cache[77] || (_cache[77] = createElementVNode("strong", null, "disadvantage", -1)),
            _cache[78] || (_cache[78] = createTextVNode(" while a hostile creature is within 5 ft — ")),
            createElementVNode("code", null, toDisplayString(derived.value.cantrip.attackDisadvantage), 1)
          ])) : createCommentVNode("", true),
          cantrip.value ? (openBlock(), createElementBlock("p", _hoisted_60, toDisplayString(cantrip.value.text), 1)) : createCommentVNode("", true),
          derived.value.cantrip ? (openBlock(), createElementBlock("p", _hoisted_61, " Cantrip damage scales with character level and takes no ability modifier. ")) : createCommentVNode("", true)
        ])) : createCommentVNode("", true),
        createElementVNode("section", null, [
          _cache[80] || (_cache[80] = createElementVNode("h3", null, "Description", -1)),
          withDirectives(createElementVNode("textarea", {
            "onUpdate:modelValue": _cache[27] || (_cache[27] = ($event) => unref(data).description = $event),
            rows: "4",
            onChange: _cache[28] || (_cache[28] = //@ts-ignore
            (...args) => unref(save) && unref(save)(...args))
          }, null, 544), [
            [vModelText, unref(data).description]
          ])
        ]),
        properties.value !== void 0 ? (openBlock(), createElementBlock("section", _hoisted_62, [
          _cache[87] || (_cache[87] = createElementVNode("h3", null, "Token", -1)),
          createElementVNode("div", _hoisted_63, [
            _cache[85] || (_cache[85] = createElementVNode("label", { for: "scc-size" }, "Size", -1)),
            createElementVNode("div", _hoisted_64, [
              createElementVNode("input", {
                id: "scc-size",
                type: "number",
                min: "0",
                step: "0.5",
                value: properties.value.size.x,
                onChange: _cache[29] || (_cache[29] = ($event) => setSize(Number($event.target.value)))
              }, null, 40, _hoisted_65),
              _cache[81] || (_cache[81] = createElementVNode("span", { class: "muted" }, "cells — 0 infers from the image", -1))
            ]),
            _cache[86] || (_cache[86] = createElementVNode("span", { id: "scc-token-flags-label" }, "Flags", -1)),
            createElementVNode("div", _hoisted_66, [
              createElementVNode("label", null, [
                createElementVNode("input", {
                  type: "checkbox",
                  checked: properties.value.nameVisible,
                  onChange: _cache[30] || (_cache[30] = ($event) => setNameVisible($event.target.checked))
                }, null, 40, _hoisted_67),
                _cache[82] || (_cache[82] = createTextVNode(" name visible "))
              ]),
              createElementVNode("label", null, [
                createElementVNode("input", {
                  type: "checkbox",
                  checked: properties.value.isLocked,
                  onChange: _cache[31] || (_cache[31] = ($event) => setLocked($event.target.checked))
                }, null, 40, _hoisted_68),
                _cache[83] || (_cache[83] = createTextVNode(" locked "))
              ]),
              createElementVNode("label", null, [
                createElementVNode("input", {
                  type: "checkbox",
                  checked: properties.value.isDefeated,
                  onChange: _cache[32] || (_cache[32] = ($event) => setDefeated($event.target.checked))
                }, null, 40, _hoisted_69),
                _cache[84] || (_cache[84] = createTextVNode(" defeated "))
              ])
            ])
          ])
        ])) : createCommentVNode("", true),
        createElementVNode("section", null, [
          _cache[89] || (_cache[89] = createElementVNode("h3", null, "Extra", -1)),
          createElementVNode("div", _hoisted_70, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(unref(data).custom, (stat) => {
              return openBlock(), createElementBlock(Fragment, {
                key: stat.name
              }, [
                createElementVNode("label", {
                  for: "scc-x-" + stat.name
                }, toDisplayString(stat.name), 9, _hoisted_71),
                createElementVNode("div", _hoisted_72, [
                  stat.type === "string" ? withDirectives((openBlock(), createElementBlock("input", {
                    key: 0,
                    id: "scc-x-" + stat.name,
                    "onUpdate:modelValue": ($event) => stat.value = $event,
                    type: "text",
                    onChange: _cache[33] || (_cache[33] = //@ts-ignore
                    (...args) => unref(save) && unref(save)(...args))
                  }, null, 40, _hoisted_73)), [
                    [vModelText, stat.value]
                  ]) : stat.type === "number" ? withDirectives((openBlock(), createElementBlock("input", {
                    key: 1,
                    id: "scc-x-" + stat.name,
                    "onUpdate:modelValue": ($event) => stat.value = $event,
                    type: "number",
                    onChange: _cache[34] || (_cache[34] = //@ts-ignore
                    (...args) => unref(save) && unref(save)(...args))
                  }, null, 40, _hoisted_74)), [
                    [
                      vModelText,
                      stat.value,
                      void 0,
                      { number: true }
                    ]
                  ]) : withDirectives((openBlock(), createElementBlock("input", {
                    key: 2,
                    id: "scc-x-" + stat.name,
                    "onUpdate:modelValue": ($event) => stat.value = $event,
                    type: "checkbox",
                    onChange: _cache[35] || (_cache[35] = //@ts-ignore
                    (...args) => unref(save) && unref(save)(...args))
                  }, null, 40, _hoisted_75)), [
                    [vModelCheckbox, stat.value]
                  ]),
                  createElementVNode("button", {
                    type: "button",
                    title: "Remove " + stat.name,
                    onClick: ($event) => removeOption(stat.name)
                  }, [
                    createVNode(_component_font_awesome_icon, { icon: "trash-alt" })
                  ], 8, _hoisted_76)
                ])
              ], 64);
            }), 128)),
            _cache[88] || (_cache[88] = createElementVNode("label", { for: "scc-new-stat" }, "Add stat", -1)),
            createElementVNode("div", _hoisted_77, [
              withDirectives(createElementVNode("input", {
                id: "scc-new-stat",
                "onUpdate:modelValue": _cache[36] || (_cache[36] = ($event) => selectedName.value = $event),
                type: "text",
                placeholder: "name"
              }, null, 512), [
                [vModelText, selectedName.value]
              ]),
              withDirectives(createElementVNode("select", {
                "onUpdate:modelValue": _cache[37] || (_cache[37] = ($event) => selectedOption.value = $event)
              }, [
                (openBlock(), createElementBlock(Fragment, null, renderList(extraOptions, (option) => {
                  return createElementVNode("option", { key: option }, toDisplayString(option), 1);
                }), 64))
              ], 512), [
                [vModelSelect, selectedOption.value]
              ]),
              createElementVNode("button", {
                type: "button",
                disabled: selectedName.value.trim().length === 0,
                title: "Add this stat",
                onClick: addOption
              }, [
                createVNode(_component_font_awesome_icon, { icon: "plus-square" })
              ], 8, _hoisted_78)
            ])
          ])
        ]),
        createElementVNode("section", null, [
          _cache[93] || (_cache[93] = createElementVNode("h3", null, "Presets", -1)),
          createElementVNode("div", _hoisted_79, [
            _cache[91] || (_cache[91] = createElementVNode("label", { for: "scc-preset" }, "Load", -1)),
            createElementVNode("div", _hoisted_80, [
              withDirectives(createElementVNode("select", {
                id: "scc-preset",
                "onUpdate:modelValue": _cache[38] || (_cache[38] = ($event) => selectedPreset.value = $event)
              }, [
                _cache[90] || (_cache[90] = createElementVNode("option", { value: "" }, "—", -1)),
                (openBlock(true), createElementBlock(Fragment, null, renderList(presetNames.value, (name) => {
                  return openBlock(), createElementBlock("option", {
                    key: name,
                    value: name
                  }, toDisplayString(name), 9, _hoisted_81);
                }), 128))
              ], 512), [
                [vModelSelect, selectedPreset.value]
              ]),
              createElementVNode("button", {
                type: "button",
                disabled: selectedPreset.value.length === 0,
                title: "Replace this sheet with the preset",
                onClick: applyPreset
              }, [
                createVNode(_component_font_awesome_icon, { icon: "download" })
              ], 8, _hoisted_82),
              createElementVNode("button", {
                type: "button",
                disabled: selectedPreset.value.length === 0,
                title: "Delete this preset",
                onClick: removePreset
              }, [
                createVNode(_component_font_awesome_icon, { icon: "trash-alt" })
              ], 8, _hoisted_83)
            ]),
            _cache[92] || (_cache[92] = createElementVNode("label", { for: "scc-preset-name" }, "Save as", -1)),
            createElementVNode("div", _hoisted_84, [
              withDirectives(createElementVNode("input", {
                id: "scc-preset-name",
                "onUpdate:modelValue": _cache[39] || (_cache[39] = ($event) => presetName.value = $event),
                type: "text",
                placeholder: "preset name"
              }, null, 512), [
                [vModelText, presetName.value]
              ]),
              createElementVNode("button", {
                type: "button",
                disabled: presetName.value.trim().length === 0,
                title: "Save this sheet as a campaign-wide preset",
                onClick: storePreset
              }, [
                createVNode(_component_font_awesome_icon, { icon: "floppy-disk" })
              ], 8, _hoisted_85)
            ])
          ]),
          _cache[94] || (_cache[94] = createElementVNode("p", { class: "muted small" }, " Presets are shared by the whole campaign and are not tied to an asset, so a statline can be reused for any token. ", -1))
        ])
      ]);
    };
  }
});
const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};
const CharTab = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-42f1af17"]]);
function cachedSheet(shape) {
  var _a;
  const globalId = api.getGlobalId(shape);
  if (globalId === void 0) return void 0;
  return (_a = api.getDataBlock({
    category: "shape",
    shape: globalId,
    name: SHEET_BLOCK
  })) == null ? void 0 : _a.data;
}
async function applyLevelUp(shape) {
  const globalId = api.getGlobalId(shape);
  if (globalId === void 0) return false;
  const block2 = await api.getOrLoadDataBlock({
    category: "shape",
    shape: globalId,
    name: SHEET_BLOCK
  });
  if (block2 === void 0) return false;
  const sheet = block2.reactiveData.value;
  if (sheet.classId === null || sheet.level >= MAX_LEVEL) return false;
  sheet.level += 1;
  const klass = findClass(sheet.classId);
  if (klass) {
    const gain = Math.max(1, Math.ceil(klass.hitDie / 2) + 1 + abilityMod(sheet.abilities.con));
    sheet.hp.max += gain;
    sheet.hp.current += gain;
  }
  block2.sync();
  return true;
}
function levelUpEntry(shape) {
  var _a;
  if (((_a = api.getShape(shape)) == null ? void 0 : _a.character) === void 0) return [];
  const sheet = cachedSheet(shape);
  const klass = sheet ? findClass(sheet.classId) : void 0;
  if (sheet === void 0) {
    return [
      {
        title: "Level up (open the Character tab first)",
        disabled: true,
        action: () => true
      }
    ];
  }
  if (sheet.classId === null) {
    return [{ title: "Level up — pick a class first", disabled: true, action: () => true }];
  }
  if (sheet.level >= MAX_LEVEL) {
    return [
      {
        title: `Level ${sheet.level} ${(klass == null ? void 0 : klass.name) ?? ""} — max for this campaign`.trim(),
        disabled: true,
        action: () => true
      }
    ];
  }
  const next = klass == null ? void 0 : klass.level2;
  return [
    {
      title: `▲ Level up to ${sheet.level + 1} ${(klass == null ? void 0 : klass.name) ?? ""}${next ? ` — ${next.name}` : ""}`,
      action: async () => applyLevelUp(shape)
    }
  ];
}
async function applyTo(shape, conditionId) {
  var _a;
  const globalId = api.getGlobalId(shape);
  if (globalId === void 0) return false;
  if (((_a = api.getShape(shape)) == null ? void 0 : _a.character) === void 0) return false;
  const block2 = await api.getOrLoadDataBlock({
    category: "shape",
    shape: globalId,
    name: SHEET_BLOCK
  });
  if (block2 === void 0) return false;
  const sheet = block2.reactiveData.value;
  sheet.conditions ?? (sheet.conditions = []);
  if (sheet.conditions.includes(conditionId)) return false;
  sheet.conditions.push(conditionId);
  block2.sync();
  return true;
}
function registerSpellHook() {
  api.eventBus.on("spell:cast", (payload) => {
    const conditionId = payload.condition;
    if (conditionId === void 0 || findCondition(conditionId) === void 0) return;
    void Promise.all(payload.shapes.map((id) => applyTo(id, conditionId)));
  });
}
let api;
async function init(meta) {
  console.log(`Loading ${meta.name} v${meta.version}`);
}
async function initGame(gameApi) {
  api = gameApi;
  api.ui.shape.registerTab(
    { component: CharTab, id: "SCS", label: "Character" },
    (shape) => {
      var _a;
      return ((_a = api.getShape(shape)) == null ? void 0 : _a.character) !== void 0;
    }
  );
  api.ui.shape.registerContextMenuEntry(levelUpEntry);
  registerSpellHook();
}
async function loadLocation() {
}
const events = {
  init,
  initGame,
  loadLocation
};
export {
  api,
  events
};
