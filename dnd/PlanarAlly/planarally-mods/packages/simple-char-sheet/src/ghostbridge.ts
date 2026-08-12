// Talking to the ghost from a context menu.
//
// Everything the ghost can do is already reachable as a command string, and it
// already resolves names, rolls, applies conditions and narrates. Rebuilding
// any of that in the mod would be a second implementation of the same rules --
// so the menu composes a command and posts it to the same endpoint the console
// uses.
//
// The address is derived from the page rather than hardcoded, so a projector or
// a laptop on the LAN reaches the same Pi that served the game.

const PORT = 8770;

export function ghostUrl(): string {
    const stored = localStorage.getItem("pa-ghost-url");
    if (stored !== null && stored.length > 0) return stored.replace(/\/+$/, "");
    return `${window.location.protocol}//${window.location.hostname}:${PORT}`;
}

/**
 * Fire a command at the ghost.
 *
 * Returns whether it was accepted. Failures are reported by the console panel's
 * own log rather than duplicated as toasts here -- the log is where someone
 * looks when a turn goes wrong, and two places to check is one too many.
 */
export async function sendCommand(command: string): Promise<boolean> {
    try {
        const response = await fetch(`${ghostUrl()}/command`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command, source: "menu" }),
        });
        return response.ok;
    } catch {
        return false;
    }
}
