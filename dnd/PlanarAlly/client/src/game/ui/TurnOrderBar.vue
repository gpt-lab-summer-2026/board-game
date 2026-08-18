<script setup lang="ts">
/**
 * The turn order, across the top, sized for a projector.
 *
 * Deliberately *not* a replacement for the initiative panel: that panel is where
 * order is edited, effects are added and values are rolled, and all of it is
 * fiddly mouse work that nobody at the table should have to watch. This is the
 * read-only half -- who is up, who is next, which side they are on -- at a size
 * that survives being thrown on a wall.
 *
 * Faction colour is carried on the border rather than a swatch or a label,
 * because it is the one property that has to be legible from across a room.
 */
import type { DeepReadonly } from "vue";
import { computed, onMounted, watch } from "vue";

import type { GlobalId } from "../../core/id";
import type { IAsset } from "../interfaces/shapes/asset";
import { getImageSrcFromHash } from "../../assets/utils";
import type { InitiativeData } from "../models/initiative";
import { getShape } from "../id";
import { gameState } from "../systems/game/state";
import { getFaction, isProvoked } from "../systems/factions";
import { propertiesState } from "../systems/properties/state";
import { turnBudgetSystem } from "../systems/turnbudget";
import { turnBudgetState } from "../systems/turnbudget/state";
import { initiativeStore } from "./initiative/state";

const HOSTILE_FALLBACK = "#a32f2f";

const isDm = computed(() => gameState.reactive.isDm);
const round = computed(() => initiativeStore.state.roundCounter);
const turn = computed(() => initiativeStore.state.turnCounter);
const budget = computed(() => turnBudgetState.reactive.data);

/** Only combatants the viewer is allowed to see, in initiative order. */
const order = computed(() =>
    initiativeStore.state.locationData.filter((a) => isDm.value || a.isVisible),
);

const visible = computed(() => initiativeStore.state.isActive && order.value.length > 0);

const activeActor = computed<DeepReadonly<InitiativeData> | undefined>(() => order.value[turn.value]);
const activeId = computed<GlobalId | null>(() => activeActor.value?.globalId ?? null);

function nameOf(actor: DeepReadonly<InitiativeData>): string {
    if (actor.localId === undefined) return "?";
    const props = propertiesState.reactive.data.get(actor.localId);
    if (props === undefined) return "?";
    return props.nameVisible || isDm.value ? props.name : "?";
}

function imageOf(actor: DeepReadonly<InitiativeData>): string | undefined {
    if (actor.localId === undefined) return undefined;
    const shape = getShape(actor.localId);
    if (shape?.type !== "assetrect") return undefined;
    return getImageSrcFromHash((shape as IAsset).assetHash);
}

/**
 * The border colour for a combatant.
 *
 * A provoked neutral is drawn hostile, matching how the ghost reads it -- the
 * bar should not say "neutral" about something that will be attacked on sight.
 */
function colourOf(actor: DeepReadonly<InitiativeData>): string {
    if (isProvoked(actor.globalId)) return HOSTILE_FALLBACK;
    return getFaction(actor.globalId)?.colour ?? "#7a7a7a";
}

function sideOf(actor: DeepReadonly<InitiativeData>): string {
    if (isProvoked(actor.globalId)) return "Provoked";
    return getFaction(actor.globalId)?.name ?? "Unaligned";
}

// Resetting on a watcher rather than from inside PA's initiative store keeps the
// fork's diff off upstream's code. Guarded to the DM so five browsers do not
// race to write the same reset.
watch(
    [round, turn, activeId],
    () => {
        if (!isDm.value) return;
        turnBudgetSystem.syncToTurn(round.value, turn.value, activeId.value);
    },
    { immediate: true },
);

onMounted(() => void turnBudgetSystem.load());
</script>

<template>
    <div v-if="visible" id="turn-order-bar" :class="{ dm: isDm }">
        <div class="round">
            <span class="label">Round</span>
            <span class="value">{{ round + 1 }}</span>
        </div>

        <ol class="order">
            <li
                v-for="(actor, index) of order"
                :key="actor.globalId"
                class="chip"
                :class="{ current: index === turn, faded: index < turn }"
                :style="{ '--side': colourOf(actor) }"
                :title="`${nameOf(actor)} — ${sideOf(actor)}`"
            >
                <img v-if="imageOf(actor)" :src="imageOf(actor)" alt="" />
                <span v-else class="initial">{{ nameOf(actor).slice(0, 2) }}</span>
                <span class="name">{{ nameOf(actor) }}</span>
                <span v-if="actor.initiative !== undefined" class="init">{{ actor.initiative }}</span>
            </li>
        </ol>

        <div v-if="activeActor" class="budget" :title="'What ' + nameOf(activeActor) + ' has left this turn'">
            <button
                type="button"
                class="pip"
                :class="{ spent: budget.action }"
                :disabled="!isDm"
                @click="turnBudgetSystem.spend('action', !budget.action)"
            >
                Action
            </button>
            <button
                type="button"
                class="pip"
                :class="{ spent: budget.bonus }"
                :disabled="!isDm"
                @click="turnBudgetSystem.spend('bonus', !budget.bonus)"
            >
                Bonus
            </button>
            <span
                class="pip"
                :class="{ spent: activeId !== null && !turnBudgetSystem.hasReaction(activeId) }"
            >
                Reaction
            </span>
            <span class="pip moved">{{ budget.movementUsed }} / {{ budget.speed }} ft</span>
        </div>

        <div v-if="isDm" class="controls">
            <button type="button" title="Previous turn" @click="initiativeStore.previousTurn()">‹</button>
            <button type="button" title="Next turn" @click="initiativeStore.nextTurn()">›</button>
        </div>
    </div>
</template>

<style scoped lang="scss">
#turn-order-bar {
    position: absolute;
    top: 0.5rem;
    left: 50%;
    transform: translateX(-50%);
    z-index: 20;

    display: flex;
    align-items: center;
    gap: 0.75rem;

    max-width: min(96vw, 1600px);
    padding: 0.4rem 0.75rem;

    background-color: rgba(20, 20, 24, 0.82);
    border-radius: 10px;
    color: white;
    // The board is the thing being looked at; the bar sits over it and must not
    // swallow a click meant for a token.
    pointer-events: auto;

    .round {
        display: flex;
        flex-direction: column;
        align-items: center;
        line-height: 1;

        .label {
            font-size: 0.6rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            opacity: 0.7;
        }

        .value {
            font-size: 1.4rem;
            font-weight: 700;
        }
    }

    .order {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        margin: 0;
        padding: 0;
        list-style: none;
        overflow-x: auto;
    }

    .chip {
        position: relative;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.15rem;
        width: 4rem;
        padding: 0.25rem;
        border-radius: 8px;
        // The faction colour, as the one thing readable from a distance.
        border: solid 3px var(--side);
        background-color: rgba(255, 255, 255, 0.06);
        transition: transform 120ms ease;

        img,
        .initial {
            width: 2.4rem;
            height: 2.4rem;
            border-radius: 6px;
            object-fit: cover;
            background-color: rgba(0, 0, 0, 0.35);
            display: grid;
            place-items: center;
            font-weight: 700;
            text-transform: uppercase;
        }

        .name {
            max-width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 0.65rem;
        }

        .init {
            position: absolute;
            top: -0.5rem;
            right: -0.4rem;
            min-width: 1.1rem;
            padding: 0 0.2rem;
            border-radius: 999px;
            background-color: var(--side);
            font-size: 0.65rem;
            font-weight: 700;
            text-align: center;
        }

        &.current {
            transform: scale(1.12);
            background-color: rgba(255, 255, 255, 0.2);
            box-shadow: 0 0 0 2px white;
        }

        &.faded {
            opacity: 0.45;
        }
    }

    .budget {
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }

    .pip {
        padding: 0.15rem 0.4rem;
        border: solid 1px rgba(255, 255, 255, 0.35);
        border-radius: 999px;
        background: none;
        color: inherit;
        font-size: 0.65rem;
        white-space: nowrap;

        &.spent {
            opacity: 0.35;
            text-decoration: line-through;
        }

        &.moved {
            text-decoration: none;
        }
    }

    button.pip:not(:disabled) {
        cursor: pointer;
    }

    .controls button {
        width: 1.6rem;
        height: 1.6rem;
        border: solid 1px rgba(255, 255, 255, 0.35);
        border-radius: 6px;
        background: none;
        color: inherit;
        font-size: 1rem;
        cursor: pointer;
    }
}
</style>
