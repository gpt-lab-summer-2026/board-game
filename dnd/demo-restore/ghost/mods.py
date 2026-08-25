"""Upload and (re)link PlanarAlly mods without going through the browser.

Two halves, because PlanarAlly splits them: the .pam is uploaded over plain
HTTP, but attaching it to a room is a socket event, so both a logged-in session
and a live game connection are needed.

The wrinkle worth knowing: a Mod row is keyed by tag+name+version+**hash of the
zip**, so every rebuild -- even one that only changes a comment -- produces a
new row. Re-uploading does not update the mod a room is using; the room keeps
pointing at the old row until it is explicitly relinked. Leaving both linked is
worse than either: PlanarAlly would load two copies of the same mod, register
the tab twice, and have both instances writing the same DataBlocks. So
`install` unlinks every other version of the tag before linking the new one.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .client import GAME_NAMESPACE, GhostClient

log = logging.getLogger(__name__)


async def upload(client: GhostClient, pam: Path | str) -> dict[str, Any]:
    """POST a .pam and return its metadata, including the hash to link by."""
    path = Path(pam)
    session = await client.session()

    async with session.post(
        f"{client.cfg.base_url}/api/mod/upload", data=path.read_bytes()
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"mod upload failed ({resp.status}): {await resp.text()}")
        meta: dict[str, Any] = await resp.json()

    log.info("uploaded %s -> %s v%s (%s)", path.name, meta["tag"], meta["version"], meta["hash"][:10])
    return meta


async def linked_mods(client: GhostClient, timeout: float = 15) -> list[dict[str, Any]]:
    """The mods this room currently loads.

    Only sent as part of Room.Info.Set during a full location load, so this
    asks for one rather than waiting for it to happen by itself.
    """
    import asyncio

    received: asyncio.Future[list[dict[str, Any]]] = asyncio.get_running_loop().create_future()

    @client.sio.on("Room.Info.Set", namespace=GAME_NAMESPACE)
    async def room_info(data: dict[str, Any]) -> None:
        if not received.done():
            received.set_result(data.get("mods", []))

    client.reset_board_state()
    await client.sio.emit("Location.Load", namespace=GAME_NAMESPACE)
    return await asyncio.wait_for(received, timeout=timeout)


def _link_payload(meta: dict[str, Any]) -> dict[str, str]:
    # The server looks the Mod row up by these three fields alone.
    return {"tag": meta["tag"], "version": meta["version"], "hash": meta["hash"]}


async def link(client: GhostClient, meta: dict[str, Any]) -> None:
    await client.emit("Mods.Room.Link", _link_payload(meta))


async def unlink(client: GhostClient, meta: dict[str, Any]) -> None:
    await client.emit("Mods.Room.Remove", _link_payload(meta))


async def install(client: GhostClient, pam: Path | str) -> dict[str, Any]:
    """Upload a mod and make it *the* version this room uses.

    Returns the new mod's metadata. Clients already in the session keep running
    the old build until they reload the page -- mods are fetched at game open.
    """
    meta = await upload(client, pam)

    for existing in await linked_mods(client):
        if existing["tag"] != meta["tag"]:
            continue
        if existing["hash"] == meta["hash"] and existing["version"] == meta["version"]:
            log.info("%s v%s already linked", meta["tag"], meta["version"])
            return meta
        log.info(
            "unlinking older %s v%s (%s)", existing["tag"], existing["version"], existing["hash"][:10]
        )
        await unlink(client, existing)

    await link(client, meta)
    log.info("linked %s v%s -- reload the game tab to pick it up", meta["tag"], meta["version"])
    return meta
