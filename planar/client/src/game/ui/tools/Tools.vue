<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

import { baseAdjust } from "../../../core/http";
import { ToolMode, ToolName } from "../../models/tools";
import { accessState } from "../../systems/access/state";
import { floorSystem } from "../../systems/floors";
import { gameSystem } from "../../systems/game";
import { gameState } from "../../systems/game/state";
import { roomState } from "../../systems/room/state";
import { locationSettingsState } from "../../systems/settings/location/state";
import { playerSettingsState } from "../../systems/settings/players/state";
import { activeModeTools, activeTool, activeToolMode, dmTools, setActiveMode, toolMap } from "../../tools/tools";
import { initiativeStore } from "../initiative/state";

import DiceTool from "./DiceTool.vue";
import DrawTool from "./DrawTool.vue";
import LightTool from "./LightTool.vue";
import MapTool from "./MapTool.vue";
import RulerTool from "./RulerTool.vue";
import SelectTool from "./SelectTool.vue";
import SpellTool from "./SpellTool.vue";
import VisionTool from "./VisionTool.vue";

const { t } = useI18n();

const visibleTools = computed(() => {
    {
        const tools = [];
        for (const [toolName] of activeModeTools.value) {
            if (dmTools.includes(toolName) && !gameState.reactive.isDm) continue;

            if (toolName === ToolName.Vision) {
                if (accessState.reactive.ownedTokens.size <= 1) continue;
            } else if (toolName === ToolName.Dice) {
                if (!roomState.reactive.enableDice) continue;
            }

            const tool = toolMap[toolName];
            tools.push({
                name: toolName,
                translation: tool.toolTranslation,
                alert: tool.alert.value,
            });
        }
        return tools;
    }
});

function getStaticToolImg(img: string): string {
    return baseAdjust(`/static/img/tools/${img}`);
}

// Build and Play are two states of one setting, so they're rendered as a
// segmented control (a radiogroup), not as one <div> that flips when clicked.
// The old version showed both words at once, styled the active one bold and the
// other italic, and toggled on click -- which reads as two options but behaves
// as one button, and gives no clue which mode a click will land you in. The
// mode decides which tools exist at all, so that ambiguity is expensive.
const toolModes = computed(() => [
    { mode: ToolMode.Build, name: t("tool.Build") },
    { mode: ToolMode.Play, name: t("tool.Play") },
]);

function toggleFakePlayer(): void {
    gameSystem.setFakePlayer(!gameState.raw.isFakePlayer);
}

function toggleLoS(): void {
    locationSettingsState.mutableReactive.losOverwritten = !locationSettingsState.raw.losOverwritten;
    floorSystem.invalidateLightAllFloors();
}
</script>

<template>
    <div id="tools">
        <!--
            Rendered before the tool bar in the DOM, not after: #tools is a
            bottom-anchored flex column now, so the detail panel sits above the
            bar by virtue of the layout rather than by a hand-tuned offset.
        -->
        <div id="tool-details">
            <SelectTool v-lazy-show="activeTool === ToolName.Select" />
            <SpellTool v-lazy-show="activeTool === ToolName.Spell" />
            <DrawTool v-lazy-show="activeTool === ToolName.Draw" />
            <RulerTool v-lazy-show="activeTool === ToolName.Ruler" />
            <MapTool v-lazy-show="activeTool === ToolName.Map" />
            <LightTool v-lazy-show="activeTool === ToolName.Light" />
            <VisionTool v-lazy-show="activeTool === ToolName.Vision" />
            <DiceTool v-lazy-show="roomState.reactive.enableDice && activeTool === ToolName.Dice" />
        </div>
        <div id="toolselect">
            <ul>
                <li v-for="tool in visibleTools" :key="tool.name" class="tool">
                    <button
                        :id="tool.name + '-selector'"
                        type="button"
                        :class="{ 'tool-selected': activeTool === tool.name, 'tool-alert': tool.alert }"
                        :title="tool.translation"
                        :aria-pressed="activeTool === tool.name"
                        @click="activeTool = tool.name"
                    >
                        <template v-if="playerSettingsState.reactive.useToolIcons.value">
                            <img :src="getStaticToolImg(`${tool.name.toLowerCase()}.svg`)" alt="" />
                            <span class="sr-only">{{ tool.translation }}</span>
                        </template>
                        <template v-else>{{ tool.translation }}</template>
                    </button>
                </li>
            </ul>
            <div id="tool-status">
                <!--
                    These three were unlabelled <div>s reading "FP", "LOS" and
                    "INI", explained only by a title tooltip -- invisible to
                    keyboard and touch users, and opaque to anyone new. They are
                    on/off switches, so they are buttons with aria-pressed and
                    a written-out label.
                -->
                <div v-if="gameState.isDmOrFake.value" id="tool-status-toggles">
                    <button
                        type="button"
                        class="status-toggle"
                        :class="{ active: gameState.reactive.isFakePlayer }"
                        :title="t('game.ui.tools.tools.FP_title')"
                        :aria-pressed="gameState.reactive.isFakePlayer"
                        @click="toggleFakePlayer"
                    >
                        <abbr :title="t('game.ui.tools.tools.FP_title')">
                            {{ t("game.ui.tools.tools.FP") }}
                        </abbr>
                        <span class="toggle-label">as player</span>
                    </button>
                    <button
                        v-if="locationSettingsState.reactive.fowLos.value"
                        type="button"
                        class="status-toggle"
                        :class="{
                            active: !locationSettingsState.reactive.losOverwritten,
                            disabled: locationSettingsState.reactive.losOverwritten,
                        }"
                        :title="t('game.ui.tools.tools.LOS_title')"
                        :aria-pressed="!locationSettingsState.reactive.losOverwritten"
                        @click="toggleLoS"
                    >
                        <abbr :title="t('game.ui.tools.tools.LOS_title')">
                            {{ t("game.ui.tools.tools.LOS") }}
                        </abbr>
                        <span class="toggle-label">line of sight</span>
                    </button>
                    <button
                        type="button"
                        class="status-toggle"
                        :class="{ active: initiativeStore.state.isActive }"
                        :title="t('game.ui.tools.tools.INI_title')"
                        :aria-pressed="initiativeStore.state.isActive"
                        @click="initiativeStore.toggleActive"
                    >
                        <abbr :title="t('game.ui.tools.tools.INI_title')">
                            {{ t("game.ui.tools.tools.INI") }}
                        </abbr>
                        <span class="toggle-label">initiative</span>
                    </button>
                </div>
                <div style="flex-grow: 1"></div>
                <div
                    id="tool-status-modes"
                    role="radiogroup"
                    :aria-label="t('game.ui.tools.tools.change_mode')"
                    :title="t('game.ui.tools.tools.change_mode')"
                >
                    <button
                        v-for="mode of toolModes"
                        :key="mode.name"
                        type="button"
                        role="radio"
                        :class="{ selected: activeToolMode === mode.mode }"
                        :aria-checked="activeToolMode === mode.mode"
                        @click="setActiveMode(mode.mode)"
                    >
                        {{ mode.name }}
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
#tools > * {
    pointer-events: auto;
}

/*
 * The whole bar is one bottom-right stack. The tool detail panel used to be
 * positioned separately with a hardcoded `--detailBottom` of 7.8rem or 6.6rem
 * depending on whether tool icons were on -- a magic number tracking this
 * element's own height, which silently desynced the moment any padding here
 * changed. Both are now flex children of a bottom-anchored column, so the
 * layout measures itself and nothing has to be re-tuned by hand.
 */
/*
 * Pinned to the bottom-right corner of the UI layer, not placed by the grid.
 *
 * `#ui` declares a "tools" grid area but nothing ever claims it -- no element
 * sets `grid-area: tools` (nor `menu`, `locations` or `annotation`). #tools is
 * therefore auto-placed into whatever cell is free, which lands it in the
 * middle of the board. That was invisible for as long as #toolselect was
 * absolutely positioned out of its cell, and only surfaced when this became a
 * flow layout. Anchoring the wrapper keeps the corner AND the self-measuring
 * stack; claiming the grid area instead would tie the bar's width to a `1fr`
 * column it doesn't fit in.
 */
#tools {
    position: absolute;
    right: 1.5rem;
    bottom: 0.8rem;

    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: flex-end;

    /* Never taller than the board; the dice panel scrolls instead. */
    max-height: calc(100% - 1.6rem);
    min-height: 0;
}

#tool-details {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    /* Hidden panels are display:none and take no space, so this only applies
       when something is actually shown. */
    min-height: 0;
    overflow-y: auto;
}

#toolselect {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    /* The bar must never be the thing that scrolls away. */
    flex: 0 0 auto;

    * {
        user-select: none !important;
        -webkit-user-drag: none !important;
    }

    > ul {
        display: flex;
        list-style: none;
        padding: 0;
        margin: 0;
        border: solid 1px cadetblue;
        background-color: cadetblue;
        border-radius: var(--pa-radius-md) var(--pa-radius-md) 0 var(--pa-radius-md);
        overflow: hidden;
    }

    #tool-status {
        display: flex;
        align-items: flex-start;

        #tool-status-toggles {
            padding-top: 0.3em;
            display: flex;
            gap: var(--pa-space-2);
        }

        #tool-status-modes {
            display: flex;
            background-color: cadetblue;
            padding: 0.25em;
            gap: 0.25em;
            border-radius: 0 0 var(--pa-radius-md) var(--pa-radius-md);

            > button {
                padding: 0.2em 0.7em;
                border: solid 1px transparent;
                border-radius: var(--pa-radius-sm);
                background: none;
                color: var(--pa-text-inverse);
                font: inherit;
                cursor: pointer;

                &:hover {
                    background-color: rgb(255 255 255 / 20%);
                }

                /* The selected mode is filled, not merely bolded: weight alone
                   is a weak signal and was previously the only one. */
                &.selected {
                    background-color: var(--pa-surface);
                    color: var(--pa-text);
                    font-weight: 700;
                }
            }
        }
    }
}

.status-toggle {
    display: flex;
    align-items: center;
    gap: 0.35rem;

    /*
     * Opaque, not a 25% black wash.
     *
     * The original translucent background sat over whatever the map happened to
     * be, so white text on it ranged from readable (dark map) to invisible
     * (a white hex grid, which is what this table uses). It survived only
     * because the labels were three bold capitals. They are words now, so the
     * background has to carry its own contrast instead of borrowing the map's.
     */
    background-color: var(--pa-surface-inverse);
    padding: 5px 8px;
    border-radius: 7px;
    border: solid 2px var(--pa-surface-inverse);
    color: var(--pa-text-inverse);
    font: inherit;
    cursor: pointer;

    > abbr {
        font-weight: 700;
        text-decoration: none;
    }

    .toggle-label {
        font-size: 0.75rem;
        /* No opacity: it was the difference between readable and not. */
    }

    /*
     * #39ff14 on a dark translucent background is legible, but "on" was being
     * signalled by colour alone. The added border weight and background give a
     * second, non-colour cue -- which also matters for the ~8% of men with a
     * colour vision deficiency.
     */
    &.active {
        border-color: #39ff14;
        color: #39ff14;
    }

    &.disabled {
        border-color: var(--pa-danger-surface);
        color: var(--pa-danger-surface);
    }
}

.tool {
    display: flex;

    > button {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 0.625rem;

        border: none;
        border-right: solid 1px var(--pa-accent);
        background-color: var(--pa-surface-sunken);
        color: var(--pa-text);
        font: inherit;
        text-decoration: none;
        cursor: pointer;

        &:hover {
            background-color: var(--pa-accent);
        }

        /* Selected state carries a left bar as well as a fill, so it survives
           being printed, screenshotted or seen by someone who can't separate
           the green from the grey. */
        &.tool-selected {
            background-color: var(--pa-accent);
            box-shadow: inset 0 3px 0 var(--pa-accent-ink);
        }

        &.tool-alert {
            background-color: var(--pa-danger-surface);
        }

        > img {
            height: 2.5rem;
            width: 2.5rem;
        }
    }
}

/* Visually hidden, still announced. The icon-only toolbar had alt text doing
   this job, which meant the label vanished when icons were switched off. */
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
    border: 0;
}
</style>

<style lang="scss">
.tool-detail {
    /* In flow now. It used to be absolutely positioned against a hardcoded
       offset that had to match the tool bar's height; see #tools above. */
    margin-bottom: var(--pa-space-2);
    padding: var(--pa-space-4);
    max-height: 60vh;
    overflow-y: auto;

    border: solid 1px var(--pa-surface-inverse);
    border-radius: var(--pa-radius-lg);

    background-color: var(--pa-surface);
    color: var(--pa-text);
    box-shadow: var(--pa-shadow-lg);

    input {
        width: 100%;
        box-sizing: border-box;
    }
}
</style>
