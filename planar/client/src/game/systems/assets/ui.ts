import type { AssetEntryId } from "../../../assets/models";

import { assetGameState, persistDockedPreference } from "./state";

function openAssetManager(): void {
    assetGameState.mutableReactive.managerOpen = true;
}

export function closeAssetManager(): void {
    if (assetGameState.raw.managerOpen) {
        assetGameState.mutableReactive.managerOpen = false;
        assetGameState.mutableReactive.draggingToBoard = false;
        if (assetGameState.raw.picker !== null) {
            assetGameState.raw.picker(null);
        }
    }
}

export function setAssetManagerDocked(docked: boolean): void {
    assetGameState.mutableReactive.managerDocked = docked;
    persistDockedPreference(docked);
}

export function toggleAssetManagerDocked(): void {
    setAssetManagerDocked(!assetGameState.raw.managerDocked);
}

export function toggleAssetManager(): void {
    if (assetGameState.raw.managerOpen) {
        closeAssetManager();
    } else {
        openAssetManager();
    }
}

export async function pickAsset(): Promise<AssetEntryId | null> {
    openAssetManager();
    return new Promise((resolve) => {
        assetGameState.mutableReactive.picker = resolve;
    });
}
