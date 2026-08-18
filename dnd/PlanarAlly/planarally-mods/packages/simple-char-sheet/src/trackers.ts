// Mirroring HP and AC onto the token itself.
//
// The sheet is only visible when someone opens the shape dialog. A PA tracker
// draws on the token, so "how hurt is that goblin" is answerable at a glance,
// and -- more to the point for this project -- the ghost player can change HP
// with a single `Shape.Options.Tracker.Update` instead of a DataBlock rewrite.
//
// The one constraint that shapes this file: a tracker's uuid is the PRIMARY KEY
// of the whole tracker table (server/src/db/models/tracker.py), not a
// per-shape id. A tempting constant like "scc-hp" would work for exactly one
// token and then silently fail to insert for the second. So each shape gets a
// generated uuid, stored back into the sheet, and reused on later saves --
// otherwise every save would stack another HP bar on the token.

import type { LocalId, Tracker, TrackerId } from "@planarally/mod-api";

import type { CharacterSheet } from "./data";
import { api } from "./main";

const SYNC = { ui: true, server: true };

const HP_COLOUR = "#ff7052";
const AC_COLOUR = "#82c8a0";

function newTrackerId(): TrackerId {
    // crypto.randomUUID needs a secure context; PA is served over plain HTTP on
    // a LAN address here, where it is undefined. The fallback only needs to be
    // unique, not unguessable.
    const uuid =
        globalThis.crypto?.randomUUID?.() ??
        `scc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    return uuid as TrackerId;
}

function upsert(shape: LocalId, id: TrackerId | null, tracker: Omit<Tracker, "uuid">): TrackerId {
    const trackers = api.systems.trackers;

    if (id !== null && trackers.get(shape, id) !== undefined) {
        trackers.update(shape, id, tracker, SYNC);
        return id;
    }

    // Either we've never made this tracker, or it was deleted by hand in the
    // Trackers tab. Both mean: make a new one.
    const uuid = newTrackerId();
    trackers.add(shape, { ...tracker, uuid }, SYNC);
    return uuid;
}

/**
 * Push the sheet's HP and AC onto the shape's trackers.
 *
 * Mutates `sheet.trackerIds` and returns whether it changed, so the caller
 * knows it needs to persist the sheet again.
 */
export function syncTrackers(shape: LocalId, sheet: CharacterSheet): boolean {
    const before = `${sheet.trackerIds.hp}/${sheet.trackerIds.ac}`;

    sheet.trackerIds.hp = upsert(shape, sheet.trackerIds.hp as TrackerId | null, {
        name: "HP",
        value: sheet.hp.current + sheet.hp.temp,
        maxvalue: sheet.hp.max,
        visible: true,
        // The only one drawn on the token; two overlapping bars is noise.
        draw: true,
        primaryColor: HP_COLOUR,
        secondaryColor: "#000000",
    });

    sheet.trackerIds.ac = upsert(shape, sheet.trackerIds.ac as TrackerId | null, {
        name: "AC",
        value: sheet.ac,
        maxvalue: sheet.ac,
        visible: true,
        draw: false,
        primaryColor: AC_COLOUR,
        secondaryColor: "#000000",
    });

    return `${sheet.trackerIds.hp}/${sheet.trackerIds.ac}` !== before;
}

/**
 * Claim trackers the token already has, instead of adding rivals beside them.
 *
 * A token that was set up by hand usually already carries an HP tracker. Making
 * a second one leaves two bars disagreeing about the same number, with only one
 * of them wired to the sheet -- so match on name first and only create when
 * there is genuinely nothing to adopt.
 */
export function adoptTrackers(shape: LocalId, sheet: CharacterSheet): boolean {
    let changed = false;

    for (const [key, name] of [
        ["hp", "HP"],
        ["ac", "AC"],
    ] as const) {
        if (sheet.trackerIds[key] !== null) continue;
        const existing = api.systems.trackers
            .getAll(shape)
            .find((t) => t.name.trim().toUpperCase() === name);
        if (existing !== undefined) {
            sheet.trackerIds[key] = existing.uuid;
            changed = true;
        }
    }

    return changed;
}

/**
 * Read HP and AC back off the token.
 *
 * The tracker is the number people actually touch during play -- far more often
 * than the sheet -- so it wins on open. Without this the first save would
 * silently undo every hit the party took, and adopting an existing tracker
 * would blank the values it already held.
 */
export function readBackFromTrackers(shape: LocalId, sheet: CharacterSheet): boolean {
    let changed = false;
    const trackers = api.systems.trackers;

    const hpId = sheet.trackerIds.hp as TrackerId | null;
    if (hpId !== null) {
        const tracker = trackers.get(shape, hpId);
        if (tracker !== undefined) {
            const current = tracker.value - sheet.hp.temp;
            if (current !== sheet.hp.current || tracker.maxvalue !== sheet.hp.max) {
                sheet.hp.current = current;
                sheet.hp.max = tracker.maxvalue;
                changed = true;
            }
        }
    }

    const acId = sheet.trackerIds.ac as TrackerId | null;
    if (acId !== null) {
        const tracker = trackers.get(shape, acId);
        if (tracker !== undefined && tracker.value !== sheet.ac) {
            // Writing `sheet.ac` here would not survive: `deriveSheet` rewrites
            // it from armour on the next save. Editing the token's AC tracker is
            // a deliberate "this creature's AC is N", so it sets the override --
            // the same thing typing in the AC box does.
            sheet.acOverride = tracker.value;
            sheet.ac = tracker.value;
            changed = true;
        }
    }

    return changed;
}
