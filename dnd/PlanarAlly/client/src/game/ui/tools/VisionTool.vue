<script setup lang="ts">
import { computed } from "vue";

import { getImageSrcFromHash } from "../../../assets/utils";
import type { LocalId } from "../../../core/id";
import { map } from "../../../core/iter";
import { getShape } from "../../id";
import type { IShape } from "../../interfaces/shape";
import type { IAsset } from "../../interfaces/shapes/asset";
import { accessSystem } from "../../systems/access";
import { accessState } from "../../systems/access/state";
import { getProperties } from "../../systems/properties/state";
import { visionTool } from "../../tools/variants/vision";

const selected = visionTool.isActiveTool;

const tokens = computed(() =>
    [...map(accessState.reactive.ownedTokens.get("vision")!, (t) => getShape(t)!)].filter(
        (sh) => !(sh.options.skipDraw ?? false),
    ),
);
const selection = computed(() => {
    const activeTokens = accessState.reactive.activeTokenFilters.get("vision");
    if (activeTokens) return new Set(activeTokens);
    return new Set(accessState.reactive.ownedTokens.get("vision")!);
});

function toggle(token: LocalId): void {
    if (selection.value.has(token)) accessSystem.removeActiveToken(token, "vision");
    else accessSystem.addActiveToken(token, "vision");
}

function getImageSrc(token: IShape): string {
    if (token.type === "assetrect") {
        return getImageSrcFromHash((token as IAsset).assetHash);
    }
    return "";
}
</script>

<template>
    <div v-if="selected" class="tool-detail">
        <p class="hint">Which of your tokens you are seeing through.</p>
        <button
            v-for="token in tokens"
            :key="token.id"
            type="button"
            class="token"
            :class="{ selected: selection.has(token.id) }"
            :aria-pressed="selection.has(token.id)"
            @click="toggle(token.id)"
        >
            <img v-if="getImageSrc(token) !== ''" :src="getImageSrc(token)" width="30px" height="30px" alt="" />
            <span class="name">{{ getProperties(token.id)!.name }}</span>
            <!-- An explicit mark, not just a shade: the two states were only
                 distinguishable by background alpha, and hovering flipped
                 each into the other one's appearance. -->
            <font-awesome-icon class="mark" :icon="selection.has(token.id) ? 'eye' : 'eye-slash'" />
        </button>
        <p v-if="tokens.length === 0" class="hint">You have no tokens with vision access.</p>
    </div>
</template>

<style scoped lang="scss">
.hint {
    margin: 0 0 0.6em;
    font-size: 0.85em;
    color: var(--pa-text-muted);
}

.token {
    width: 100%;
    margin-bottom: 0.5em;
    padding: 0.35em 0.6em;
    display: flex;
    align-items: center;
    gap: 0.5em;

    font: inherit;
    text-align: left;
    cursor: pointer;

    border: solid 2px var(--pa-border-strong);
    border-radius: 1em;
    background-color: var(--pa-surface);
    color: var(--pa-text);

    &:last-of-type {
        margin-bottom: 0;
    }

    /*
     * Hover used to move an unselected token to exactly the selected shade and
     * a selected one back to the unselected shade, so the two states were
     * impossible to tell apart while the mouse was anywhere near them. Hover is
     * now a small nudge in the same direction for both.
     */
    &:hover {
        border-color: var(--pa-accent-ink);
    }

    > .name {
        flex: 1;
    }

    > .mark {
        opacity: 0.35;
    }

    /* Selected differs by fill, border AND icon -- three cues, one of which
       survives being printed or seen without colour. */
    &.selected {
        background-color: var(--pa-accent);
        border-color: var(--pa-accent-ink);
        font-weight: 700;

        > .mark {
            opacity: 1;
        }
    }
}

</style>

<style scoped lang="scss">
.tool-detail {
    display: block;
}
</style>
