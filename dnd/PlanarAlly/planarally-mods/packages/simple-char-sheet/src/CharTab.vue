<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import {
    catalogue,
    ensureCatalogue,
    findBackground,
    findCantrip,
    findClass,
    findCondition,
    findWeapon,
    findRace,
    weaponGroups,
    type Passive,
} from "./catalogue";
import { ABILITIES, type CharacterSheet, type StatType } from "./data";
import { api } from "./main";
import { deletePreset, ensurePresets, getPreset, presetLibrary, savePreset, toPreset } from "./presets";
import {
    MAX_LEVEL,
    abilityMod,
    availableCantrips,
    canCast,
    castingAbility,
    signed,
    suggestedMaxHp,
    weaponActions,
} from "./rules";
import { useSheet } from "./sheet";

const SYNC = { ui: true, server: true };

const { data, load, save, write } = useSheet();

// The active character drives everything. This is the only place the component
// learns which shape it is looking at.
const localId = computed(() => {
    const charId = api.systemsState.characters.reactive.activeCharacterId;
    if (charId === undefined) return undefined;
    return api.systems.characters.getShape(charId)?.id;
});

watch(
    () => api.systemsState.characters.reactive.activeCharacterId,
    async (charId) => {
        if (charId === undefined) return;
        const shapeId = api.systems.characters.getShapeId(charId);
        const local = api.systems.characters.getShape(charId)?.id;
        if (shapeId !== undefined && local !== undefined) await load(shapeId, local);
    },
    // Without `immediate` the component would mount against an already-selected
    // character and never load it, because a watcher is lazy by default.
    { immediate: true },
);

onMounted(() => {
    void ensureCatalogue();
    void ensurePresets();
});

// ---- identity --------------------------------------------------------------

const race = computed(() => findRace(data.value.raceId));
const background = computed(() => findBackground(data.value.backgroundId));
const klass = computed(() => findClass(data.value.classId));

const passives = computed(() =>
    [race.value, background.value, klass.value]
        .filter((t): t is NonNullable<typeof t> => t !== undefined)
        .map((t) => ({ source: t.name, ...t.passive } as Passive & { source: string })),
);

// ---- combat ----------------------------------------------------------------

// Split so natural weapons (claws, bite) sit in their own group rather than
// among the swords -- a bear isn't picking gear off a rack.
const meleeWeapons = computed(() => weaponGroups("melee"));
// Actions come from the weapon's damage type and properties, not from a
// per-weapon list -- so every sword gets Lacerate without an entry for it.
const actions = computed(() => [
    ...weaponActions(findWeapon(data.value.equipped.melee)),
    ...weaponActions(findWeapon(data.value.equipped.ranged)),
]);
const rangedWeapons = computed(() => weaponGroups("ranged"));

// ---- spellcasting ----------------------------------------------------------

const spellAbility = computed(() => castingAbility(data.value));
const cantrip = computed(() => findCantrip(data.value.equipped.cantrip));
const isCaster = computed(() => canCast(data.value));
const cantripChoices = computed(() => availableCantrips(data.value));

// ---- conditions ------------------------------------------------------------

const activeConditions = computed(() =>
    data.value.conditions.map(findCondition).filter((c): c is NonNullable<typeof c> => c !== undefined),
);

function toggleCondition(id: string): void {
    const list = data.value.conditions;
    const at = list.indexOf(id);
    if (at === -1) list.push(id);
    else list.splice(at, 1);

    // Unconscious is the one condition PlanarAlly itself models, via the
    // defeated marker. Keeping the two in step means the token shows it
    // without anyone having to remember to set it twice.
    const condition = findCondition(id);
    if (condition?.impliesDefeated === true && localId.value !== undefined) {
        api.systems.properties.setIsDefeated(localId.value, at === -1, SYNC);
    }
    save();
}

// ---- levelling -------------------------------------------------------------

const canLevelUp = computed(() => data.value.classId !== null && data.value.level < MAX_LEVEL);
const nextFeature = computed(() => (canLevelUp.value ? klass.value?.level2 : undefined));

function levelUp(): void {
    if (!canLevelUp.value) return;
    data.value.level = data.value.level + 1;
    // Hit points are the one thing levelling always changes, so raise the
    // maximum with it -- and heal by the same amount rather than silently
    // leaving the character wounded by their own advancement.
    const klassDef = klass.value;
    if (klassDef) {
        const gain = Math.max(1, Math.ceil(klassDef.hitDie / 2) + 1 + abilityMod(data.value.abilities.con));
        data.value.hp.max += gain;
        data.value.hp.current += gain;
    }
    save();
}

// Read straight off the stored block rather than recomputing in the template:
// `derived` is what the ghost player rolls, so showing anything else here would
// let the panel and the voice commands disagree.
const derived = computed(() => data.value.derived);

const hpSuggestion = computed(() => {
    const suggested = suggestedMaxHp(data.value);
    return suggested === undefined || suggested === data.value.hp.max ? undefined : suggested;
});

function applyHpSuggestion(): void {
    const suggested = hpSuggestion.value;
    if (suggested === undefined) return;
    data.value.hp.max = suggested;
    if (data.value.hp.current === 0 || data.value.hp.current > suggested) {
        data.value.hp.current = suggested;
    }
    save();
}

// ---- token -----------------------------------------------------------------
//
// These are PA shape properties, not sheet data -- they're here so that one
// panel is the whole character rather than a scavenger hunt across tabs.

const properties = computed(() => {
    const id = localId.value;
    return id === undefined ? undefined : api.systemsState.properties.reactive.data.get(id);
});

const tokenName = ref("");
watch(properties, (props) => (tokenName.value = props?.name ?? ""), { immediate: true });

function commitTokenName(): void {
    const id = localId.value;
    if (id === undefined || tokenName.value.length === 0) return;
    api.systems.properties.setName(id, tokenName.value, SYNC);
}

function setNameVisible(visible: boolean): void {
    if (localId.value !== undefined) api.systems.properties.setNameVisible(localId.value, visible, SYNC);
}

function setLocked(locked: boolean): void {
    if (localId.value !== undefined) api.systems.properties.setLocked(localId.value, locked, SYNC);
}

function setDefeated(defeated: boolean): void {
    if (localId.value !== undefined) api.systems.properties.setIsDefeated(localId.value, defeated, SYNC);
}

function setSize(value: number): void {
    // 0 means "infer from the image", which is PA's default and worth keeping
    // reachable rather than forcing an explicit number.
    if (localId.value !== undefined) api.systems.properties.setSize(localId.value, { x: value, y: value }, SYNC);
}

// ---- extra stats -----------------------------------------------------------

const extraOptions = ["Text", "Number", "Checkbox"] as const;
const selectedOption = ref<(typeof extraOptions)[number]>(extraOptions[0]);
const selectedName = ref("");

function addOption(): void {
    const name = selectedName.value.trim();
    if (name.length === 0 || data.value.custom.some((s) => s.name === name)) return;

    let stat: StatType;
    if (selectedOption.value === "Checkbox") stat = { name, type: "check", value: false };
    else if (selectedOption.value === "Number") stat = { name, type: "number", value: 0 };
    else stat = { name, type: "string", value: "" };

    data.value.custom.push(stat);
    selectedName.value = "";
    save();
}

function removeOption(name: string): void {
    data.value.custom = data.value.custom.filter((s) => s.name !== name);
    save();
}

// A sheet nobody has filled in yet. Offering the preset library at the top
// in that state is the difference between "make a goblin" being one click
// and being a page of typing -- and it disappears the moment the sheet has
// anything in it, so it never nags an existing character.
const isBlank = computed(
    () =>
        data.value.classId === null &&
        data.value.raceId === null &&
        data.value.level === 1 &&
        data.value.hp.max === 0 &&
        data.value.custom.length === 0 &&
        Object.values(data.value.abilities).every((v) => v === 10),
);

// ---- presets ---------------------------------------------------------------

const selectedPreset = ref("");
const presetName = ref("");
const presetNames = computed(() => Object.keys(presetLibrary.value).sort());

function applyPreset(): void {
    const preset = getPreset(selectedPreset.value);
    if (preset === undefined) return;
    // Keep this token's trackers; take everything else from the preset.
    write({ ...preset, trackerIds: data.value.trackerIds, derived: data.value.derived } as CharacterSheet);
    save();
}

async function storePreset(): Promise<void> {
    const name = presetName.value.trim();
    if (name.length === 0) return;
    if (await savePreset(name, toPreset(data.value))) {
        selectedPreset.value = name;
        presetName.value = "";
    }
}

async function removePreset(): Promise<void> {
    if (await deletePreset(selectedPreset.value)) selectedPreset.value = "";
}
</script>

<template>
    <div id="scc">
        <section v-if="isBlank && presetNames.length > 0" class="starter">
            <h3>Start from a preset</h3>
            <div class="inline">
                <select v-model="selectedPreset">
                    <option value="">—</option>
                    <option v-for="name of presetNames" :key="name" :value="name">{{ name }}</option>
                </select>
                <button type="button" :disabled="selectedPreset.length === 0" @click="applyPreset">
                    Use this preset
                </button>
                <span class="muted small">or just fill the sheet in below</span>
            </div>
        </section>

        <section>
            <h3>Identity</h3>
            <div class="grid">
                <label for="scc-token-name">Token name</label>
                <input id="scc-token-name" v-model="tokenName" type="text" @change="commitTokenName" />

                <label for="scc-race">Race</label>
                <select id="scc-race" v-model="data.raceId" @change="save">
                    <option :value="null">—</option>
                    <option v-for="r of catalogue.races" :key="r.id" :value="r.id">{{ r.name }}</option>
                </select>

                <label for="scc-background">Background</label>
                <select id="scc-background" v-model="data.backgroundId" @change="save">
                    <option :value="null">—</option>
                    <option v-for="b of catalogue.backgrounds" :key="b.id" :value="b.id">{{ b.name }}</option>
                </select>

                <label for="scc-class">Class</label>
                <select id="scc-class" v-model="data.classId" @change="save">
                    <option :value="null">—</option>
                    <option v-for="c of catalogue.classes" :key="c.id" :value="c.id">
                        {{ c.name }} (d{{ c.hitDie }})
                    </option>
                </select>

                <label for="scc-level">Level</label>
                <div class="inline">
                    <input
                        id="scc-level"
                        v-model.number="data.level"
                        type="number"
                        min="1"
                        :max="MAX_LEVEL"
                        @change="save"
                    />
                    <span class="muted">proficiency {{ signed(derived.proficiency) }}</span>
                    <button v-if="canLevelUp" type="button" class="levelup" @click="levelUp">
                        <font-awesome-icon icon="arrow-up" /> Level up
                    </button>
                    <span v-else-if="data.level >= MAX_LEVEL" class="muted">max for this campaign</span>
                </div>
                <template v-if="nextFeature">
                    <span></span>
                    <p class="muted small next-up">
                        Next level: <strong>{{ nextFeature.name }}</strong> — {{ nextFeature.text }}
                    </p>
                </template>
            </div>

            <ul v-if="passives.length > 0" class="passives">
                <li v-for="p of passives" :key="p.source + p.name">
                    <strong>{{ p.name }}</strong>
                    <span class="muted"> · {{ p.source }}</span>
                    <div>{{ p.text }}</div>
                </li>
            </ul>
        </section>

        <section>
            <h3>Abilities</h3>
            <div class="abilities">
                <div v-for="a of ABILITIES" :key="a.key" class="ability">
                    <label :for="'scc-' + a.key" :title="a.long">{{ a.label }}</label>
                    <input
                        :id="'scc-' + a.key"
                        v-model.number="data.abilities[a.key]"
                        type="number"
                        min="1"
                        max="30"
                        @change="save"
                    />
                    <span class="mod">{{ signed(abilityMod(data.abilities[a.key])) }}</span>
                </div>
            </div>
        </section>

        <section>
            <h3>Conditions</h3>
            <div class="conditions">
                <button
                    v-for="c of catalogue.conditions"
                    :key="c.id"
                    type="button"
                    class="chip"
                    :class="{ on: data.conditions.includes(c.id) }"
                    :aria-pressed="data.conditions.includes(c.id)"
                    :title="c.text"
                    @click="toggleCondition(c.id)"
                >
                    {{ c.name }}
                </button>
            </div>
            <ul v-if="activeConditions.length > 0" class="passives">
                <li v-for="c of activeConditions" :key="c.id">
                    <strong>{{ c.name }}</strong>
                    <div>{{ c.text }}</div>
                </li>
            </ul>
            <p v-else class="muted small">None. Click one to apply it.</p>
        </section>

        <section>
            <h3>Saving throws</h3>
            <div class="abilities">
                <div v-for="a of ABILITIES" :key="a.key" class="ability" :class="{ trained: derived.saves[a.key].proficient }">
                    <span class="lbl" :title="a.long">{{ a.label }}</span>
                    <span class="mod">{{ signed(derived.saves[a.key].bonus) }}</span>
                    <span class="prof">{{ derived.saves[a.key].proficient ? "proficient" : "&nbsp;" }}</span>
                </div>
            </div>
        </section>

        <section>
            <h3>Combat</h3>
            <div class="grid">
                <label for="scc-hp">Hit points</label>
                <div class="inline">
                    <input id="scc-hp" v-model.number="data.hp.current" type="number" @change="save" />
                    <span class="muted">/</span>
                    <input v-model.number="data.hp.max" type="number" min="0" @change="save" />
                    <span class="muted">temp</span>
                    <input v-model.number="data.hp.temp" type="number" min="0" @change="save" />
                    <button v-if="hpSuggestion !== undefined" type="button" @click="applyHpSuggestion">
                        use {{ hpSuggestion }}
                    </button>
                </div>

                <label for="scc-ac">Armour class</label>
                <div class="inline">
                    <input id="scc-ac" v-model.number="data.ac" type="number" min="0" @change="save" />
                    <label for="scc-speed" class="muted">speed</label>
                    <input id="scc-speed" v-model.number="data.speed" type="number" min="0" @change="save" />
                    <span class="muted">ft</span>
                </div>
            </div>

            <table class="attacks">
                <thead>
                    <tr>
                        <th>Attack</th>
                        <th>Weapon</th>
                        <th>To hit</th>
                        <th>Damage</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <th scope="row">Melee</th>
                        <td>
                            <select v-model="data.equipped.melee" @change="save">
                                <option :value="null">—</option>
                                <optgroup label="Weapons">
                                    <option v-for="w of meleeWeapons.carried" :key="w.id" :value="w.id">
                                        {{ w.name }}
                                    </option>
                                </optgroup>
                                <optgroup label="Natural">
                                    <option v-for="w of meleeWeapons.natural" :key="w.id" :value="w.id">
                                        {{ w.name }}
                                    </option>
                                </optgroup>
                            </select>
                        </td>
                        <td>
                            <code v-if="derived.melee">{{ derived.melee.attack }}</code>
                            <span v-else class="muted">—</span>
                        </td>
                        <td>
                            <code v-if="derived.melee">{{ derived.melee.damage }}</code>
                            <span v-else class="muted">—</span>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">Ranged</th>
                        <td>
                            <select v-model="data.equipped.ranged" @change="save">
                                <option :value="null">—</option>
                                <optgroup label="Weapons">
                                    <option v-for="w of rangedWeapons.carried" :key="w.id" :value="w.id">
                                        {{ w.name }}
                                    </option>
                                </optgroup>
                                <optgroup v-if="rangedWeapons.natural.length > 0" label="Natural">
                                    <option v-for="w of rangedWeapons.natural" :key="w.id" :value="w.id">
                                        {{ w.name }}
                                    </option>
                                </optgroup>
                            </select>
                        </td>
                        <td>
                            <code v-if="derived.ranged">{{ derived.ranged.attack }}</code>
                            <span v-else class="muted">—</span>
                        </td>
                        <td>
                            <code v-if="derived.ranged">{{ derived.ranged.damage }}</code>
                            <span v-else class="muted">—</span>
                        </td>
                    </tr>
                </tbody>
            </table>
            <template v-if="actions.length > 0">
                <h3 style="margin-top: 0.9rem">Weapon actions</h3>
                <ul class="passives">
                    <li v-for="a of actions" :key="a.id">
                        <strong>{{ a.name }}</strong>
                        <span class="muted"> · {{ a.source === "5e" ? "5e" : "house rule" }}</span>
                        <span v-if="a.save" class="muted"> · {{ a.save.toUpperCase() }} save</span>
                        <div>{{ a.text }}</div>
                    </li>
                </ul>
            </template>
            <p class="muted small">
                Attack rows are computed from ability scores, level and the equipped weapon. The ghost player rolls
                these exact numbers, and can roll any of them with advantage or disadvantage.
            </p>
        </section>

        <!-- Only casters get this section at all. A fighter has no business
             being offered a cantrip picker, and the ability override that used
             to live here quietly let them take one. -->
        <section v-if="isCaster">
            <h3>Spellcasting</h3>
            <div class="grid">
                <label for="scc-cantrip">Cantrip</label>
                <div class="inline">
                    <select id="scc-cantrip" v-model="data.equipped.cantrip" @change="save">
                        <option :value="null">—</option>
                        <option v-for="c of cantripChoices" :key="c.id" :value="c.id">{{ c.name }}</option>
                    </select>
                    <span class="muted">
                        {{ klass?.name }} list · casts with {{ spellAbility?.toUpperCase() }} · save DC
                        {{ derived.spellSaveDc }}
                    </span>
                </div>
            </div>

            <table v-if="derived.cantrip" class="attacks">
                <thead>
                    <tr>
                        <th>Cantrip</th>
                        <th>Range</th>
                        <th>{{ derived.cantrip.kind === "attack" ? "To hit" : "Save" }}</th>
                        <th>Damage</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <th scope="row">{{ derived.cantrip.name }}</th>
                        <td>{{ derived.cantrip.range }}{{ derived.cantrip.range === "touch" ? "" : " ft" }}</td>
                        <td>
                            <code v-if="derived.cantrip.attack">{{ derived.cantrip.attack }}</code>
                            <span v-else>DC {{ derived.cantrip.saveDc }} {{ derived.cantrip.save?.toUpperCase() }}</span>
                        </td>
                        <td>
                            <code>{{ derived.cantrip.damage }}</code>
                            <span class="muted"> {{ derived.cantrip.damageType }}</span>
                        </td>
                    </tr>
                </tbody>
            </table>

            <p v-if="derived.cantrip?.closeRangeDisadvantage" class="warn small">
                Ranged spell attack: <strong>disadvantage</strong> while a hostile creature is within 5 ft —
                <code>{{ derived.cantrip.attackDisadvantage }}</code>
            </p>
            <p v-if="cantrip" class="muted small">{{ cantrip.text }}</p>
            <p v-if="derived.cantrip" class="muted small">
                Cantrip damage scales with character level and takes no ability modifier.
            </p>
        </section>

        <section>
            <h3>Description</h3>
            <textarea v-model="data.description" rows="4" @change="save"></textarea>
        </section>

        <section v-if="properties !== undefined">
            <h3>Token</h3>
            <div class="grid">
                <label for="scc-size">Size</label>
                <div class="inline">
                    <input
                        id="scc-size"
                        type="number"
                        min="0"
                        step="0.5"
                        :value="properties.size.x"
                        @change="setSize(Number(($event.target as HTMLInputElement).value))"
                    />
                    <span class="muted">cells — 0 infers from the image</span>
                </div>

                <span id="scc-token-flags-label">Flags</span>
                <div class="inline" role="group" aria-labelledby="scc-token-flags-label">
                    <label>
                        <input
                            type="checkbox"
                            :checked="properties.nameVisible"
                            @change="setNameVisible(($event.target as HTMLInputElement).checked)"
                        />
                        name visible
                    </label>
                    <label>
                        <input
                            type="checkbox"
                            :checked="properties.isLocked"
                            @change="setLocked(($event.target as HTMLInputElement).checked)"
                        />
                        locked
                    </label>
                    <label>
                        <input
                            type="checkbox"
                            :checked="properties.isDefeated"
                            @change="setDefeated(($event.target as HTMLInputElement).checked)"
                        />
                        defeated
                    </label>
                </div>
            </div>
        </section>

        <section>
            <h3>Extra</h3>
            <div class="grid">
                <template v-for="stat of data.custom" :key="stat.name">
                    <label :for="'scc-x-' + stat.name">{{ stat.name }}</label>
                    <div class="inline">
                        <input
                            v-if="stat.type === 'string'"
                            :id="'scc-x-' + stat.name"
                            v-model="stat.value"
                            type="text"
                            @change="save"
                        />
                        <input
                            v-else-if="stat.type === 'number'"
                            :id="'scc-x-' + stat.name"
                            v-model.number="stat.value"
                            type="number"
                            @change="save"
                        />
                        <input
                            v-else
                            :id="'scc-x-' + stat.name"
                            v-model="stat.value"
                            type="checkbox"
                            @change="save"
                        />
                        <button type="button" :title="'Remove ' + stat.name" @click="removeOption(stat.name)">
                            <font-awesome-icon icon="trash-alt" />
                        </button>
                    </div>
                </template>

                <label for="scc-new-stat">Add stat</label>
                <div class="inline">
                    <input id="scc-new-stat" v-model="selectedName" type="text" placeholder="name" />
                    <select v-model="selectedOption">
                        <option v-for="option of extraOptions" :key="option">{{ option }}</option>
                    </select>
                    <button
                        type="button"
                        :disabled="selectedName.trim().length === 0"
                        title="Add this stat"
                        @click="addOption"
                    >
                        <font-awesome-icon icon="plus-square" />
                    </button>
                </div>
            </div>
        </section>

        <section>
            <h3>Presets</h3>
            <div class="grid">
                <label for="scc-preset">Load</label>
                <div class="inline">
                    <select id="scc-preset" v-model="selectedPreset">
                        <option value="">—</option>
                        <option v-for="name of presetNames" :key="name" :value="name">{{ name }}</option>
                    </select>
                    <button
                        type="button"
                        :disabled="selectedPreset.length === 0"
                        title="Replace this sheet with the preset"
                        @click="applyPreset"
                    >
                        <font-awesome-icon icon="download" />
                    </button>
                    <button
                        type="button"
                        :disabled="selectedPreset.length === 0"
                        title="Delete this preset"
                        @click="removePreset"
                    >
                        <font-awesome-icon icon="trash-alt" />
                    </button>
                </div>

                <label for="scc-preset-name">Save as</label>
                <div class="inline">
                    <input id="scc-preset-name" v-model="presetName" type="text" placeholder="preset name" />
                    <button
                        type="button"
                        :disabled="presetName.trim().length === 0"
                        title="Save this sheet as a campaign-wide preset"
                        @click="storePreset"
                    >
                        <font-awesome-icon icon="floppy-disk" />
                    </button>
                </div>
            </div>
            <p class="muted small">
                Presets are shared by the whole campaign and are not tied to an asset, so a statline can be reused for
                any token.
            </p>
        </section>
    </div>
</template>

<style scoped lang="scss">
#scc {
    padding: 1rem;
    background-color: white;

    /*
     * Scroll inside the tab rather than growing the dialog off the screen.
     * `height: -webkit-fill-available` used to be here; it is non-standard,
     * behaves differently across engines, and gave the panel no upper bound at
     * all when its container had none either.
     */
    max-height: 100%;
    overflow-y: auto;

    display: flex;
    flex-direction: column;
    gap: 1.25rem;

    h3 {
        margin: 0 0 0.5rem;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #555;
        border-bottom: solid 1px #ddd;
        padding-bottom: 0.25rem;
    }

    .grid {
        display: grid;
        grid-template-columns: 8rem 1fr;
        column-gap: 1rem;
        row-gap: 0.4rem;
        align-items: center;
    }

    .inline {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.4rem;

        input[type="number"] {
            width: 4.5rem;
        }

        label {
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }
    }

    input[type="text"],
    input[type="number"],
    select,
    textarea {
        padding: 0.25rem 0.4rem;
        border: solid 1px #bbb;
        border-radius: 4px;
        font: inherit;
    }

    textarea {
        width: 100%;
        box-sizing: border-box;
        resize: vertical;
    }

    button {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        padding: 0.25rem 0.5rem;
        border: solid 1px #bbb;
        border-radius: 4px;
        background-color: #f5f5f5;
        font: inherit;
        cursor: pointer;

        &:hover:not(:disabled) {
            background-color: #82c8a0;
        }

        &:disabled {
            opacity: 0.4;
            cursor: default;
        }
    }

    // Keyboard users need to see where they are; the surrounding app removes
    // outlines in a lot of places, so this panel puts one back explicitly.
    :focus-visible {
        outline: solid 2px #2b6cb0;
        outline-offset: 1px;
    }

    .abilities {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 0.5rem;

        .ability {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.15rem;
            padding: 0.4rem 0.2rem;
            border: solid 1px #ddd;
            border-radius: 6px;

            label {
                font-size: 0.7rem;
                font-weight: 700;
                letter-spacing: 0.05em;
                color: #555;
            }

            input {
                width: 100%;
                text-align: center;
            }

            .mod {
                font-variant-numeric: tabular-nums;
                font-weight: 700;
            }
        }
    }

    .attacks {
        width: 100%;
        border-collapse: collapse;
        margin-top: 0.5rem;

        th,
        td {
            text-align: left;
            padding: 0.3rem 0.5rem;
            border-bottom: solid 1px #eee;
        }

        thead th {
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #777;
        }

        code {
            font-variant-numeric: tabular-nums;
        }
    }

    .passives {
        list-style: none;
        margin: 0.75rem 0 0;
        padding: 0;
        display: flex;
        flex-direction: column;
        gap: 0.4rem;

        > li {
            padding: 0.4rem 0.6rem;
            background-color: #f5f5f5;
            border-left: solid 3px #82c8a0;
            border-radius: 0 4px 4px 0;
            font-size: 0.9rem;
        }
    }

    .muted {
        color: #666;
    }

    .levelup {
        background-color: #e8f5ee;
        border-color: #1f7a4d;
        color: #1f7a4d;
        font-weight: 700;
    }

    .next-up {
        margin: 0;
    }

    .ability {
        .lbl {
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            color: #555;
        }

        .prof {
            font-size: 0.6rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #1f7a4d;
        }

        &.trained {
            border-color: #1f7a4d;
            background-color: #f2fbf6;
        }
    }

    .starter {
        padding: 0.6rem 0.8rem;
        border-left: solid 3px #1f7a4d;
        background-color: #f2fbf6;
        border-radius: 0 4px 4px 0;

        h3 {
            border-bottom: none;
            margin-bottom: 0.35rem;
        }
    }

    .conditions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
    }

    .chip {
        padding: 0.2rem 0.6rem;
        border-radius: 999px;
        font-size: 0.85rem;

        /* Applied conditions differ by fill, weight and border -- a chip row
           read at a glance across a table needs more than a tint. */
        &.on {
            background-color: #7c253e;
            border-color: #7c253e;
            color: #fff;
            font-weight: 700;
        }
    }

    .warn {
        padding: 0.4rem 0.6rem;
        background-color: #fff4e5;
        border-left: solid 3px #d98324;
        border-radius: 0 4px 4px 0;
    }

    .small {
        font-size: 0.8rem;
        margin: 0.5rem 0 0;
    }
}
</style>
