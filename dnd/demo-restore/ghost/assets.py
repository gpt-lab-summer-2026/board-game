"""Uploading and organising assets.

The asset manager is a *different* socket namespace from the game
(`/pa_assetmgmt` vs `/planarally`), so this opens its own connection reusing the
same session cookie. Uploads are chunked -- the server reassembles slices keyed
by a uuid and only writes the file once `totalSlices` have arrived -- so even a
small file has to follow the slice protocol.

Nothing here is destructive: it creates folders, uploads files, and moves inodes
that were asked for by id. It never deletes.
"""
from __future__ import annotations

import asyncio
import logging
import uuid as uuid_mod
from typing import Any

import socketio
from yarl import URL

from .client import GhostClient

log = logging.getLogger(__name__)

ASSET_NAMESPACE = "/pa_assetmgmt"
# Comfortably under any sane websocket frame limit, and small enough that a
# slow link makes progress visible rather than stalling.
SLICE_BYTES = 128 * 1024


class AssetManager:
    def __init__(self, client: GhostClient):
        self.client = client
        self.sio = socketio.AsyncClient(logger=False, engineio_logger=False)
        self.root: int | None = None
        self._folders: dict[int, list[dict[str, Any]]] = {}

    async def connect(self) -> None:
        session = await self.client.session()
        cookies = session.cookie_jar.filter_cookies(URL(self.client.cfg.base_url))
        header = "; ".join(f"{k}={v.coded_value}" for k, v in cookies.items())
        await self.sio.connect(
            self.client.cfg.base_url,
            namespaces=[ASSET_NAMESPACE],
            headers={"Cookie": header},
            transports=["websocket"],
        )
        await self.refresh()

    async def refresh(self, folder: int | None = None) -> list[dict[str, Any]]:
        """Fetch a folder's children. No argument means the root.

        `Folder.Get` answers with an ack rather than emitting an event, so
        this is a call, not a fire-and-forget with a listener.
        """
        result = await self.sio.call(
            "Folder.Get", folder, namespace=ASSET_NAMESPACE, timeout=15
        )
        data = (result or {}).get("folder") or {}
        folder_id = data.get("id")
        if folder is None:
            self.root = folder_id
        self._folders[folder_id] = data.get("children") or []
        return self._folders[folder_id]

    async def close(self) -> None:
        if self.sio.connected:
            await self.sio.disconnect()

    # ---- folders -----------------------------------------------------------

    def find_child(self, parent: int, name: str) -> dict[str, Any] | None:
        for child in self._folders.get(parent, []):
            if child.get("name") == name:
                return child
        return None

    async def ensure_folder(self, name: str, parent: int | None = None) -> int:
        """Create a folder if it isn't there, and return its id either way."""
        parent = parent if parent is not None else self.root
        assert parent is not None

        # Look at the *parent*, not whatever was cached last. Refreshing the
        # root here instead was the bug that made every nested folder look
        # like a failed creation.
        await self.refresh(parent)
        existing = self.find_child(parent, name)
        if existing is not None and existing.get("asset") is None:
            return int(existing["id"])

        await self.sio.emit(
            "Folder.Create", {"name": name, "parent": parent}, namespace=ASSET_NAMESPACE
        )
        await asyncio.sleep(0.4)
        await self.refresh(parent)
        created = self.find_child(parent, name)
        if created is None:
            raise RuntimeError(f"could not create folder {name!r}")
        log.info("created folder %r", name)
        return int(created["id"])

    # ---- uploads -----------------------------------------------------------

    async def upload(self, name: str, data: bytes, directory: int) -> None:
        """Upload one file, sliced the way the server expects."""
        upload_id = str(uuid_mod.uuid4())
        slices = max(1, -(-len(data) // SLICE_BYTES))
        for index in range(slices):
            chunk = data[index * SLICE_BYTES : (index + 1) * SLICE_BYTES]
            await self.sio.emit(
                "Asset.Upload",
                {
                    "uuid": upload_id,
                    "name": name,
                    "directory": directory,
                    "newDirectories": [],
                    "slice": index,
                    "totalSlices": slices,
                    "data": chunk,
                },
                namespace=ASSET_NAMESPACE,
            )
        # The write happens on the final slice; give it a moment to land before
        # the caller refreshes and looks for it.
        await asyncio.sleep(0.5)
        log.info("uploaded %s (%d bytes, %d slice(s))", name, len(data), slices)

    async def find_texture(self, name: str) -> dict[str, Any] | None:
        """Look up an uploaded texture by name, anywhere under Textures/.

        Returns a flat {name, fileHash, assetId} -- the two fields an
        `assetrect` needs. They arrive nested under `asset`, and folders are
        distinguished by that key being null rather than by any type field.
        """
        root = await self.refresh()
        textures = next((c for c in root if c.get("name") == "Textures"), None)
        if textures is None:
            return None
        for folder in await self.refresh(int(textures["id"])):
            if folder.get("asset") is not None:
                continue
            for child in await self.refresh(int(folder["id"])):
                asset = child.get("asset")
                if child.get("name") == name and asset:
                    return {
                        "name": child["name"],
                        "fileHash": asset["fileHash"],
                        "assetId": asset["id"],
                    }
        return None

    async def share(self, inode: int, username: str, right: str = "edit") -> None:
        """Share a folder with another account.

        Assets are per-user: the ghost uploading a texture puts it in the
        *ghost's* tree, where the DM would never see it. Sharing the folder
        is what makes it appear in their asset manager.
        """
        await self.sio.emit(
            "Asset.Share.Create",
            {"asset": inode, "user": username, "right": right},
            namespace=ASSET_NAMESPACE,
        )

    async def move(self, inode: int, parent: int) -> None:
        await self.sio.emit(
            "Inode.Move", {"inode": inode, "target": parent}, namespace=ASSET_NAMESPACE
        )
