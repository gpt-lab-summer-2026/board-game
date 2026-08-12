<script setup lang="ts">
import { useI18n } from "vue-i18n";

import { assetSystem } from "..";
import { baseAdjust } from "../../core/http";
import { useModal } from "../../core/plugins/modals/plugin";
import { sendCreateFolder } from "../emits";
import { assetState } from "../state";

import { canEdit } from "./access";

const { t } = useI18n();
const modals = useModal();

async function createDirectory(): Promise<void> {
    const currentFolder = assetState.currentFolder.value;
    if (currentFolder === undefined || !canEdit(currentFolder)) return;
    const name = await modals.prompt(t("assetManager.AssetManager.new_folder_name"), "?");
    if (name !== undefined) {
        sendCreateFolder({ name, parent: currentFolder });
    }
}

function prepareUpload(): void {
    if (!canEdit(assetState.currentFolder.value)) return;
    document.getElementById("files")!.click();
}

const upload = async (): Promise<void> => {
    if (!canEdit(assetState.currentFolder.value)) return;
    const files = (document.getElementById("files") as HTMLInputElement).files;
    if (files !== null) await assetSystem.upload(files);
};

async function deleteSelection(): Promise<void> {
    if (!canEdit(assetState.currentFolder.value)) return;
    if (assetState.raw.selected.length === 0) return;
    const result = await modals.confirm(t("assetManager.AssetContextMenu.ask_remove"));
    if (result === true) {
        assetSystem.removeSelection();
    }
}
</script>

<template>
    <!--
        These were bare <img @click> elements: not focusable, not announced as
        controls, and operable only by mouse. An <img> with alt text describes a
        picture; it does not make the picture a button.
    -->
    <div v-show="assetState.reactive.sharedRight !== 'view'" class="asset-actions">
        <input id="files" type="file" multiple hidden @change="upload()" />
        <button
            type="button"
            :title="t('assetManager.AssetManager.create_folder')"
            :aria-label="t('assetManager.AssetManager.create_folder')"
            @click.stop="createDirectory"
        >
            <img :src="baseAdjust('/static/img/assetmanager/create_folder.svg')" alt="" />
        </button>
        <button
            type="button"
            :title="t('assetManager.AssetManager.upload_files')"
            :aria-label="t('assetManager.AssetManager.upload_files')"
            @click.stop="prepareUpload"
        >
            <img :src="baseAdjust('/static/img/assetmanager/add_file.svg')" alt="" />
        </button>
        <button
            type="button"
            :title="t('common.remove')"
            :aria-label="t('common.remove')"
            @click.stop="deleteSelection"
        >
            <img :src="baseAdjust('/static/img/assetmanager/delete_selection.svg')" alt="" />
        </button>
    </div>
</template>

<style scoped lang="scss">
.asset-actions {
    display: flex;
    align-items: center;
    gap: var(--pa-space-1);

    > button {
        display: flex;
        align-items: center;
        justify-content: center;

        padding: var(--pa-space-1);
        border: none;
        border-radius: var(--pa-radius-sm);
        background: none;
        cursor: pointer;

        &:hover {
            background-color: var(--pa-surface-sunken);
        }

        > img {
            height: 100%;
            pointer-events: none;
        }
    }
}
</style>
