<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

import ColourPicker from "../../../core/components/ColourPicker.vue";
import { GridType } from "../../../core/grid";
import { baseAdjust } from "../../../core/http";
import { selectedState } from "../../systems/selected/state";
import { locationSettingsState } from "../../systems/settings/location/state";
import { SpellShape, spellTool } from "../../tools/variants/spell";
import { getOrLoadDataBlock } from "../../dataBlock";

const { t } = useI18n();

const selected = spellTool.isActiveTool;

const isHexGrid = computed(() => locationSettingsState.reactive.gridType.value !== GridType.Square);

// Hex grids used to be offered the Hex template and nothing else, which made
// cone and circle spells unreachable on a hex board -- even though a cone is
// just a Circle with a 60 degree viewing angle and has nothing square about it.
// The hex-aligned template is genuinely hex-only, so it leads; the rest are
// shapes that work on any grid and are the ones people actually cast.
const shapes = computed(() =>
    isHexGrid.value
        ? [SpellShape.Hex, SpellShape.Circle, SpellShape.Cone, SpellShape.Line]
        : [SpellShape.Square, SpellShape.Circle, SpellShape.Cone, SpellShape.Line],
);

// Cone and Line are cast *from* a token, so both need a selection.
const needsCaster = (shape: SpellShape): boolean =>
    shape === SpellShape.Cone || shape === SpellShape.Line;
const hasCaster = computed(() => selectedState.reactive.selected.size > 0);

// The enum values were being used directly as font-awesome icon names,
// which only worked because the picker was hidden on hex grids -- "hex" and
// "line" are not icons. Map them explicitly instead.
const iconMapping: Record<string, string> = {
    [SpellShape.Square]: "square",
    [SpellShape.Circle]: "circle",
    [SpellShape.Hex]: "hexagon",
    [SpellShape.Line]: "slash",
};

const translationMapping = {
    [SpellShape.Square]: t("game.ui.tools.DrawTool.square"),
    [SpellShape.Circle]: t("game.ui.tools.DrawTool.circle"),
    [SpellShape.Cone]: t("game.ui.tools.DrawTool.cone"),
    [SpellShape.Hex]: t("game.ui.tools.DrawTool.square"),
    [SpellShape.Line]: "Line",
};

const stepSize = computed(() => {
    if (isHexGrid.value && spellTool.state.selectedSpellShape === SpellShape.Hex) {
        return 1;
    }
    return 5;
});

// The condition vocabulary belongs to the character sheet mod, which keeps
// it in a room DataBlock. Reading it here is a deliberate, narrow coupling:
// the alternative is a second hardcoded list that drifts from the sheets.
const conditions = ref<{ id: string; name: string }[]>([]);

onMounted(async () => {
    const block = await getOrLoadDataBlock<{ conditions?: { id: string; name: string }[] }>({
        source: "scc",
        name: "catalogue",
        category: "room",
    });
    conditions.value = block?.data.conditions ?? [];
});

async function selectShape(shape: SpellShape): Promise<void> {
    spellTool.state.selectedSpellShape = shape;
    await spellTool.drawShape();
}
</script>

<template>
    <div v-if="selected" class="tool-detail">
        <!-- This was `v-if="!isHexGrid"`, which hid the shape picker
             entirely on hex boards and left the tool stuck on one template. -->
        <div class="selectgroup">
            <div
                v-for="shape in shapes"
                :key="shape"
                class="option"
                :class="{
                    'option-selected': spellTool.state.selectedSpellShape === shape,
                    disabled: !hasCaster && needsCaster(shape),
                }"
                :title="translationMapping[shape]"
                @click="selectShape(shape)"
            >
                <font-awesome-icon v-if="shape !== 'cone'" :icon="iconMapping[shape]" />
                <img v-else :src="baseAdjust('static/img/cone.svg')" />
            </div>
        </div>
        <p v-if="spellTool.state.lastTargets.length > 0" class="targets">
            Last cast caught
            <strong>{{ spellTool.state.lastTargets.filter((x) => x.visible).length }}</strong>
            <template v-if="spellTool.state.lastTargets.some((x) => !x.visible)">
                ({{ spellTool.state.lastTargets.filter((x) => !x.visible).length }} out of sight)
            </template>
        </p>
        <div id="grid">
            <label for="size" style="flex: 5">{{ t("game.ui.tools.SpellTool.size") }}</label>
            <input
                id="size"
                v-model.number="spellTool.state.size"
                type="number"
                style="flex: 1; align-self: center"
                min="0"
                :step="stepSize"
            />
            <template v-if="isHexGrid && spellTool.state.selectedSpellShape === SpellShape.Hex">
                <label for="oddHexOrientation" style="flex: 5">Odd Hex Orientation</label>
                <input
                    id="oddHexOrientation"
                    v-model.number="spellTool.state.oddHexOrientation"
                    type="checkbox"
                    style="flex: 1; align-self: center"
                />
            </template>
            <template v-if="spellTool.state.selectedSpellShape === SpellShape.Line">
                <label for="lineWidth" style="flex: 5">Width</label>
                <input
                    id="lineWidth"
                    v-model.number="spellTool.state.lineWidth"
                    type="number"
                    style="flex: 1; align-self: center"
                    min="1"
                    step="5"
                />
            </template>
            <label for="los" style="flex: 5">Only what the caster sees</label>
            <button
                id="los"
                class="slider-checkbox"
                :aria-pressed="spellTool.state.requireLineOfSight"
                @click="spellTool.state.requireLineOfSight = !spellTool.state.requireLineOfSight"
            ></button>
            <label for="condition" style="flex: 5">Inflicts</label>
            <select id="condition" v-model="spellTool.state.condition" style="flex: 1">
                <option value="">nothing</option>
                <option v-for="c of conditions" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <label for="colour" style="flex: 5">{{ t("common.fill_color") }}</label>
            <ColourPicker
                v-model:colour="spellTool.state.colour"
                class="option"
                :title="t('game.ui.tools.DrawTool.background_color')"
            />
            <label for="public" style="flex: 5">{{ t("game.ui.selection.edit_dialog.dialog.show_annotation") }}</label>
            <button
                id="public"
                class="slider-checkbox"
                :aria-pressed="spellTool.state.showPublic"
                @click="spellTool.state.showPublic = !spellTool.state.showPublic"
            ></button>
        </div>
    </div>
</template>

<style scoped lang="scss">
.option {
    padding: 6px;
    border: solid 1px var(--pa-accent);
    border-radius: 0;
    flex: 1 1;
    display: flex;
    justify-content: center;
    align-items: center;
    font-size: 13px;
    min-width: 25px;

    img {
        width: 1.25em;
    }
}

.option-selected,
.option:hover {
    background-color: var(--pa-accent);
    cursor: pointer;
}

.selectgroup {
    display: flex;
    margin-bottom: 10px;

    > .option:first-of-type {
        border-top-left-radius: 10px;
        border-bottom-left-radius: 10px;
    }

    > .option:last-of-type {
        border-top-right-radius: 10px;
        border-bottom-right-radius: 10px;
    }
}

#grid {
    display: grid;
    grid-template-columns: 1fr 0.5fr;
    row-gap: 5px;
    align-items: center;
}

.targets {
    margin: 0 0 0.5rem;
    font-size: 0.85rem;
    color: var(--pa-text-muted);
}

.disabled {
    /* the cone svg is not inlined so just setting color does not work */
    filter: invert(52%) sepia(18%) saturate(268%) hue-rotate(173deg) brightness(92%) contrast(87%);
    cursor: not-allowed;

    &:hover,
    &:hover * {
        cursor: not-allowed;
        background-color: inherit;
    }
}
</style>

<style scoped lang="scss">
.tool-detail {
    display: block;
}
</style>
