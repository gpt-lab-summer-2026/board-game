/**
 * The action economy, alongside PlanarAlly's initiative counters.
 *
 * PA already tracks round and turn and ticks its own initiative effects, so none
 * of that is duplicated here; what it has no concept of is a creature having
 * spent its action. That gap is why "you would provoke an opportunity attack" or
 * "you have already moved 25 of your 30 feet" cannot be answered without this.
 *
 * A room DataBlock rather than local state, for the same reason as Sides: the
 * ghost reads DataBlocks over the same socket the browser uses, so the voice
 * layer can ask what is left of a turn without a parallel source of truth.
 */
import type { GlobalId } from "../../../core/id";
import { registerSystem } from "../../../core/systems";
import type { System } from "../../../core/systems/models";
import { getOrLoadDataBlock } from "../../dataBlock";
import type { DataBlock } from "../../dataBlock/db";

import { turnBudgetState } from "./state";
import type { BudgetKind, TurnBudget } from "./types";
import { defaultTurnBudget } from "./types";

const { mutableReactive: $ } = turnBudgetState;

const DB_REPR = { source: "pa-turnbudget", category: "room", name: "budget" } as const;

let block: DataBlock<never, TurnBudget> | undefined;

class TurnBudgetSystem implements System {
    clear(): void {
        block = undefined;
        $.data = defaultTurnBudget();
        $.loaded = false;
    }

    async load(): Promise<void> {
        if (block !== undefined) return;
        block = await getOrLoadDataBlock<never, TurnBudget>(DB_REPR, {
            createOnServer: true,
            defaultData: defaultTurnBudget,
            updateCallback: (data) => {
                $.data = data;
                $.loaded = true;
            },
        });
        if (block !== undefined) {
            $.data = block.data;
            $.loaded = true;
        }
    }

    private save(): void {
        if (block === undefined) {
            // Called before load() finished. Dropping it here is what made the
            // first turn-sync vanish, so retry once the block arrives instead.
            void this.load().then(() => {
                if (block === undefined) return;
                block.updateData($.data as TurnBudget);
                block.sync();
            });
            return;
        }
        block.updateData($.data as TurnBudget);
        block.sync();
    }

    /**
     * Point the budget at the turn that is now current, clearing the spends if
     * it has actually changed.
     *
     * Idempotent on purpose: it is called from a watcher on the initiative
     * counters, which fires on every client and can fire more than once for the
     * same turn. Only a real change writes, so a re-render does not wipe an
     * action the DM has just marked as spent.
     */
    syncToTurn(round: number, turn: number, active: GlobalId | null): void {
        const d = $.data;
        if (d.round === round && d.turn === turn && d.active === active) return;

        // Bank what the outgoing creature had spent before overwriting it, and
        // give the incoming one back whatever it had already spent this round.
        // Blanking unconditionally -- which is what this did -- meant "previous
        // turn, next turn" refunded a whole turn's economy.
        const spent = { ...(d.spent ?? {}) };
        if (d.active !== null) {
            spent[d.active] = {
                round: d.round,
                action: d.action,
                bonus: d.bonus,
                movementUsed: d.movementUsed,
                speedBonus: d.speedBonus ?? 0,
            };
        }
        const restored = active === null ? undefined : spent[active];
        const carry = restored !== undefined && restored.round === round;

        $.data = {
            ...d,
            round,
            turn,
            active,
            action: carry ? restored.action : false,
            bonus: carry ? restored.bonus : false,
            movementUsed: carry ? restored.movementUsed : 0,
            speed: d.speed,
            speedBonus: carry ? restored.speedBonus : 0,
            spent,
            // Reactions deliberately survive: they refresh at the start of the
            // creature's *own* turn, which is handled below, not whenever any
            // turn ends. Only on a turn this creature has not already had --
            // revisiting its turn must not refund the reaction either.
            reactions:
                active === null || carry ? d.reactions : dropReaction(d.reactions, active),
        };
        this.save();
    }

    /**
     * Mirror the active creature's live spends into `spent`.
     *
     * Called by every mutator, because `syncToTurn` banks on the way out and
     * that is one moment too late: a spend made after the last sync would be
     * captured, but only if nothing else overwrote `$.data` first. Keeping the
     * bank current at every write makes the restore path independent of
     * ordering.
     */
    private bank(next: TurnBudget): TurnBudget {
        if (next.active === null) return next;
        return {
            ...next,
            spent: {
                ...(next.spent ?? {}),
                [next.active]: {
                    round: next.round,
                    action: next.action,
                    bonus: next.bonus,
                    movementUsed: next.movementUsed,
                    speedBonus: next.speedBonus ?? 0,
                },
            },
        };
    }

    spend(kind: BudgetKind, spent = true): void {
        $.data = this.bank({ ...$.data, [kind]: spent });
        this.save();
    }

    spendMovement(feet: number): void {
        $.data = this.bank({ ...$.data, movementUsed: Math.max(0, $.data.movementUsed + feet) });
        this.save();
    }

    setMovement(feet: number): void {
        $.data = this.bank({ ...$.data, movementUsed: Math.max(0, feet) });
        this.save();
    }

    setSpeed(feet: number): void {
        $.data = this.bank({ ...$.data, speed: Math.max(0, feet) });
        this.save();
    }

    useReaction(shape: GlobalId): void {
        $.data = { ...$.data, reactions: { ...$.data.reactions, [shape]: $.data.round } };
        this.save();
    }

    /** True when this creature still has its reaction for the current round. */
    hasReaction(shape: GlobalId): boolean {
        const used = $.data.reactions[shape];
        return used === undefined || used < $.data.round;
    }
}

/** A creature's reaction comes back when its own turn starts. */
function dropReaction(reactions: Record<GlobalId, number>, active: GlobalId): Record<GlobalId, number> {
    if (reactions[active] === undefined) return reactions;
    const { [active]: _refreshed, ...rest } = reactions;
    return rest;
}

export const turnBudgetSystem = new TurnBudgetSystem();
registerSystem("turnbudget", turnBudgetSystem, false, turnBudgetState);
