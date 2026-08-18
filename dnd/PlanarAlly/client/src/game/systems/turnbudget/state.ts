import { buildState } from "../../../core/systems/state";

import type { TurnBudget } from "./types";
import { defaultTurnBudget } from "./types";

interface TurnBudgetState {
    data: TurnBudget;
    /** False until the room's DataBlock has come back from the server. */
    loaded: boolean;
}

const state = buildState<TurnBudgetState>({
    data: defaultTurnBudget(),
    loaded: false,
});

export const turnBudgetState = {
    ...state,
};
