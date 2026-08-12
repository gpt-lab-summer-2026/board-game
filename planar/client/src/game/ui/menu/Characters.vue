<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";

import { getImageSrcFromHash } from "../../../assets/utils";
import { useModal } from "../../../core/plugins/modals/plugin";
import { DropAssetInfo } from "../../dropAsset";
import { setCenterPosition } from "../../position";
import { characterSystem } from "../../systems/characters";
import { sendRemoveCharacter } from "../../systems/characters/emits";
import type { CharacterId } from "../../systems/characters/models";
import { characterState } from "../../systems/characters/state";
import { gameState } from "../../systems/game/state";
import { selectedSystem } from "../../systems/selected";
import { uiSystem } from "../../systems/ui";
import { activeShapeStore } from "../../../store/activeShape";

const { t } = useI18n();

const modals = useModal();

const characterId = ref<CharacterId | undefined>(undefined);

const charAsset = computed(() => {
    if (characterId.value === undefined) return undefined;

    const char = characterState.readonly.characters.get(characterId.value);
    if (char === undefined) return undefined;

    return { assetHash: char.assetHash, assetId: char.assetId };
});

function dragStart(event: DragEvent): void {
    if (!gameState.isDmOrFake.value) return;
    if (event.dataTransfer === null) return;
    if (charAsset.value === undefined) return;
    const { assetHash, assetId } = charAsset.value;

    event.dataTransfer.setDragImage(new Image(), 0, 0);
    event.dataTransfer.setData(
        "text/plain",
        JSON.stringify({ assetHash, assetId, characterId: characterId.value } as DropAssetInfo),
    );

    characterId.value = undefined;
}

function focus(charId: CharacterId): void {
    const shape = characterSystem.getShape(charId);
    if (shape) setCenterPosition(shape.center);
}

/**
 * Jump straight to a character's sheet.
 *
 * Levelling itself lives in the character-sheet mod, and duplicating the
 * rules here so a menu arrow could apply them would be two implementations
 * of the same thing. So the arrow does what a shortcut should: selects the
 * token, opens its dialog, and lands on the Character tab.
 */
function openSheet(charId: CharacterId): void {
    const shape = characterSystem.getShape(charId);
    if (shape === undefined) return;
    setCenterPosition(shape.center);
    selectedSystem.set(shape.id);
    // "SCS" is the char-sheet mod's tab id. If the mod is not loaded the
    // dialog simply falls back to its first tab, which is fine.
    uiSystem.setActiveShapeTab("SCS");
    activeShapeStore.setShowEditDialog(true);
}

async function remove(charId: CharacterId): Promise<void> {
    const name = characterState.readonly.characters.get(charId)?.name ?? "??";
    const confirmed = await modals.confirm("Character Removal", `Are you sure you wish to remove character ${name}?`);
    if (confirmed ?? false) {
        sendRemoveCharacter(charId);
    }
}
</script>

<template>
    <button class="menu-accordion">{{ t("game.ui.menu.MenuBar.characters") }}</button>
    <div class="menu-accordion-panel">
        <div class="menu-accordion-subpanel" style="position: relative">
            <div
                v-for="char in characterState.reactive.characterIds"
                :key="char"
                class="character"
                :draggable="gameState.isDmOrFake.value"
                @dragstart="dragStart"
                @mouseover="characterId = char"
                @mouseout="characterId = undefined"
                @click="focus(char)"
            >
                <span class="char-name">
                    {{ characterState.readonly.characters.get(char)?.name ?? "??" }}
                </span>
                <button
                    type="button"
                    class="level"
                    title="Open the character sheet to level up"
                    aria-label="Open character sheet"
                    @click.stop="openSheet(char)"
                >
                    <font-awesome-icon icon="arrow-up" />
                </button>
                <button type="button" class="remove" title="Remove character" @click.stop="remove(char)">
                    X
                </button>
            </div>
            <div v-if="!characterState.reactive.characterIds.size">
                {{ t("game.ui.menu.MenuBar.no_characters") }}
            </div>
            <div v-if="charAsset !== undefined" class="preview">
                <img class="asset-preview-image" :src="getImageSrcFromHash(charAsset.assetHash)" alt="" />
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
.preview {
    position: fixed;
    left: 200px;
    top: 0;
}

.asset-preview-image {
    width: 100%;
    max-width: 250px;
}

.character {
    display: flex;
    align-items: center;
    gap: 0.4rem;

    &:hover {
        cursor: pointer;
    }

    .char-name {
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    /* Was an absolutely positioned <span>; a control that removes a
       character should be a button and reachable by keyboard. */
    .level,
    .remove {
        flex: 0 0 auto;
        padding: 0.1rem 0.35rem;
        border: solid 1px transparent;
        border-radius: var(--pa-radius-sm);
        background: none;
        color: inherit;
        font: inherit;
        cursor: pointer;

        &:hover {
            background-color: rgb(0 0 0 / 12%);
            font-weight: 700;
        }
    }

    .level:hover {
        color: var(--pa-accent-ink);
    }
}
</style>
