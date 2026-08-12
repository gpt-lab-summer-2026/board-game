<script setup lang="ts">
import { computed, useTemplateRef, nextTick } from "vue";
import { useI18n } from "vue-i18n";

import type { PanelTab } from "../../../game/systems/ui/types";

import Modal from "./Modal.vue";

const { tabs } = defineProps<{
    visible: boolean;
    tabs: (PanelTab & { props?: object })[];
}>();

const emit = defineEmits<{
    (e: "update:visible", visible: boolean): void;
    (e: "close"): void;
}>();

const selection = defineModel<string | undefined>("selection", { required: true });

const { t } = useI18n();

const activeTab = computed(() => {
    const tab = tabs.find((tab) => tab.id === selection.value);
    if (tab === undefined) return undefined;
    return {
        ...tab,
        props: { ...tab.props, tabSelected: computed(() => tab.id === selection.value) },
    };
});

function setSelection(id: string): void {
    selection.value = id;
}

// ---- keyboard navigation ---------------------------------------------------
//
// This strip is the primary navigation of the shape editor and every settings
// dialog, and it was a list of <div>s with a click handler -- unreachable by
// keyboard entirely. The WAI-ARIA tabs pattern applies: one tab stop for the
// whole set, arrows to move between them, Home/End to jump. That's why the
// selected tab has tabindex 0 and the rest -1 ("roving tabindex"); making all
// of them focusable would force a user to tab through ten items to leave.

const tabRefs = useTemplateRef<HTMLButtonElement[]>("tabRefs");

async function focusTab(index: number): Promise<void> {
    const tab = tabs[index];
    if (tab === undefined) return;
    setSelection(tab.id);
    // The list re-renders on selection, so wait before reaching for the node.
    await nextTick();
    tabRefs.value?.[index]?.focus();
}

async function onTabKeydown(event: KeyboardEvent, index: number): Promise<void> {
    const last = tabs.length - 1;
    let target: number | undefined;

    // Wrapping is deliberate: with a vertical strip this short, stopping dead
    // at the ends is more annoying than surprising.
    if (event.key === "ArrowDown" || event.key === "ArrowRight") target = index === last ? 0 : index + 1;
    else if (event.key === "ArrowUp" || event.key === "ArrowLeft") target = index === 0 ? last : index - 1;
    else if (event.key === "Home") target = 0;
    else if (event.key === "End") target = last;

    if (target === undefined) return;
    // Arrow keys otherwise scroll the dialog out from under the user.
    event.preventDefault();
    await focusTab(target);
}

function hideModal(): void {
    emit("update:visible", false);
    emit("close");
}
</script>

<template>
    <Modal :visible="visible" :colour="'rgba(255, 255, 255, 0.8)'" :mask="false">
        <template #header="m">
            <div class="modal-header" draggable="true" @dragstart="m.dragStart" @dragend="m.dragEnd">
                <div><slot name="title"></slot></div>
                <button
                    type="button"
                    class="header-close"
                    :title="t('common.close')"
                    :aria-label="t('common.close')"
                    @click.stop="hideModal"
                >
                    <font-awesome-icon :icon="['far', 'window-close']" />
                </button>
            </div>
        </template>
        <div class="modal-body">
            <div id="categories" role="tablist" aria-orientation="vertical">
                <button
                    v-for="(tab, index) of tabs"
                    :id="`panel-tab-${tab.id}`"
                    :key="tab.id"
                    ref="tabRefs"
                    type="button"
                    role="tab"
                    class="category"
                    :class="{ selected: tab.id === selection }"
                    :aria-selected="tab.id === selection"
                    :aria-controls="`panel-panel-${tab.id}`"
                    :tabindex="tab.id === selection ? 0 : -1"
                    @click="setSelection(tab.id)"
                    @keydown="onTabKeydown($event, index)"
                >
                    {{ tab.label }}
                </button>
            </div>
            <!-- tabindex 0: the panel scrolls, and a scrollable region has to be
                 focusable or the keyboard can't reach its contents. -->
            <div
                v-if="activeTab"
                :id="`panel-panel-${activeTab.id}`"
                class="panel-content"
                role="tabpanel"
                :aria-labelledby="`panel-tab-${activeTab.id}`"
                tabindex="0"
            >
                <KeepAlive>
                    <component :is="activeTab.component" v-bind="activeTab.props" @close="hideModal" />
                </KeepAlive>
            </div>
            <div v-else class="panel-content"></div>
        </div>
    </Modal>
</template>

<style scoped lang="scss">


/*
 * Cap the dialog and scroll its content.
 *
 * `.modal-container` in Modal.vue is `position: absolute` with `height: auto`,
 * so a tab taller than the screen simply runs off the bottom of it with no way
 * to reach what's down there. Nothing was ever bounded -- it only went
 * unnoticed while every tab happened to be short. Capping here rather than in
 * Modal.vue keeps the change to dialogs that are actually panel-and-tabs.
 *
 * 75vh rather than 100vh because the dialog is draggable and usually isn't
 * flush with the top of the window.
 */
.modal-body {
    display: flex;
    flex-direction: row;
    max-height: 75vh;

    /*
     * Keep the frame still between tabs. Tab content ranges from a couple of
     * toggles (Trackers, ~485px) to a full character sheet (~1000px), and
     * because the dialog is `width: auto` it used to resize and re-centre
     * under the cursor every time you switched. A floor means only the tall
     * tabs move it, and only outwards.
     */
    min-width: min(46rem, 90vw);
}

* {
    box-sizing: border-box;
}

#categories {
    width: 7.5em;
    flex: 0 0 7.5em;
    display: flex;
    flex-direction: column;
    background-color: rgba(0, 0, 0, 0);
    border-right: solid 1px var(--pa-accent);
    /* Long tab lists scroll on their own rather than stretching the dialog. */
    overflow-y: auto;
}

.panel-content {
    display: flex;
    flex-direction: column;

    flex: 1 1 auto;
    /* Without min-height:0 a flex child refuses to shrink below its content,
       which silently defeats the overflow below. */
    min-height: 0;
    overflow-y: auto;
}

.category {
    border: none;
    border-bottom: solid 1px var(--pa-accent);
    padding: 5px 10px 5px 5px;
    text-align: right;
    background-color: white;
    color: var(--pa-text);
    font: inherit;
    cursor: pointer;
}

.selected,
.category:hover {
    background-color: var(--pa-accent);
    font-weight: bold;
}

/* The bar marks the selected tab without relying on the green alone, which is
   only ~1.9:1 against white. */
.selected {
    box-shadow: inset -3px 0 0 var(--pa-accent-ink);
}

:deep() {
    @layer base-modals {
        .panel {
            background-color: white;
            padding: 1em;
            display: grid;
            grid-template-columns: [setting] 1fr [value] 1fr [end];
            /* align-items: center; */
            align-content: start;
            min-height: 10em;

            button {
                padding: 6px 12px;
                border: 1px solid lightgray;
                border-radius: 0.25em;
                background-color: rgb(235, 235, 228);
            }

            input[type="number"],
            input[type="text"] {
                width: 100%;
            }
        }

        .row {
            display: contents;

            &:first-of-type > * {
                margin-top: 0.5em;
            }

            &:last-of-type > * {
                margin-bottom: 0.5em;
            }

            &:hover > * {
                cursor: pointer;
                text-shadow: 0px 0px 1px black;
            }
        }

        .row > *,
        .panel > *:not(.row) {
            display: flex;
            /* justify-content: center; */
            align-items: center;
            margin: 0.4em 0;
        }

        .smallrow > * {
            padding: 0.2em;
        }

        .header {
            line-height: 0.1em;
            margin: 20px 0 15px;
            font-style: italic;
            overflow: hidden;
            padding: 0.5em;

            &:after {
                position: relative;
                width: 100%;
                border-bottom: 1px solid #000;
                content: "";
                margin-right: -100%;
                margin-left: 10px;
                display: inline-block;
            }
        }

        .danger {
            color: var(--pa-danger-surface);

            &:hover {
                text-shadow: 0px 0px 1px var(--pa-danger-surface);
                cursor: pointer;
            }
        }

        .spanrow {
            grid-column: 1 / end;
            justify-self: normal;
            font-weight: bold;
        }

        input[type="checkbox"] {
            width: 16px;
            height: 23px;
            margin: 0;
            white-space: nowrap;
            display: inline-block;
        }

        .color-picker {
            margin: 0.5em 0 !important;
        }
    }
}
</style>
