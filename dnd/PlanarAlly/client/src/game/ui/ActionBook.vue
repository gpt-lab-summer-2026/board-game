<script setup lang="ts">
/**
 * What the selected character can do, down the left-hand side.
 *
 * The list is built by the ghost, not here. It depends on what the character is
 * holding, what they have prepared and what is left in their pack -- all of
 * which the ghost already reads to resolve a command. A panel that worked it out
 * independently would be a second implementation of the same rules, and the two
 * would disagree the first time either changed.
 *
 * Every entry is literally the command text, so a button press and a typed line
 * take the same path into the game. Nothing here can do anything you could not
 * type, which is what keeps the voice, the console and this panel honest.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { selectedState } from "../systems/selected/state";
import { propertiesState } from "../systems/properties/state";

interface Entry {
    label: string;
    command: string;
    needsTarget: boolean;
    detail: string;
}
interface Group {
    name: string;
    entries: Entry[];
}

const ghost = `${window.location.protocol}//${window.location.hostname}:8770`;
const POS_KEY = "pa-actionbook-pos";

interface Pos {
    left: number;
    top: number;
}

const rootEl = ref<HTMLElement | null>(null);
const viewport = ref({ w: window.innerWidth, h: window.innerHeight });
const pos = ref<Pos | null>(readStoredPos());
let dragFrom: { x: number; y: number; left: number; top: number } | null = null;

function readStoredPos(): Pos | null {
    try {
        const raw = localStorage.getItem(POS_KEY);
        if (raw === null) return null;
        const parsed = JSON.parse(raw) as Pos;
        return typeof parsed.left === "number" && typeof parsed.top === "number" ? parsed : null;
    } catch {
        return null;
    }
}

/**
 * Keep the panel on screen.
 *
 * Clamped when it is *rendered*, not only while it is dragged: a position saved
 * on a 2560px display is off the edge of a 1920px one, and the only control for
 * getting it back would be on the part that is off screen.
 */
function clamp(p: Pos): Pos {
    const width = rootEl.value?.offsetWidth ?? 260;
    const height = rootEl.value?.offsetHeight ?? 320;
    return {
        left: Math.min(Math.max(p.left, 0), Math.max(0, viewport.value.w - width)),
        top: Math.min(Math.max(p.top, 0), Math.max(0, viewport.value.h - height)),
    };
}

const placement = computed(() => {
    if (pos.value === null) return {};
    const safe = clamp(pos.value);
    return { left: `${safe.left}px`, top: `${safe.top}px` };
});

function onDragStart(event: PointerEvent): void {
    const box = rootEl.value?.getBoundingClientRect();
    if (box === undefined) return;
    dragFrom = { x: event.clientX, y: event.clientY, left: box.left, top: box.top };
    (event.target as HTMLElement).setPointerCapture(event.pointerId);
    event.preventDefault();
}

function onDragMove(event: PointerEvent): void {
    if (dragFrom === null) return;
    pos.value = clamp({
        left: dragFrom.left + (event.clientX - dragFrom.x),
        top: dragFrom.top + (event.clientY - dragFrom.y),
    });
}

function onDragEnd(): void {
    dragFrom = null;
    if (pos.value !== null) localStorage.setItem(POS_KEY, JSON.stringify(pos.value));
}

function resetPosition(): void {
    pos.value = null;
    localStorage.removeItem(POS_KEY);
}

function onResize(): void {
    viewport.value = { w: window.innerWidth, h: window.innerHeight };
    if (pos.value !== null) pos.value = clamp(pos.value);
}

onMounted(() => window.addEventListener("resize", onResize));
onBeforeUnmount(() => window.removeEventListener("resize", onResize));

const open = ref(true);
const groups = ref<Group[]>([]);
const character = ref<string | null>(null);
const target = ref("");
const busy = ref(false);
const lastResult = ref<string[]>([]);

/** The first selected token's name, which is what the list is built for. */
const selectedName = computed(() => {
    const id = [...selectedState.reactive.selected][0];
    if (id === undefined) return null;
    return propertiesState.reactive.data.get(id)?.name ?? null;
});

async function refresh(name: string | null): Promise<void> {
    character.value = name;
    groups.value = [];
    if (name === null) return;
    try {
        const res = await fetch(`${ghost}/actions?character=${encodeURIComponent(name)}`);
        const body = (await res.json()) as { found?: boolean; groups?: Group[] };
        groups.value = body.found === true ? (body.groups ?? []) : [];
    } catch {
        // The ghost being down is a normal state during development; an empty
        // panel says so more usefully than an error box would.
        groups.value = [];
    }
}

watch(selectedName, (name) => void refresh(name), { immediate: true });

function needsMissingTarget(entry: Entry): boolean {
    return entry.needsTarget && target.value.trim() === "";
}

async function run(entry: Entry): Promise<void> {
    if (needsMissingTarget(entry)) return;
    const command = entry.command.replace("{t}", target.value.trim());
    busy.value = true;
    try {
        const res = await fetch(`${ghost}/command`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command, source: "panel" }),
        });
        const body = (await res.json()) as { entries?: { lines?: string[] }[] };
        lastResult.value = body.entries?.[0]?.lines ?? [];
    } catch {
        lastResult.value = ["The ghost did not answer."];
    } finally {
        busy.value = false;
        void refresh(character.value);
    }
}
</script>

<template>
    <div id="action-book" ref="rootEl" :class="{ collapsed: !open, floating: pos !== null }" :style="placement">
        <button class="handle" :title="open ? 'Hide actions' : 'Show actions'" @click="open = !open">
            {{ open ? "‹" : "›" }}
        </button>

        <div v-if="open" class="body">
            <header
                @pointerdown="onDragStart"
                @pointermove="onDragMove"
                @pointerup="onDragEnd"
                @pointercancel="onDragEnd"
            >
                <span class="grip" title="Drag to move">⠿</span>
                <span class="who">{{ character ?? "Select a token" }}</span>
                <button
                    v-if="pos !== null"
                    class="reset"
                    title="Back to the left edge"
                    @pointerdown.stop
                    @click="resetPosition"
                >
                    ⤺
                </button>
            </header>

            <label class="target">
                <span>Target</span>
                <input v-model="target" type="text" placeholder="name" spellcheck="false" />
            </label>

            <div v-for="group of groups" :key="group.name" class="group">
                <h4>{{ group.name }}</h4>
                <button
                    v-for="entry of group.entries"
                    :key="entry.label"
                    type="button"
                    class="entry"
                    :class="{ blocked: needsMissingTarget(entry) }"
                    :disabled="busy"
                    :title="needsMissingTarget(entry) ? 'Name a target first' : entry.command.replace('{t}', target || '…')"
                    @click="run(entry)"
                >
                    <span class="label">{{ entry.label }}</span>
                    <span v-if="entry.detail" class="detail">{{ entry.detail }}</span>
                </button>
            </div>

            <p v-if="character && groups.length === 0" class="muted">
                Nothing to show — the ghost may be offline, or this token has no sheet.
            </p>

            <ul v-if="lastResult.length" class="result">
                <li v-for="(line, i) of lastResult" :key="i">{{ line }}</li>
            </ul>
        </div>
    </div>
</template>

<style scoped lang="scss">
#action-book {
    position: absolute;
    top: 6rem;
    left: 0;
    z-index: 19;

    // Once dragged it is positioned explicitly, and the rounded left edge that
    // made sense against the window edge no longer does.
    &.floating .body {
        border-radius: 8px;
    }

    display: flex;
    align-items: flex-start;

    // The board is the thing being looked at; this must never grow so tall that
    // it covers it, hence a hard cap and its own scroll.
    max-height: calc(100vh - 12rem);

    .handle {
        width: 1.1rem;
        padding: 0.6rem 0;
        border: none;
        border-radius: 0 6px 6px 0;
        background-color: rgba(20, 20, 24, 0.82);
        color: white;
        cursor: pointer;
    }

    .body {
        width: 15rem;
        max-height: calc(100vh - 12rem);
        overflow-y: auto;
        padding: 0.5rem 0.6rem;
        order: -1;
        background-color: rgba(20, 20, 24, 0.86);
        border-radius: 0 8px 8px 0;
        color: white;
        font-size: 0.75rem;
    }

    header {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        cursor: grab;
        touch-action: none;

        &:active {
            cursor: grabbing;
        }

        .grip {
            opacity: 0.5;
        }

        .who {
            flex: 1;
            font-weight: 700;
            font-size: 0.9rem;
        }

        .reset {
            border: none;
            background: none;
            color: inherit;
            cursor: pointer;
            opacity: 0.7;
        }
    }

    .target {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        margin: 0.4rem 0 0.6rem;

        input {
            flex: 1;
            min-width: 0;
            padding: 0.15rem 0.3rem;
            border: solid 1px rgba(255, 255, 255, 0.3);
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.08);
            color: inherit;
        }
    }

    h4 {
        margin: 0.6rem 0 0.25rem;
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        opacity: 0.65;
    }

    .entry {
        display: flex;
        justify-content: space-between;
        gap: 0.4rem;
        width: 100%;
        margin-bottom: 0.15rem;
        padding: 0.25rem 0.4rem;
        border: solid 1px rgba(255, 255, 255, 0.18);
        border-radius: 5px;
        background: rgba(255, 255, 255, 0.06);
        color: inherit;
        text-align: left;
        cursor: pointer;

        &:hover:not(:disabled) {
            background: rgba(130, 200, 160, 0.25);
        }

        // Dimmed rather than hidden: knowing the option exists and needs a
        // target is more useful than the button disappearing.
        &.blocked {
            opacity: 0.45;
        }

        .detail {
            opacity: 0.6;
            white-space: nowrap;
        }
    }

    .muted {
        opacity: 0.6;
    }

    .result {
        margin: 0.6rem 0 0;
        padding-left: 0.9rem;
        opacity: 0.85;
    }
}
</style>
