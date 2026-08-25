<script setup lang="ts">
/*
 * Sides panel: who is with whom.
 *
 * The board tells you where a token is, never whose side it is on -- so a DM
 * running six goblins and two PCs has to hold that in their head, and the ghost
 * has no way to answer "attack the nearest enemy" at all. This panel is the one
 * place that mapping is written down; everything else (initiative grouping,
 * death saves, ghost targeting) reads it back out of the same DataBlock.
 *
 * Tokens are listed by faction with an Unaligned bucket at the bottom, because
 * the job you actually do at the table is "these three are enemies", not
 * "open each token's settings in turn".
 */
import { computed, onMounted, ref, watch } from "vue";

import type { GlobalId } from "../../core/id";
import { LayerName } from "../models/floor";
import { factionSystem, getFaction, isProvoked } from "../systems/factions";
import { factionState } from "../systems/factions/state";
import type { Disposition, FactionId } from "../systems/factions/types";
import { DISPOSITIONS, DISPOSITION_COLOURS } from "../systems/factions/types";
import { uiState } from "../systems/ui/state";
import { uiSystem } from "../systems/ui";

import { collectShapes } from "./shapeInventory";

const visible = computed(() => uiState.reactive.showFactions);

onMounted(() => void factionSystem.load());

// A location load clears every system, including this one. The panel stays
// mounted through it, so without this it would sit showing the default three
// sides with nobody assigned to them.
watch(
    () => factionState.reactive.loaded,
    (loaded) => {
        if (!loaded) void factionSystem.load();
    },
);

const newFactionName = ref("");
const newFactionDisposition = ref<Disposition>("hostile");

type Entry = { id: GlobalId; name: string };

/**
 * Every token on the board, across floors.
 *
 * Restricted to the token and DM layers: the map layer is scenery and the fow
 * layers are lighting, and listing those would bury the eight things you care
 * about under a hundred you do not.
 */
const tokens = computed<Entry[]>(() => {
    // Touch the faction data so renames/re-assignments re-run this.
    void factionState.reactive.data;

    return collectShapes({ layers: [LayerName.Tokens, LayerName.Dm], namedOnly: true }).sort((a, b) =>
        a.name.localeCompare(b.name),
    );
});

const grouped = computed(() => {
    const groups = factionState.reactive.data.factions.map((faction) => ({
        faction,
        members: tokens.value.filter((t) => getFaction(t.id)?.id === faction.id),
    }));
    const unaligned = tokens.value.filter((t) => getFaction(t.id) === undefined);
    return { groups, unaligned };
});

function assign(shape: GlobalId, event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    factionSystem.setFaction(shape, value === "" ? undefined : (value as FactionId));
}

function addFaction(): void {
    const name = newFactionName.value.trim();
    if (name === "") return;
    factionSystem.addFaction(name, newFactionDisposition.value, DISPOSITION_COLOURS[newFactionDisposition.value]);
    newFactionName.value = "";
}
</script>

<template>
    <div v-if="visible" id="faction-panel">
        <header>
            <span>Sides</span>
            <button title="Close" @click="uiSystem.toggleFactions()">&times;</button>
        </header>

        <div class="body">
            <div v-for="group of grouped.groups" :key="group.faction.id" class="faction">
                <div class="faction-header">
                    <span class="swatch" :style="{ backgroundColor: group.faction.colour }"></span>
                    <input
                        class="faction-name"
                        :value="group.faction.name"
                        @change="factionSystem.updateFaction(group.faction.id, { name: ($event.target as HTMLInputElement).value })"
                    />
                    <select
                        :value="group.faction.disposition"
                        @change="factionSystem.updateFaction(group.faction.id, { disposition: ($event.target as HTMLSelectElement).value as Disposition })"
                    >
                        <option v-for="d of DISPOSITIONS" :key="d" :value="d">{{ d }}</option>
                    </select>
                    <button title="Remove faction" @click="factionSystem.removeFaction(group.faction.id)">&times;</button>
                </div>

                <div v-for="member of group.members" :key="member.id" class="member">
                    <span class="member-name">{{ member.name }}</span>
                    <label
                        v-if="group.faction.disposition !== 'party'"
                        :title="'Temporarily hostile, regardless of ' + group.faction.name"
                    >
                        <input
                            type="checkbox"
                            :checked="isProvoked(member.id)"
                            @change="factionSystem.setProvoked(member.id, ($event.target as HTMLInputElement).checked)"
                        />
                        provoked
                    </label>
                    <select :value="group.faction.id" @change="assign(member.id, $event)">
                        <option value="">— unaligned —</option>
                        <option v-for="f of factionState.reactive.data.factions" :key="f.id" :value="f.id">
                            {{ f.name }}
                        </option>
                    </select>
                </div>
                <div v-if="group.members.length === 0" class="empty">no tokens</div>
            </div>

            <div class="faction">
                <div class="faction-header"><span class="swatch neutral"></span><span class="faction-name">Unaligned</span></div>
                <div v-for="member of grouped.unaligned" :key="member.id" class="member">
                    <span class="member-name">{{ member.name }}</span>
                    <select value="" @change="assign(member.id, $event)">
                        <option value="">— unaligned —</option>
                        <option v-for="f of factionState.reactive.data.factions" :key="f.id" :value="f.id">
                            {{ f.name }}
                        </option>
                    </select>
                </div>
                <div v-if="grouped.unaligned.length === 0" class="empty">nothing unaligned</div>
            </div>

            <div class="add">
                <input v-model="newFactionName" placeholder="New faction" @keyup.enter="addFaction" />
                <select v-model="newFactionDisposition">
                    <option v-for="d of DISPOSITIONS" :key="d" :value="d">{{ d }}</option>
                </select>
                <button @click="addFaction">add</button>
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
#faction-panel {
    position: absolute;
    top: 6rem;
    right: 1.5rem;
    width: 22rem;
    max-height: 70vh;
    display: flex;
    flex-direction: column;
    background-color: white;
    border: solid 1px var(--pa-secondary-light, #7c253e);
    border-radius: 0.5rem;
    box-shadow: 0 0 1rem rgb(0 0 0 / 40%);
    pointer-events: auto;
    z-index: 100;

    header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.5rem 0.75rem;
        font-weight: bold;
        border-bottom: solid 1px rgb(0 0 0 / 15%);

        button {
            border: none;
            background: none;
            font-size: 1.25rem;
            cursor: pointer;
        }
    }

    .body {
        overflow-y: auto;
        padding: 0.5rem 0.75rem 0.75rem;
    }

    .faction {
        margin-bottom: 0.75rem;
    }

    .faction-header {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        margin-bottom: 0.25rem;

        select {
            max-width: 6rem;
        }

        button {
            border: none;
            background: none;
            cursor: pointer;
        }
    }

    .faction-name {
        flex: 1;
        font-weight: bold;
        border: none;
        border-bottom: solid 1px transparent;

        &:focus {
            border-bottom-color: var(--pa-secondary-light, #7c253e);
        }
    }

    .swatch {
        width: 0.75rem;
        height: 0.75rem;
        border-radius: 50%;
        flex-shrink: 0;

        &.neutral {
            background-color: #999;
        }
    }

    .member {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.15rem 0 0.15rem 1.1rem;

        label {
            display: flex;
            align-items: center;
            gap: 0.2rem;
            font-size: 0.75rem;
            white-space: nowrap;
        }

        select {
            max-width: 7rem;
        }
    }

    .member-name {
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .empty {
        padding-left: 1.1rem;
        font-size: 0.8rem;
        font-style: italic;
        opacity: 0.6;
    }

    .add {
        display: flex;
        gap: 0.35rem;
        border-top: solid 1px rgb(0 0 0 / 15%);
        padding-top: 0.5rem;

        input {
            flex: 1;
            min-width: 0;
        }
    }
}
</style>
