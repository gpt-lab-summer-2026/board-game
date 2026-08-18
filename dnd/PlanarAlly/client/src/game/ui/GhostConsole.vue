<script setup lang="ts">
/*
 * The voice/command console, inside the game.
 *
 * It used to be a separate page on the ghost's own port, which is unusable once
 * the board is projected -- you cannot alt-tab away from the thing everyone is
 * looking at. So the same endpoints are driven from a panel here.
 *
 * The ghost is a separate process on :8770, so every call is cross-origin (the
 * console sets permissive CORS headers for exactly this). The host is derived
 * from the page rather than hardcoded to localhost, so a projector or a laptop
 * opening the game over the LAN talks to the same Pi that served the page.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { uiState } from "../systems/ui/state";
import { uiSystem } from "../systems/ui";

interface LogEntry {
    n: number;
    source: string;
    command: string;
    intent: { action: string; actor?: string; target?: string; kind?: string; bias?: string } | null;
    ok: boolean;
    awaiting: boolean;
    lines: string[];
}

const STORAGE_KEY = "pa-ghost-url";
const POS_KEY = "pa-ghost-pos";

function defaultGhostUrl(): string {
    return `${window.location.protocol}//${window.location.hostname}:8770`;
}

const ghostUrl = ref(localStorage.getItem(STORAGE_KEY) ?? defaultGhostUrl());
watch(ghostUrl, (value) => localStorage.setItem(STORAGE_KEY, value.replace(/\/+$/, "")));

const visible = computed(() => uiState.reactive.showGhostConsole);
const command = ref("");
const entries = ref<LogEntry[]>([]);
const online = ref<boolean | null>(null);
const busy = ref(false);
const showSettings = ref(false);
const inputEl = ref<HTMLInputElement | null>(null);

// ---- position --------------------------------------------------------------
//
// It was pinned bottom-right, which is exactly where the tool bar and the
// Build/Play switch live -- so it covered the controls you need while running
// a turn. Draggable by its header, and remembered, because where it should
// sit depends on the projector and the map, not on a guess made here.

interface Pos {
    left: number;
    top: number;
}

function loadPos(): Pos | null {
    try {
        const raw = localStorage.getItem(POS_KEY);
        return raw === null ? null : (JSON.parse(raw) as Pos);
    } catch {
        return null;
    }
}

const pos = ref<Pos | null>(loadPos());

// Bumped on resize so the clamp below recomputes. A stored position is only
// valid for the window it was saved in, and windows change between
// sessions and monitors.
const viewport = ref({ w: window.innerWidth, h: window.innerHeight });
function onResize(): void {
    viewport.value = { w: window.innerWidth, h: window.innerHeight };
}

/**
 * Keep the whole panel on screen.
 *
 * Not "keep a handle visible": a position restored from a wider window
 * should come all the way back, and there is no case where leaving two
 * thirds of the panel past the edge is what someone wanted.
 */
function clampPos(p: Pos): Pos {
    const width = rootEl.value?.offsetWidth ?? 480;
    const height = rootEl.value?.offsetHeight ?? 320;
    return {
        left: Math.min(Math.max(p.left, 0), Math.max(0, viewport.value.w - width)),
        top: Math.min(Math.max(p.top, 0), Math.max(0, viewport.value.h - height)),
    };
}

const style = computed(() => {
    if (pos.value === null) {
        // Default clear of the tool bar (bottom-right) and the menu (left).
        return { top: '6rem', right: '1.5rem' };
    }
    // Clamp on *render*, not only while dragging. A position saved on a
    // 2560px-wide window put the panel at left:2068 on a 1920px one --
    // completely off-screen, with the reset button stranded on the panel
    // itself, so there was no way back short of clearing localStorage.
    const safe = clampPos(pos.value);
    return { left: `${safe.left}px`, top: `${safe.top}px`, right: 'auto' };
});

let dragFrom: { x: number; y: number; left: number; top: number } | null = null;
const rootEl = ref<HTMLDivElement | null>(null);

function startDrag(event: PointerEvent): void {
    if (rootEl.value === null) return;
    // Buttons inside the header must stay clickable.
    if ((event.target as HTMLElement).closest('button') !== null) return;
    const box = rootEl.value.getBoundingClientRect();
    dragFrom = { x: event.clientX, y: event.clientY, left: box.left, top: box.top };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function onDrag(event: PointerEvent): void {
    if (dragFrom === null) return;
    // Same clamp as the render path, so what you drag to is what gets
    // stored and what comes back next session.
    pos.value = clampPos({
        left: dragFrom.left + event.clientX - dragFrom.x,
        top: dragFrom.top + event.clientY - dragFrom.y,
    });
}

function endDrag(): void {
    if (dragFrom === null) return;
    dragFrom = null;
    if (pos.value !== null) localStorage.setItem(POS_KEY, JSON.stringify(pos.value));
}

function resetPos(): void {
    pos.value = null;
    localStorage.removeItem(POS_KEY);
}


const awaiting = computed(() => entries.value.find((e) => e.awaiting));

let timer: number | undefined;

async function refresh(): Promise<void> {
    try {
        const r = await fetch(`${ghostUrl.value}/log`);
        entries.value = ((await r.json()) as { entries: LogEntry[] }).entries ?? [];
        online.value = true;
    } catch {
        // The ghost may simply not be running; that is a normal state, not an
        // error worth shouting about on every poll.
        online.value = false;
    }
}

async function send(text: string, source = "text"): Promise<void> {
    const trimmed = text.trim();
    if (trimmed.length === 0 || busy.value) return;
    busy.value = true;
    command.value = "";
    try {
        await fetch(`${ghostUrl.value}/command`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command: trimmed, source }),
        });
        await refresh();
    } catch {
        online.value = false;
    } finally {
        busy.value = false;
        inputEl.value?.focus();
    }
}

function describeIntent(i: LogEntry["intent"]): string {
    if (i === null) return "not understood";
    const bits: string[] = [i.action];
    if (i.kind) bits.push(i.kind);
    if (i.actor) bits.push(`actor=${i.actor}`);
    if (i.target) bits.push(`target=${i.target}`);
    if (i.bias && i.bias !== "normal") bits.push(i.bias);
    return bits.join("  ");
}

// ---- speech ----------------------------------------------------------------
// A stand-in until whisper feeds the same endpoint. Dual input is deliberate:
// a noisy room or a tired player must never be a reason the demo stalls.

const SR = (window as unknown as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown });
const recogniser = (SR.SpeechRecognition ?? SR.webkitSpeechRecognition) as
    | (new () => {
          lang: string;
          interimResults: boolean;
          continuous: boolean;
          start: () => void;
          stop: () => void;
          addEventListener: (t: string, cb: (e: never) => void) => void;
      })
    | undefined;

const listening = ref(false);
let rec: InstanceType<NonNullable<typeof recogniser>> | undefined;

function toggleMic(): void {
    if (rec === undefined) return;
    listening.value ? rec.stop() : rec.start();
}

onMounted(() => {
    if (recogniser !== undefined) {
        rec = new recogniser();
        rec.lang = "en-GB";
        rec.interimResults = false;
        rec.continuous = false;
        rec.addEventListener("start", (() => (listening.value = true)) as never);
        rec.addEventListener("end", (() => (listening.value = false)) as never);
        rec.addEventListener("result", ((e: { results: { 0: { 0: { transcript: string } } } }) => {
            void send(e.results[0][0].transcript.trim(), "voice");
        }) as never);
    }
    void refresh();
    timer = window.setInterval(refresh, 4000);
    window.addEventListener("resize", onResize);
});

onBeforeUnmount(() => {
    if (timer !== undefined) window.clearInterval(timer);
    window.removeEventListener("resize", onResize);
});

watch(visible, async (open) => {
    if (open) {
        await refresh();
        // The point of the panel is typing into it; make that possible without
        // an extra click.
        setTimeout(() => inputEl.value?.focus(), 0);
    }
});
</script>

<template>
    <div v-if="visible" id="ghost-console" ref="rootEl" :style="style">
        <header
            class="draggable"
            @pointerdown="startDrag"
            @pointermove="onDrag"
            @pointerup="endDrag"
            @pointercancel="endDrag"
        >
            <span class="title">Ghost console</span>
            <span class="dot" :class="{ up: online === true, down: online === false }" :title="
                online === false ? 'Cannot reach the ghost' : online === true ? 'Connected' : 'Connecting'
            "></span>
            <button type="button" title="Reset position" @click="resetPos">
                <font-awesome-icon icon="arrows-alt" />
            </button>
            <button type="button" title="Connection settings" @click="showSettings = !showSettings">
                <font-awesome-icon icon="cog" />
            </button>
            <button type="button" title="Close" @click="uiSystem.setGhostConsole(false)">
                <font-awesome-icon :icon="['far', 'window-close']" />
            </button>
        </header>

        <div v-if="showSettings" class="settings">
            <label for="ghost-url">Ghost address</label>
            <input id="ghost-url" v-model="ghostUrl" type="text" spellcheck="false" />
            <p class="hint">
                The ghost runs as its own process:
                <code>server/.venv/bin/python -m ghost --host 0.0.0.0</code>
            </p>
        </div>

        <p v-if="online === false" class="offline">
            No ghost at <code>{{ ghostUrl }}</code>. Start it, or change the address above.
        </p>

        <div v-if="awaiting" class="ask">
            <div>{{ awaiting.lines[awaiting.lines.length - 1] }}</div>
            <div class="row">
                <button type="button" @click="send('yes')">Yes</button>
                <button type="button" class="ghost" @click="send('no')">No</button>
            </div>
        </div>

        <div class="log" aria-live="polite">
            <p v-if="entries.length === 0" class="empty">
                Nothing yet. Try <code>help</code>, or <code>measure from x to y</code>.
            </p>
            <div v-for="e of [...entries].reverse()" :key="e.n" class="entry"
                 :class="e.awaiting ? 'ask' : e.ok ? 'ok' : 'bad'">
                <div class="head">
                    <span class="n">#{{ e.n }}</span>
                    <span class="cmd">{{ e.command }}</span>
                    <span class="src">{{ e.source }}</span>
                </div>
                <!-- Intent and result stay separate: after a surprising turn the
                     question is whether it misheard you or misapplied the rules. -->
                <div class="intent">{{ describeIntent(e.intent) }}</div>
                <div class="result"><div v-for="(l, i) of e.lines" :key="i">{{ l }}</div></div>
            </div>
        </div>

        <form class="bar" @submit.prevent="send(command)">
            <label for="ghost-cmd" class="sr-only">Command</label>
            <input id="ghost-cmd" ref="inputEl" v-model="command" type="text" autocomplete="off"
                   placeholder="elf ranged attack on goblin" />
            <button type="submit" :disabled="busy">Run</button>
            <button v-if="recogniser" type="button" class="ghost" :aria-pressed="listening"
                    :class="{ listening }" title="Dictate" @click="toggleMic">
                <font-awesome-icon icon="microphone" />
            </button>
        </form>
    </div>
</template>

<style scoped lang="scss">
#ghost-console {
    pointer-events: auto;
    /* fixed, not absolute: the panel is dragged in viewport coordinates and
       must not be shifted by the UI grid it happens to sit in. */
    position: fixed;
    z-index: 20;

    display: flex;
    flex-direction: column;
    width: min(30rem, 92vw);
    max-height: min(32rem, 70vh);

    background-color: var(--pa-surface);
    color: var(--pa-text);
    border: solid 1px var(--pa-border);
    border-radius: var(--pa-radius-md);
    box-shadow: var(--pa-shadow-lg);
    overflow: hidden;

    header.draggable {
        cursor: move;
        touch-action: none;
    }

    header {
        display: flex;
        align-items: center;
        gap: var(--pa-space-2);
        padding: var(--pa-space-2) var(--pa-space-3);
        background-color: var(--pa-secondary);
        color: var(--pa-text-inverse);

        .title {
            flex: 1;
            font-weight: 700;
        }

        > button {
            display: flex;
            padding: 0.2rem 0.35rem;
            border: none;
            border-radius: var(--pa-radius-sm);
            background: none;
            color: inherit;
            cursor: pointer;

            &:hover {
                background-color: rgb(255 255 255 / 20%);
            }
        }
    }

    .dot {
        width: 0.6rem;
        height: 0.6rem;
        border-radius: 50%;
        background-color: var(--pa-text-muted);

        &.up { background-color: #39ff14; }
        &.down { background-color: var(--pa-danger-surface); }
    }

    .settings,
    .offline {
        padding: var(--pa-space-2) var(--pa-space-3);
        border-bottom: solid 1px var(--pa-border);
        font-size: 0.85rem;

        input {
            width: 100%;
            padding: 0.3rem 0.5rem;
            font: inherit;
        }
    }

    .offline { color: var(--pa-danger); }
    .hint { margin: 0.4rem 0 0; color: var(--pa-text-muted); }

    .ask {
        padding: var(--pa-space-2) var(--pa-space-3);
        border-left: solid 4px var(--pa-warning);
        background-color: var(--pa-surface-raised);

        .row {
            display: flex;
            gap: var(--pa-space-2);
            margin-top: var(--pa-space-2);
        }
    }

    .log {
        flex: 1 1 auto;
        min-height: 0;
        overflow-y: auto;
        padding: var(--pa-space-2) var(--pa-space-3);
        display: flex;
        flex-direction: column;
        gap: var(--pa-space-2);
    }

    .empty { color: var(--pa-text-muted); font-style: italic; margin: 0; }

    .entry {
        border-left: solid 3px var(--pa-border-strong);
        padding-left: var(--pa-space-2);
        font-size: 0.9rem;

        &.ok { border-left-color: var(--pa-accent-ink); }
        &.bad { border-left-color: var(--pa-danger); }
        &.ask { border-left-color: var(--pa-warning); }

        .head { display: flex; gap: var(--pa-space-2); align-items: baseline; flex-wrap: wrap; }
        .n { color: var(--pa-text-muted); font-size: 0.75rem; font-variant-numeric: tabular-nums; }
        .cmd { font-weight: 700; }
        .src {
            font-size: 0.65rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--pa-text-muted);
            border: solid 1px var(--pa-border);
            border-radius: 999px;
            padding: 0 0.35rem;
        }
        .intent { color: var(--pa-text-muted); font-family: ui-monospace, monospace; font-size: 0.78rem; }
    }

    .bar {
        display: flex;
        gap: var(--pa-space-2);
        padding: var(--pa-space-2) var(--pa-space-3);
        border-top: solid 1px var(--pa-border);

        input {
            flex: 1;
            padding: 0.45rem 0.6rem;
            font: inherit;
            border: solid 1px var(--pa-border-strong);
            border-radius: var(--pa-radius-sm);
        }
    }

    button {
        padding: 0.45rem 0.8rem;
        border: solid 1px var(--pa-secondary);
        border-radius: var(--pa-radius-sm);
        background-color: var(--pa-secondary);
        color: var(--pa-text-inverse);
        font: inherit;
        cursor: pointer;

        &.ghost { background: none; color: var(--pa-text); }
        &.listening { background-color: var(--pa-danger); border-color: var(--pa-danger); color: #fff; }
        &:disabled { opacity: 0.5; cursor: default; }
    }

    .sr-only {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip-path: inset(50%);
    }
}
</style>
