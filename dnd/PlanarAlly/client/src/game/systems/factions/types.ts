import type { GlobalId } from "../../../core/id";

export type FactionId = string;

/**
 * How a faction stands towards the player party.
 *
 * This is deliberately a property of the faction rather than of each token, so
 * that turning a whole warband hostile is one edit instead of six. The one case
 * that is genuinely per-token -- a neutral that a player just attacked -- is the
 * `provoked` set below, not a disposition of its own: the goblin camp does not
 * become hostile because you shot one merchant.
 */
export type Disposition = "party" | "friendly" | "neutral" | "hostile";

export interface Faction {
    id: FactionId;
    name: string;
    /** Used for the token outline and the panel swatch. */
    colour: string;
    disposition: Disposition;
}

export interface FactionData {
    version: 1;
    factions: Faction[];
    /** Shape -> faction. A shape with no entry is unaligned and hostile to nobody. */
    members: Record<GlobalId, FactionId>;
    /**
     * Shapes that are temporarily hostile to the party regardless of their
     * faction's disposition. Cleared by hand from the panel -- a truce is a
     * table decision, not something that should time out on its own.
     */
    provoked: GlobalId[];
}

export const DISPOSITIONS: Disposition[] = ["party", "friendly", "neutral", "hostile"];

export const DISPOSITION_COLOURS: Record<Disposition, string> = {
    party: "#2f7d32",
    friendly: "#2f6f7d",
    neutral: "#8a7d2f",
    hostile: "#a32f2f",
};

/**
 * The factions a fresh room starts with.
 *
 * Seeded rather than left empty because an empty faction panel gives you nothing
 * to drag tokens onto, and every table has at least these three sides.
 */
export function defaultFactionData(): FactionData {
    return {
        version: 1,
        factions: [
            { id: "party", name: "The Party", colour: DISPOSITION_COLOURS.party, disposition: "party" },
            { id: "enemies", name: "Enemies", colour: DISPOSITION_COLOURS.hostile, disposition: "hostile" },
            { id: "neutrals", name: "Neutrals", colour: DISPOSITION_COLOURS.neutral, disposition: "neutral" },
        ],
        members: {},
        provoked: [],
    };
}
