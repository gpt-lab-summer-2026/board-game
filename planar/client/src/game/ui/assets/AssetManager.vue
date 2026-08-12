<script setup lang="ts">
import { nextTick, watch } from "vue";

import { assetGameState } from "../../systems/assets/state";
import { closeAssetManager, toggleAssetManagerDocked } from "../../systems/assets/ui";
import { modalSystem } from "../../systems/modals";
import type { ModalIndex } from "../../systems/modals/types";

import AssetList from "./AssetList.vue";

const emit = defineEmits<(e: "close" | "focus") => void>();
defineExpose({ close });
const props = defineProps<{ modalIndex: ModalIndex }>();

watch(
    () => assetGameState.reactive.managerOpen,
    async (open) => {
        if (open) {
            await nextTick(() => modalSystem.focus(props.modalIndex));
        }
    },
);

function close(): void {
    closeAssetManager();
    emit("close");
}
</script>

<template>
    <div
        v-show="assetGameState.reactive.managerOpen"
        id="asset-container"
        :class="{ docked: assetGameState.reactive.managerDocked }"
    >
        <div id="assets-dialog" @click="$emit('focus')">
            <div id="assets-window-controls">
                <button
                    type="button"
                    :title="
                        assetGameState.reactive.managerDocked
                            ? 'Float this panel over the board'
                            : 'Dock this panel to the side so the board stays visible'
                    "
                    :aria-pressed="assetGameState.reactive.managerDocked"
                    @click="toggleAssetManagerDocked"
                >
                    <!-- window-restore only exists in the regular pack here. -->
                    <font-awesome-icon
                        :icon="
                            assetGameState.reactive.managerDocked
                                ? ['far', 'window-restore']
                                : ['fas', 'angle-double-right']
                        "
                    />
                </button>
                <button type="button" title="Close the asset browser" @click="close">
                    <font-awesome-icon :icon="['far', 'window-close']" />
                </button>
            </div>
            <AssetList />
        </div>
    </div>
</template>

<style lang="scss">
#asset-container {
    position: absolute;
    display: grid;
    justify-items: center;
    padding-top: 10vh;
    align-items: start;
    width: 100vw;
    height: 100vh;
}

#assets-dialog {
    position: relative;
    display: flex;
    flex-direction: column;

    padding: 1.5rem 2rem;
    border-radius: var(--pa-radius-lg);
    max-height: 80vh;
    width: 60vw;

    background-color: var(--pa-surface);
    color: var(--pa-text);

    pointer-events: all;

    box-shadow: var(--pa-shadow-lg);

    font-family:
        "HelveticaNeue-Light", "Helvetica Neue Light", "Helvetica Neue", Helvetica, Arial, "Lucida Grande", sans-serif;

    overflow: hidden;
}

/*
 * Docked mode: a full-height column pinned to the right edge.
 *
 * The point is the placement loop. Floating, the panel sits over the middle of
 * the board, which is why the old code hid it the instant a drag began -- you
 * could not see where you were dropping. Anchored to the edge, the board stays
 * visible and clickable, and assets can be dragged out one after another
 * without the panel going anywhere.
 *
 * `justify-items` and the container padding have to be unset, not overridden
 * with a bigger number: they are what centres the floating dialog.
 */
#asset-container.docked {
    justify-items: end;
    align-items: stretch;
    padding-top: 0;

    #assets-dialog {
        width: min(28rem, 40vw);
        max-height: 100vh;
        height: 100%;
        padding: 1rem 1.25rem;
        border-radius: 0;
        border-left: solid 1px var(--pa-border);
    }
}

#assets-window-controls {
    position: absolute;
    top: 0.6rem;
    right: 0.6rem;
    z-index: 1;

    display: flex;
    gap: 0.25rem;

    > button {
        display: flex;
        align-items: center;
        justify-content: center;

        width: 2rem;
        height: 2rem;

        border: solid 1px transparent;
        border-radius: var(--pa-radius-sm);
        background: none;
        color: var(--pa-text-muted);
        font-size: 1.1rem;
        cursor: pointer;

        &:hover {
            background-color: var(--pa-surface-sunken);
            color: var(--pa-text);
        }

        /* The dock toggle is a two-state control; say so visually as well as
           through aria-pressed. */
        &[aria-pressed="true"] {
            border-color: var(--pa-accent);
            color: var(--pa-accent-ink);
        }
    }
}
</style>
