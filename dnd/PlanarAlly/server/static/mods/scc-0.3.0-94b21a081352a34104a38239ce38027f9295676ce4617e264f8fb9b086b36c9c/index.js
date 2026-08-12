import { ref, watch, shallowReadonly, defineComponent, computed, onMounted, resolveComponent, createElementBlock, openBlock, createElementVNode, createCommentVNode, withDirectives, vModelText, unref, Fragment, renderList, toDisplayString, vModelSelect, createTextVNode, vModelCheckbox, createVNode } from "vue";
const BLOCK_NAME$1 = "catalogue";
function defaultCatalogue() {
  return {
    version: 1,
    weapons: [
      { id: "longsword", name: "Longsword", kind: "melee", damage: "1d8", damageType: "slashing", properties: ["versatile (1d10)"] },
      { id: "dagger", name: "Dagger", kind: "melee", damage: "1d4", damageType: "piercing", finesse: true, properties: ["light", "thrown (20/60)"] },
      { id: "greataxe", name: "Greataxe", kind: "melee", damage: "1d12", damageType: "slashing", properties: ["heavy", "two-handed"] },
      { id: "rapier", name: "Rapier", kind: "melee", damage: "1d8", damageType: "piercing", finesse: true },
      { id: "quarterstaff", name: "Quarterstaff", kind: "melee", damage: "1d6", damageType: "bludgeoning", properties: ["versatile (1d8)"] },
      { id: "shortbow", name: "Shortbow", kind: "ranged", damage: "1d6", damageType: "piercing", range: "80/320", properties: ["two-handed"] },
      { id: "light-crossbow", name: "Light crossbow", kind: "ranged", damage: "1d8", damageType: "piercing", range: "80/320", properties: ["loading", "two-handed"] },
      { id: "sling", name: "Sling", kind: "ranged", damage: "1d4", damageType: "bludgeoning", range: "30/120" },
      { id: "javelin", name: "Javelin", kind: "ranged", damage: "1d6", damageType: "piercing", range: "30/120", properties: ["thrown"] }
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
      { id: "fighter", name: "Fighter", hitDie: 10, primaryAbility: "str", savingThrows: ["str", "con"], passive: { name: "Second Wind", text: "As a bonus action, regain 1d10 + level hit points. Once per short rest." } },
      { id: "rogue", name: "Rogue", hitDie: 8, primaryAbility: "dex", savingThrows: ["dex", "int"], passive: { name: "Sneak Attack", text: "Once per turn, deal an extra 1d6 damage to a target you have advantage against." } },
      { id: "wizard", name: "Wizard", hitDie: 6, primaryAbility: "int", savingThrows: ["int", "wis"], passive: { name: "Arcane Recovery", text: "Once per day on a short rest, recover spell slots totalling half your level, rounded up." } },
      { id: "cleric", name: "Cleric", hitDie: 8, primaryAbility: "wis", savingThrows: ["wis", "cha"], passive: { name: "Divine Domain", text: "Your chosen domain grants extra spells and a domain feature at 1st level." } },
      { id: "barbarian", name: "Barbarian", hitDie: 12, primaryAbility: "str", savingThrows: ["str", "con"], passive: { name: "Rage", text: "Advantage on Strength checks and saves, bonus melee damage, and resistance to physical damage." } }
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
    current.value = dataBlock.reactiveData.value;
    watch(dataBlock.reactiveData, (value) => {
      current.value = value;
    });
  }
  return dataBlock;
}
function findWeapon(id) {
  return id === null ? void 0 : current.value.weapons.find((w) => w.id === id);
}
function weaponsOfKind(kind) {
  return current.value.weapons.filter((w) => w.kind === kind);
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
    equipped: { melee: null, ranged: null },
    trackerIds: { hp: null, ac: null },
    derived: {
      proficiency: 2,
      mods: { str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 },
      melee: null,
      ranged: null
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
function clampLevel(level) {
  if (!Number.isFinite(level)) return 1;
  return Math.min(20, Math.max(1, Math.floor(level)));
}
function signed(value) {
  return `${value >= 0 ? "+" : "-"}${Math.abs(value)}`;
}
function withModifier(dice, modifier) {
  return modifier === 0 ? dice : `${dice}${signed(modifier)}`;
}
function attackAbility(weapon, abilities) {
  if (weapon.kind === "ranged") return "dex";
  if (weapon.finesse === true) return abilities.dex > abilities.str ? "dex" : "str";
  return "str";
}
function deriveAttack(weapon, abilities, proficiency) {
  if (weapon === void 0) return null;
  const ability = attackAbility(weapon, abilities);
  const mod = abilityMod(abilities[ability]);
  return {
    weapon: weapon.name,
    // Proficiency is assumed. Tracking per-weapon proficiency would mean a
    // checkbox per weapon on every sheet, which is a lot of UI for a rule
    // that almost never bites at a table using the default catalogue.
    attack: withModifier("1d20", mod + proficiency),
    damage: withModifier(weapon.damage, mod),
    ability
  };
}
function deriveSheet(sheet) {
  const proficiency = proficiencyBonus(sheet.level);
  const mods = {};
  for (const { key } of ABILITIES) mods[key] = abilityMod(sheet.abilities[key]);
  return {
    proficiency,
    mods,
    melee: deriveAttack(findWeapon(sheet.equipped.melee), sheet.abilities, proficiency),
    ranged: deriveAttack(findWeapon(sheet.equipped.ranged), sheet.abilities, proficiency)
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
function readBackHp(shape, sheet) {
  const id = sheet.trackerIds.hp;
  if (id === null) return false;
  const tracker = api.systems.trackers.get(shape, id);
  if (tracker === void 0) return false;
  const current2 = tracker.value - sheet.hp.temp;
  if (current2 === sheet.hp.current && tracker.maxvalue === sheet.hp.max) return false;
  sheet.hp.current = current2;
  sheet.hp.max = tracker.maxvalue;
  return true;
}
async function loadBlock(shape) {
  const repr = { category: "shape", shape, name: SHEET_BLOCK };
  const existing = await api.getOrLoadDataBlock(repr);
  if (existing !== void 0) return existing;
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
    if (readBackHp(localId, internal.value)) save();
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
const _hoisted_2 = { class: "grid" };
const _hoisted_3 = ["value"];
const _hoisted_4 = ["value"];
const _hoisted_5 = ["value"];
const _hoisted_6 = { class: "inline" };
const _hoisted_7 = { class: "muted" };
const _hoisted_8 = {
  key: 0,
  class: "passives"
};
const _hoisted_9 = { class: "muted" };
const _hoisted_10 = { class: "abilities" };
const _hoisted_11 = ["for", "title"];
const _hoisted_12 = ["id", "onUpdate:modelValue"];
const _hoisted_13 = { class: "mod" };
const _hoisted_14 = { class: "grid" };
const _hoisted_15 = { class: "inline" };
const _hoisted_16 = { class: "inline" };
const _hoisted_17 = { class: "attacks" };
const _hoisted_18 = ["value"];
const _hoisted_19 = { key: 0 };
const _hoisted_20 = {
  key: 1,
  class: "muted"
};
const _hoisted_21 = { key: 0 };
const _hoisted_22 = {
  key: 1,
  class: "muted"
};
const _hoisted_23 = ["value"];
const _hoisted_24 = { key: 0 };
const _hoisted_25 = {
  key: 1,
  class: "muted"
};
const _hoisted_26 = { key: 0 };
const _hoisted_27 = {
  key: 1,
  class: "muted"
};
const _hoisted_28 = { key: 0 };
const _hoisted_29 = { class: "grid" };
const _hoisted_30 = { class: "inline" };
const _hoisted_31 = ["value"];
const _hoisted_32 = {
  class: "inline",
  role: "group",
  "aria-labelledby": "scc-token-flags-label"
};
const _hoisted_33 = ["checked"];
const _hoisted_34 = ["checked"];
const _hoisted_35 = ["checked"];
const _hoisted_36 = { class: "grid" };
const _hoisted_37 = ["for"];
const _hoisted_38 = { class: "inline" };
const _hoisted_39 = ["id", "onUpdate:modelValue"];
const _hoisted_40 = ["id", "onUpdate:modelValue"];
const _hoisted_41 = ["id", "onUpdate:modelValue"];
const _hoisted_42 = ["title", "onClick"];
const _hoisted_43 = { class: "inline" };
const _hoisted_44 = ["disabled"];
const _hoisted_45 = { class: "grid" };
const _hoisted_46 = { class: "inline" };
const _hoisted_47 = ["value"];
const _hoisted_48 = ["disabled"];
const _hoisted_49 = ["disabled"];
const _hoisted_50 = { class: "inline" };
const _hoisted_51 = ["disabled"];
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
    const meleeWeapons = computed(() => weaponsOfKind("melee"));
    const rangedWeapons = computed(() => weaponsOfKind("ranged"));
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
      const _component_font_awesome_icon = resolveComponent("font-awesome-icon");
      return openBlock(), createElementBlock("div", _hoisted_1, [
        createElementVNode("section", null, [
          _cache[45] || (_cache[45] = createElementVNode("h3", null, "Identity", -1)),
          createElementVNode("div", _hoisted_2, [
            _cache[40] || (_cache[40] = createElementVNode("label", { for: "scc-token-name" }, "Token name", -1)),
            withDirectives(createElementVNode("input", {
              id: "scc-token-name",
              "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => tokenName.value = $event),
              type: "text",
              onChange: commitTokenName
            }, null, 544), [
              [vModelText, tokenName.value]
            ]),
            _cache[41] || (_cache[41] = createElementVNode("label", { for: "scc-race" }, "Race", -1)),
            withDirectives(createElementVNode("select", {
              id: "scc-race",
              "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => unref(data).raceId = $event),
              onChange: _cache[2] || (_cache[2] = //@ts-ignore
              (...args) => unref(save) && unref(save)(...args))
            }, [
              _cache[37] || (_cache[37] = createElementVNode("option", { value: null }, "—", -1)),
              (openBlock(true), createElementBlock(Fragment, null, renderList(unref(catalogue).races, (r) => {
                return openBlock(), createElementBlock("option", {
                  key: r.id,
                  value: r.id
                }, toDisplayString(r.name), 9, _hoisted_3);
              }), 128))
            ], 544), [
              [vModelSelect, unref(data).raceId]
            ]),
            _cache[42] || (_cache[42] = createElementVNode("label", { for: "scc-background" }, "Background", -1)),
            withDirectives(createElementVNode("select", {
              id: "scc-background",
              "onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => unref(data).backgroundId = $event),
              onChange: _cache[4] || (_cache[4] = //@ts-ignore
              (...args) => unref(save) && unref(save)(...args))
            }, [
              _cache[38] || (_cache[38] = createElementVNode("option", { value: null }, "—", -1)),
              (openBlock(true), createElementBlock(Fragment, null, renderList(unref(catalogue).backgrounds, (b) => {
                return openBlock(), createElementBlock("option", {
                  key: b.id,
                  value: b.id
                }, toDisplayString(b.name), 9, _hoisted_4);
              }), 128))
            ], 544), [
              [vModelSelect, unref(data).backgroundId]
            ]),
            _cache[43] || (_cache[43] = createElementVNode("label", { for: "scc-class" }, "Class", -1)),
            withDirectives(createElementVNode("select", {
              id: "scc-class",
              "onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => unref(data).classId = $event),
              onChange: _cache[6] || (_cache[6] = //@ts-ignore
              (...args) => unref(save) && unref(save)(...args))
            }, [
              _cache[39] || (_cache[39] = createElementVNode("option", { value: null }, "—", -1)),
              (openBlock(true), createElementBlock(Fragment, null, renderList(unref(catalogue).classes, (c) => {
                return openBlock(), createElementBlock("option", {
                  key: c.id,
                  value: c.id
                }, toDisplayString(c.name) + " (d" + toDisplayString(c.hitDie) + ") ", 9, _hoisted_5);
              }), 128))
            ], 544), [
              [vModelSelect, unref(data).classId]
            ]),
            _cache[44] || (_cache[44] = createElementVNode("label", { for: "scc-level" }, "Level", -1)),
            createElementVNode("div", _hoisted_6, [
              withDirectives(createElementVNode("input", {
                id: "scc-level",
                "onUpdate:modelValue": _cache[7] || (_cache[7] = ($event) => unref(data).level = $event),
                type: "number",
                min: "1",
                max: "20",
                onChange: _cache[8] || (_cache[8] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 544), [
                [
                  vModelText,
                  unref(data).level,
                  void 0,
                  { number: true }
                ]
              ]),
              createElementVNode("span", _hoisted_7, "proficiency " + toDisplayString(unref(signed)(derived.value.proficiency)), 1)
            ])
          ]),
          passives.value.length > 0 ? (openBlock(), createElementBlock("ul", _hoisted_8, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(passives.value, (p) => {
              return openBlock(), createElementBlock("li", {
                key: p.source + p.name
              }, [
                createElementVNode("strong", null, toDisplayString(p.name), 1),
                createElementVNode("span", _hoisted_9, " · " + toDisplayString(p.source), 1),
                createElementVNode("div", null, toDisplayString(p.text), 1)
              ]);
            }), 128))
          ])) : createCommentVNode("", true)
        ]),
        createElementVNode("section", null, [
          _cache[46] || (_cache[46] = createElementVNode("h3", null, "Abilities", -1)),
          createElementVNode("div", _hoisted_10, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(unref(ABILITIES), (a) => {
              return openBlock(), createElementBlock("div", {
                key: a.key,
                class: "ability"
              }, [
                createElementVNode("label", {
                  for: "scc-" + a.key,
                  title: a.long
                }, toDisplayString(a.label), 9, _hoisted_11),
                withDirectives(createElementVNode("input", {
                  id: "scc-" + a.key,
                  "onUpdate:modelValue": ($event) => unref(data).abilities[a.key] = $event,
                  type: "number",
                  min: "1",
                  max: "30",
                  onChange: _cache[9] || (_cache[9] = //@ts-ignore
                  (...args) => unref(save) && unref(save)(...args))
                }, null, 40, _hoisted_12), [
                  [
                    vModelText,
                    unref(data).abilities[a.key],
                    void 0,
                    { number: true }
                  ]
                ]),
                createElementVNode("span", _hoisted_13, toDisplayString(unref(signed)(unref(abilityMod)(unref(data).abilities[a.key]))), 1)
              ]);
            }), 128))
          ])
        ]),
        createElementVNode("section", null, [
          _cache[58] || (_cache[58] = createElementVNode("h3", null, "Combat", -1)),
          createElementVNode("div", _hoisted_14, [
            _cache[51] || (_cache[51] = createElementVNode("label", { for: "scc-hp" }, "Hit points", -1)),
            createElementVNode("div", _hoisted_15, [
              withDirectives(createElementVNode("input", {
                id: "scc-hp",
                "onUpdate:modelValue": _cache[10] || (_cache[10] = ($event) => unref(data).hp.current = $event),
                type: "number",
                onChange: _cache[11] || (_cache[11] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 544), [
                [
                  vModelText,
                  unref(data).hp.current,
                  void 0,
                  { number: true }
                ]
              ]),
              _cache[47] || (_cache[47] = createElementVNode("span", { class: "muted" }, "/", -1)),
              withDirectives(createElementVNode("input", {
                "onUpdate:modelValue": _cache[12] || (_cache[12] = ($event) => unref(data).hp.max = $event),
                type: "number",
                min: "0",
                onChange: _cache[13] || (_cache[13] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 544), [
                [
                  vModelText,
                  unref(data).hp.max,
                  void 0,
                  { number: true }
                ]
              ]),
              _cache[48] || (_cache[48] = createElementVNode("span", { class: "muted" }, "temp", -1)),
              withDirectives(createElementVNode("input", {
                "onUpdate:modelValue": _cache[14] || (_cache[14] = ($event) => unref(data).hp.temp = $event),
                type: "number",
                min: "0",
                onChange: _cache[15] || (_cache[15] = //@ts-ignore
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
            _cache[52] || (_cache[52] = createElementVNode("label", { for: "scc-ac" }, "Armour class", -1)),
            createElementVNode("div", _hoisted_16, [
              withDirectives(createElementVNode("input", {
                id: "scc-ac",
                "onUpdate:modelValue": _cache[16] || (_cache[16] = ($event) => unref(data).ac = $event),
                type: "number",
                min: "0",
                onChange: _cache[17] || (_cache[17] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 544), [
                [
                  vModelText,
                  unref(data).ac,
                  void 0,
                  { number: true }
                ]
              ]),
              _cache[49] || (_cache[49] = createElementVNode("label", {
                for: "scc-speed",
                class: "muted"
              }, "speed", -1)),
              withDirectives(createElementVNode("input", {
                id: "scc-speed",
                "onUpdate:modelValue": _cache[18] || (_cache[18] = ($event) => unref(data).speed = $event),
                type: "number",
                min: "0",
                onChange: _cache[19] || (_cache[19] = //@ts-ignore
                (...args) => unref(save) && unref(save)(...args))
              }, null, 544), [
                [
                  vModelText,
                  unref(data).speed,
                  void 0,
                  { number: true }
                ]
              ]),
              _cache[50] || (_cache[50] = createElementVNode("span", { class: "muted" }, "ft", -1))
            ])
          ]),
          createElementVNode("table", _hoisted_17, [
            _cache[57] || (_cache[57] = createElementVNode("thead", null, [
              createElementVNode("tr", null, [
                createElementVNode("th", null, "Attack"),
                createElementVNode("th", null, "Weapon"),
                createElementVNode("th", null, "To hit"),
                createElementVNode("th", null, "Damage")
              ])
            ], -1)),
            createElementVNode("tbody", null, [
              createElementVNode("tr", null, [
                _cache[54] || (_cache[54] = createElementVNode("th", { scope: "row" }, "Melee", -1)),
                createElementVNode("td", null, [
                  withDirectives(createElementVNode("select", {
                    "onUpdate:modelValue": _cache[20] || (_cache[20] = ($event) => unref(data).equipped.melee = $event),
                    onChange: _cache[21] || (_cache[21] = //@ts-ignore
                    (...args) => unref(save) && unref(save)(...args))
                  }, [
                    _cache[53] || (_cache[53] = createElementVNode("option", { value: null }, "—", -1)),
                    (openBlock(true), createElementBlock(Fragment, null, renderList(meleeWeapons.value, (w) => {
                      return openBlock(), createElementBlock("option", {
                        key: w.id,
                        value: w.id
                      }, toDisplayString(w.name), 9, _hoisted_18);
                    }), 128))
                  ], 544), [
                    [vModelSelect, unref(data).equipped.melee]
                  ])
                ]),
                createElementVNode("td", null, [
                  derived.value.melee ? (openBlock(), createElementBlock("code", _hoisted_19, toDisplayString(derived.value.melee.attack), 1)) : (openBlock(), createElementBlock("span", _hoisted_20, "—"))
                ]),
                createElementVNode("td", null, [
                  derived.value.melee ? (openBlock(), createElementBlock("code", _hoisted_21, toDisplayString(derived.value.melee.damage), 1)) : (openBlock(), createElementBlock("span", _hoisted_22, "—"))
                ])
              ]),
              createElementVNode("tr", null, [
                _cache[56] || (_cache[56] = createElementVNode("th", { scope: "row" }, "Ranged", -1)),
                createElementVNode("td", null, [
                  withDirectives(createElementVNode("select", {
                    "onUpdate:modelValue": _cache[22] || (_cache[22] = ($event) => unref(data).equipped.ranged = $event),
                    onChange: _cache[23] || (_cache[23] = //@ts-ignore
                    (...args) => unref(save) && unref(save)(...args))
                  }, [
                    _cache[55] || (_cache[55] = createElementVNode("option", { value: null }, "—", -1)),
                    (openBlock(true), createElementBlock(Fragment, null, renderList(rangedWeapons.value, (w) => {
                      return openBlock(), createElementBlock("option", {
                        key: w.id,
                        value: w.id
                      }, toDisplayString(w.name), 9, _hoisted_23);
                    }), 128))
                  ], 544), [
                    [vModelSelect, unref(data).equipped.ranged]
                  ])
                ]),
                createElementVNode("td", null, [
                  derived.value.ranged ? (openBlock(), createElementBlock("code", _hoisted_24, toDisplayString(derived.value.ranged.attack), 1)) : (openBlock(), createElementBlock("span", _hoisted_25, "—"))
                ]),
                createElementVNode("td", null, [
                  derived.value.ranged ? (openBlock(), createElementBlock("code", _hoisted_26, toDisplayString(derived.value.ranged.damage), 1)) : (openBlock(), createElementBlock("span", _hoisted_27, "—"))
                ])
              ])
            ])
          ]),
          _cache[59] || (_cache[59] = createElementVNode("p", { class: "muted small" }, " Attack rows are computed from ability scores, level and the equipped weapon. The ghost player rolls these exact numbers. ", -1))
        ]),
        createElementVNode("section", null, [
          _cache[60] || (_cache[60] = createElementVNode("h3", null, "Description", -1)),
          withDirectives(createElementVNode("textarea", {
            "onUpdate:modelValue": _cache[24] || (_cache[24] = ($event) => unref(data).description = $event),
            rows: "4",
            onChange: _cache[25] || (_cache[25] = //@ts-ignore
            (...args) => unref(save) && unref(save)(...args))
          }, null, 544), [
            [vModelText, unref(data).description]
          ])
        ]),
        properties.value !== void 0 ? (openBlock(), createElementBlock("section", _hoisted_28, [
          _cache[67] || (_cache[67] = createElementVNode("h3", null, "Token", -1)),
          createElementVNode("div", _hoisted_29, [
            _cache[65] || (_cache[65] = createElementVNode("label", { for: "scc-size" }, "Size", -1)),
            createElementVNode("div", _hoisted_30, [
              createElementVNode("input", {
                id: "scc-size",
                type: "number",
                min: "0",
                step: "0.5",
                value: properties.value.size.x,
                onChange: _cache[26] || (_cache[26] = ($event) => setSize(Number($event.target.value)))
              }, null, 40, _hoisted_31),
              _cache[61] || (_cache[61] = createElementVNode("span", { class: "muted" }, "cells — 0 infers from the image", -1))
            ]),
            _cache[66] || (_cache[66] = createElementVNode("span", { id: "scc-token-flags-label" }, "Flags", -1)),
            createElementVNode("div", _hoisted_32, [
              createElementVNode("label", null, [
                createElementVNode("input", {
                  type: "checkbox",
                  checked: properties.value.nameVisible,
                  onChange: _cache[27] || (_cache[27] = ($event) => setNameVisible($event.target.checked))
                }, null, 40, _hoisted_33),
                _cache[62] || (_cache[62] = createTextVNode(" name visible "))
              ]),
              createElementVNode("label", null, [
                createElementVNode("input", {
                  type: "checkbox",
                  checked: properties.value.isLocked,
                  onChange: _cache[28] || (_cache[28] = ($event) => setLocked($event.target.checked))
                }, null, 40, _hoisted_34),
                _cache[63] || (_cache[63] = createTextVNode(" locked "))
              ]),
              createElementVNode("label", null, [
                createElementVNode("input", {
                  type: "checkbox",
                  checked: properties.value.isDefeated,
                  onChange: _cache[29] || (_cache[29] = ($event) => setDefeated($event.target.checked))
                }, null, 40, _hoisted_35),
                _cache[64] || (_cache[64] = createTextVNode(" defeated "))
              ])
            ])
          ])
        ])) : createCommentVNode("", true),
        createElementVNode("section", null, [
          _cache[69] || (_cache[69] = createElementVNode("h3", null, "Extra", -1)),
          createElementVNode("div", _hoisted_36, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(unref(data).custom, (stat) => {
              return openBlock(), createElementBlock(Fragment, {
                key: stat.name
              }, [
                createElementVNode("label", {
                  for: "scc-x-" + stat.name
                }, toDisplayString(stat.name), 9, _hoisted_37),
                createElementVNode("div", _hoisted_38, [
                  stat.type === "string" ? withDirectives((openBlock(), createElementBlock("input", {
                    key: 0,
                    id: "scc-x-" + stat.name,
                    "onUpdate:modelValue": ($event) => stat.value = $event,
                    type: "text",
                    onChange: _cache[30] || (_cache[30] = //@ts-ignore
                    (...args) => unref(save) && unref(save)(...args))
                  }, null, 40, _hoisted_39)), [
                    [vModelText, stat.value]
                  ]) : stat.type === "number" ? withDirectives((openBlock(), createElementBlock("input", {
                    key: 1,
                    id: "scc-x-" + stat.name,
                    "onUpdate:modelValue": ($event) => stat.value = $event,
                    type: "number",
                    onChange: _cache[31] || (_cache[31] = //@ts-ignore
                    (...args) => unref(save) && unref(save)(...args))
                  }, null, 40, _hoisted_40)), [
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
                    onChange: _cache[32] || (_cache[32] = //@ts-ignore
                    (...args) => unref(save) && unref(save)(...args))
                  }, null, 40, _hoisted_41)), [
                    [vModelCheckbox, stat.value]
                  ]),
                  createElementVNode("button", {
                    type: "button",
                    title: "Remove " + stat.name,
                    onClick: ($event) => removeOption(stat.name)
                  }, [
                    createVNode(_component_font_awesome_icon, { icon: "trash-alt" })
                  ], 8, _hoisted_42)
                ])
              ], 64);
            }), 128)),
            _cache[68] || (_cache[68] = createElementVNode("label", { for: "scc-new-stat" }, "Add stat", -1)),
            createElementVNode("div", _hoisted_43, [
              withDirectives(createElementVNode("input", {
                id: "scc-new-stat",
                "onUpdate:modelValue": _cache[33] || (_cache[33] = ($event) => selectedName.value = $event),
                type: "text",
                placeholder: "name"
              }, null, 512), [
                [vModelText, selectedName.value]
              ]),
              withDirectives(createElementVNode("select", {
                "onUpdate:modelValue": _cache[34] || (_cache[34] = ($event) => selectedOption.value = $event)
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
              ], 8, _hoisted_44)
            ])
          ])
        ]),
        createElementVNode("section", null, [
          _cache[73] || (_cache[73] = createElementVNode("h3", null, "Presets", -1)),
          createElementVNode("div", _hoisted_45, [
            _cache[71] || (_cache[71] = createElementVNode("label", { for: "scc-preset" }, "Load", -1)),
            createElementVNode("div", _hoisted_46, [
              withDirectives(createElementVNode("select", {
                id: "scc-preset",
                "onUpdate:modelValue": _cache[35] || (_cache[35] = ($event) => selectedPreset.value = $event)
              }, [
                _cache[70] || (_cache[70] = createElementVNode("option", { value: "" }, "—", -1)),
                (openBlock(true), createElementBlock(Fragment, null, renderList(presetNames.value, (name) => {
                  return openBlock(), createElementBlock("option", {
                    key: name,
                    value: name
                  }, toDisplayString(name), 9, _hoisted_47);
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
              ], 8, _hoisted_48),
              createElementVNode("button", {
                type: "button",
                disabled: selectedPreset.value.length === 0,
                title: "Delete this preset",
                onClick: removePreset
              }, [
                createVNode(_component_font_awesome_icon, { icon: "trash-alt" })
              ], 8, _hoisted_49)
            ]),
            _cache[72] || (_cache[72] = createElementVNode("label", { for: "scc-preset-name" }, "Save as", -1)),
            createElementVNode("div", _hoisted_50, [
              withDirectives(createElementVNode("input", {
                id: "scc-preset-name",
                "onUpdate:modelValue": _cache[36] || (_cache[36] = ($event) => presetName.value = $event),
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
              ], 8, _hoisted_51)
            ])
          ]),
          _cache[74] || (_cache[74] = createElementVNode("p", { class: "muted small" }, " Presets are shared by the whole campaign and are not tied to an asset, so a statline can be reused for any token. ", -1))
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
const CharTab = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-b1cb78ab"]]);
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
