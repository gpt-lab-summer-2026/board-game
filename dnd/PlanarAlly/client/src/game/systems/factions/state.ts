import { buildState } from "../../../core/systems/state";

import type { FactionData } from "./types";
import { defaultFactionData } from "./types";

interface FactionState {
    data: FactionData;
    /** False until the room's DataBlock has come back from the server. */
    loaded: boolean;
}

const state = buildState<FactionState>({
    data: defaultFactionData(),
    loaded: false,
});

export const factionState = {
    ...state,
};
