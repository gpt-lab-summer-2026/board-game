import type { AssetEntryId } from "../../../assets/models";
import { buildState } from "../../../core/systems/state";

interface ReactiveAssetState {
    managerOpen: boolean;
    // Docked turns the asset browser from a centred modal into a side panel, so
    // the map stays visible and clickable while assets are dragged onto it.
    // Building a scene means placing dozens of assets in a row; a modal that
    // covers the board makes that loop far more tedious than it needs to be.
    managerDocked: boolean;
    shortcuts: AssetEntryId[];

    // True while an asset is being dragged out towards the board. Kept here
    // rather than poked into the DOM so that the board and the panel can both
    // react to it through Vue.
    draggingToBoard: boolean;

    picker: ((value: AssetEntryId | null) => void) | null;
}

// Client-side preference only: it changes nothing anyone else sees, so it is
// not worth a server round-trip or a schema change.
const DOCKED_KEY = "pa-assets-docked";

function loadDockedPreference(): boolean {
    try {
        return localStorage.getItem(DOCKED_KEY) === "true";
    } catch {
        // Private browsing modes can throw on access rather than return null.
        return false;
    }
}

export function persistDockedPreference(docked: boolean): void {
    try {
        localStorage.setItem(DOCKED_KEY, String(docked));
    } catch {
        // Preference is a nicety; failing to remember it must not break the UI.
    }
}

const state = buildState<ReactiveAssetState>({
    managerOpen: false,
    managerDocked: loadDockedPreference(),
    shortcuts: [],

    draggingToBoard: false,

    picker: null,
});

export const assetGameState = {
    ...state,
};
