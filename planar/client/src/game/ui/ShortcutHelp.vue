<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";

import { SHORTCUT_GROUPS } from "../input/keyboard/bindings";
import { gameState } from "../systems/game/state";
import { uiState } from "../systems/ui/state";
import { uiSystem } from "../systems/ui";

const visible = computed(() => uiState.reactive.showShortcutHelp);

// DM-only rows would be noise for a player who cannot act on them.
const groups = computed(() =>
    SHORTCUT_GROUPS.map((group) => ({
        title: group.title,
        shortcuts: group.shortcuts.filter((s) => s.dmOnly !== true || gameState.reactive.isDm),
    })).filter((group) => group.shortcuts.length > 0),
);

function close(): void {
    uiSystem.setShortcutHelp(false);
}

// Escape closes it. Registered here rather than in the global key handler so
// the two cannot get out of step: the overlay owns its own dismissal.
function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape" && visible.value) {
        event.preventDefault();
        event.stopPropagation();
        close();
    }
}

onMounted(() => window.addEventListener("keydown", onKeydown, true));
onUnmounted(() => window.removeEventListener("keydown", onKeydown, true));
</script>

<template>
    <div v-if="visible" id="shortcut-help-backdrop" @click.self="close">
        <div id="shortcut-help" role="dialog" aria-modal="true" aria-labelledby="shortcut-help-title">
            <header>
                <h2 id="shortcut-help-title">Keyboard shortcuts</h2>
                <button type="button" title="Close" @click="close">
                    <font-awesome-icon :icon="['far', 'window-close']" />
                </button>
            </header>

            <div class="groups">
                <section v-for="group of groups" :key="group.title">
                    <h3>{{ group.title }}</h3>
                    <dl>
                        <template v-for="shortcut of group.shortcuts" :key="shortcut.description">
                            <dt>
                                <template v-for="(key, index) of shortcut.keys" :key="key">
                                    <span v-if="index > 0" class="plus">+</span>
                                    <kbd>{{ key }}</kbd>
                                </template>
                            </dt>
                            <dd>{{ shortcut.description }}</dd>
                        </template>
                    </dl>
                </section>
            </div>

            <footer>Press <kbd>?</kbd> at any time to bring this back.</footer>
        </div>
    </div>
</template>

<style scoped lang="scss">
#shortcut-help-backdrop {
    position: fixed;
    inset: 0;
    z-index: 100;

    display: flex;
    align-items: center;
    justify-content: center;

    background-color: rgb(0 0 0 / 45%);
    pointer-events: auto;
}

#shortcut-help {
    display: flex;
    flex-direction: column;

    width: min(52rem, 92vw);
    max-height: 85vh;
    padding: var(--pa-space-6);

    background-color: var(--pa-surface);
    color: var(--pa-text);
    border-radius: var(--pa-radius-lg);
    box-shadow: var(--pa-shadow-lg);

    header {
        display: flex;
        align-items: center;
        gap: var(--pa-space-4);
        margin-bottom: var(--pa-space-4);

        h2 {
            flex-grow: 1;
            margin: 0;
            font-size: 1.35rem;
        }

        > button {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 2rem;
            height: 2rem;
            border: none;
            border-radius: var(--pa-radius-sm);
            background: none;
            color: var(--pa-text-muted);
            font-size: 1.25rem;
            cursor: pointer;

            &:hover {
                background-color: var(--pa-surface-sunken);
                color: var(--pa-text);
            }
        }
    }

    .groups {
        overflow-y: auto;
        // Two columns where there's room, one where there isn't. No media
        // query needed: the track count follows the available width.
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr));
        gap: var(--pa-space-6);
    }

    h3 {
        margin: 0 0 var(--pa-space-2);
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--pa-text-muted);
        border-bottom: solid 1px var(--pa-border);
        padding-bottom: var(--pa-space-1);
    }

    dl {
        display: grid;
        grid-template-columns: auto 1fr;
        column-gap: var(--pa-space-4);
        row-gap: var(--pa-space-2);
        margin: 0;
        align-items: baseline;
    }

    dt {
        display: flex;
        align-items: center;
        gap: 0.2rem;
        white-space: nowrap;
    }

    dd {
        margin: 0;
        color: var(--pa-text);
    }

    .plus {
        color: var(--pa-text-muted);
        font-size: 0.8rem;
    }

    footer {
        margin-top: var(--pa-space-4);
        padding-top: var(--pa-space-3);
        border-top: solid 1px var(--pa-border);
        color: var(--pa-text-muted);
        font-size: 0.85rem;
    }
}

kbd {
    display: inline-block;
    padding: 0.1rem 0.4rem;

    background-color: var(--pa-surface-raised);
    border: solid 1px var(--pa-border);
    border-bottom-width: 2px;
    border-radius: var(--pa-radius-sm);

    font-family: inherit;
    font-size: 0.85em;
    line-height: 1.4;
    white-space: nowrap;
}
</style>
