/**
 * The keyboard shortcuts, written down once.
 *
 * PlanarAlly has around twenty bindings and, before this file, no way to
 * discover any of them: they existed only as `else if (event.key === ...)`
 * branches in down.ts and up.ts. A new user -- someone opening the app to build
 * a map for the first time -- had no route to finding out that Tab switches
 * mode or that `a` opens the assets browser.
 *
 * This table is the source the help overlay renders. It is documentation, not
 * dispatch: the handlers still own the behaviour. Keeping it beside them in the
 * same directory is the reminder that adding a branch there means adding a row
 * here.
 */

export interface Shortcut {
    /** Displayed as-is. Use "+" between simultaneous keys. */
    keys: string[];
    description: string;
    /** Only meaningful to the DM; hidden from players in the overlay. */
    dmOnly?: boolean;
}

export interface ShortcutGroup {
    title: string;
    shortcuts: Shortcut[];
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
    {
        title: "Moving around",
        shortcuts: [
            { keys: ["Arrow keys"], description: "Move the selection, or pan the board when nothing is selected" },
            { keys: ["Numpad 1-9"], description: "The same, including diagonals" },
            { keys: ["Numpad 5"], description: "Centre on the selection, or on the origin" },
            { keys: ["Ctrl", "0"], description: "Reset the viewport to the origin" },
            { keys: ["Space"], description: "Cycle through your own tokens" },
            { keys: ["Page Up"], description: "Go up a floor" },
            { keys: ["Page Down"], description: "Go down a floor" },
            { keys: ["Alt", "Page Up/Down"], description: "Move the selected shapes a floor instead" },
            { keys: ["Alt", "Shift", "Page Up/Down"], description: "Move the shapes and follow them" },
        ],
    },
    {
        title: "Working with shapes",
        shortcuts: [
            { keys: ["Enter"], description: "Open the edit dialog for the selection" },
            { keys: ["d"], description: "Deselect everything" },
            { keys: ["Delete"], description: "Delete the selection" },
            { keys: ["x"], description: "Mark the selection defeated" },
            { keys: ["Ctrl", "l"], description: "Lock or unlock the selection" },
            { keys: ["Ctrl", "c"], description: "Copy" },
            { keys: ["Ctrl", "v"], description: "Paste" },
            { keys: ["Ctrl", "z"], description: "Undo" },
            { keys: ["Ctrl", "Shift", "z"], description: "Redo" },
            { keys: ["Shift"], description: "Hold while moving to ignore collisions", dmOnly: true },
        ],
    },
    {
        title: "Panels and modes",
        shortcuts: [
            { keys: ["Tab"], description: "Switch between Build and Play mode" },
            { keys: ["a"], description: "Open or close the asset browser" },
            { keys: ["n"], description: "Open or close notes" },
            { keys: ["g"], description: "Open or close the ghost console" },
            { keys: ["Ctrl", "u"], description: "Hide or show the whole interface" },
            { keys: ["?"], description: "Show this list" },
        ],
    },
];
