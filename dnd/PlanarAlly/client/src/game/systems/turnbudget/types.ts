import type { GlobalId } from "../../../core/id";

/**
 * 5e's action economy: what the creature whose turn it is has spent so far.
 *
 * Only the *active* creature's action and bonus action are tracked, because
 * only the active creature has any. Reactions are the exception -- everyone has
 * one, and it refreshes at the start of their own turn rather than at the end of
 * the round -- so they are kept per shape, stamped with the round they were used
 * in, which is enough to answer "can this creature still take an opportunity
 * attack?" without a second timer.
 */
export interface TurnBudget {
    version: 1;
    /**
     * The turn these spends belong to. When the initiative counters move on,
     * a mismatch here is what tells us to clear rather than carry them over --
     * cheaper and more reliable than trying to catch every way a turn can end.
     */
    round: number;
    turn: number;
    active: GlobalId | null;

    action: boolean;
    bonus: boolean;
    /** Feet of movement already used. */
    movementUsed: number;
    /**
     * The active creature's speed in feet.
     *
     * PlanarAlly has no speed of its own -- it belongs to the character sheet
     * mod -- so it is copied here by whoever knows it (the ghost, when it plans a
     * move) rather than read across a module boundary. 30 until told otherwise,
     * which is the right guess often enough to be a useful default and obviously
     * wrong when it isn't.
     */
    speed: number;
    /**
     * Extra feet granted this turn, by Dash and nothing else so far.
     *
     * Separate from `speed` because it is not a property of the creature, and
     * separate from a negative `movementUsed` because that is clamped at zero --
     * which is why crediting Dash as negative spending silently did nothing
     * whenever the creature had not moved yet. Cleared by `syncToTurn`.
     */
    speedBonus: number;

    /** Shape -> the round in which it last spent its reaction. */
    reactions: Record<GlobalId, number>;
    /**
     * What each creature has already spent this round, so that revisiting a
     * turn does not hand it a fresh action.
     *
     * Without this, stepping back one turn and forward again reset the budget:
     * `syncToTurn` blanks on any change to (round, turn, active), and going
     * back and forth is two such changes. That is a free action, a free bonus
     * action and a full move for anyone who says "previous turn, next turn" --
     * which the ghost made trivially easy to say out loud.
     *
     * Keyed by shape and stamped with the round it belongs to; an entry from an
     * earlier round is ignored rather than restored, so a genuinely new round
     * still starts clean.
     */
    spent: Record<GlobalId, { round: number; action: boolean; bonus: boolean; movementUsed: number; speedBonus: number }>;
}

export type BudgetKind = "action" | "bonus";

export function defaultTurnBudget(): TurnBudget {
    return {
        version: 1,
        round: 0,
        turn: 0,
        active: null,
        action: false,
        bonus: false,
        movementUsed: 0,
        speed: 30,
        speedBonus: 0,
        reactions: {},
        spent: {},
    };
}
