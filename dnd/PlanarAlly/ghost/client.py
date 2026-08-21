"""A headless PlanarAlly client -- the "ghost player" the voice pipeline drives.

Connects the same way a browser does, because PlanarAlly has no separate
machine API: log in over HTTP for a session cookie, then open a socket.io
connection on the /planarally namespace carrying that cookie. The server
requires the account to already have a PlayerRoom row for the room, or it
silently refuses the connection (see server/src/api/socket/connection.py).

Everything the game sends arrives as socket events; the interesting ones for
perceiving a board are Board.Set (the whole initial state) and the Shape.*
family (incremental changes).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from yarl import URL

import aiohttp
import socketio

log = logging.getLogger(__name__)

GAME_NAMESPACE = "/planarally"


@dataclass
class GhostConfig:
    base_url: str = "http://127.0.0.1:8000"
    username: str = "ghost"
    password: str = ""
    # The room's creator and name, exactly as they appear in the game URL
    # /game/<creator>/<room>. The socket handshake matches on both.
    room_creator: str = "sampo"
    room_name: str = "sanpo"
    # Refuse to emit anything that would change the session. Worth keeping on
    # until the intent parser has been watched for a while: a bad parse
    # otherwise becomes a visible change in someone's live game.
    dry_run: bool = False


@dataclass
class InitiativeState:
    """The initiative order, as the server last broadcast it.

    The ghost used to have no copy of this at all. `turns.active_shape` read the
    `pa-turnbudget` block instead, which is written *only* by an open DM browser
    -- so with the projector tab closed it went stale, and it never held the
    order or its length, which is exactly what advancing a turn needs.

    `Location.Load` already sends `Initiative.Set`, so nothing extra has to be
    asked for; the ghost simply used to throw it away in the catch-all.
    """

    round: int = 0
    turn: int = 0
    sort: int = 0
    is_active: bool = False
    """Shape uuids, in turn order."""
    order: list[str] = field(default_factory=list)

    @property
    def current(self) -> str | None:
        """The shape whose turn it is, or None if the order is empty."""
        if 0 <= self.turn < len(self.order):
            return self.order[self.turn]
        return None

    def clear(self) -> None:
        self.round = 0
        self.turn = 0
        self.sort = 0
        self.is_active = False
        self.order.clear()


@dataclass
class BoardState:
    """What the ghost currently believes is on the board."""

    locations: dict[int, str] = field(default_factory=dict)
    floors: list[dict[str, Any]] = field(default_factory=list)
    shapes: dict[str, dict[str, Any]] = field(default_factory=dict)
    """shape uuid -> layer name."""
    shape_layer: dict[str, str] = field(default_factory=dict)
    """shape uuid -> floor name. Needed to know what a floor removal would
    strand; see scene.remove_floor."""
    shape_floor: dict[str, str] = field(default_factory=dict)
    players: dict[int, str] = field(default_factory=dict)
    """character name -> shape uuid. What lets a voice command name a target."""
    characters: dict[str, str] = field(default_factory=dict)
    """character name -> character id, which is what Character.Remove wants
    (shape uuid and character id are different keys)."""
    character_ids: dict[str, int] = field(default_factory=dict)
    """Grid geometry, needed to reason about movement in cells rather than pixels."""
    grid_type: str = "SQUARE"
    """How many feet one cell represents."""
    unit_size: float = 5.0
    """Shapes the DM has explicitly marked as dangerous terrain."""
    hazard_uuids: set[str] = field(default_factory=set)
    """Name of the floor the ghost is looking at. Shape.Add addresses floors
    and layers by name, not id, and silently drops an unknown pair."""
    current_floor: str | None = None
    """Round, turn and order, mirrored from the server's initiative broadcasts."""
    initiative: InitiativeState = field(default_factory=InitiativeState)

    def find_shape(self, name: str) -> str | None:
        """Resolve a spoken name to a shape uuid.

        Case-insensitive, and falls back to a unique substring match -- speech
        recognition rarely returns the exact capitalisation a DM typed, and
        "hamta" should find "big hamta". An ambiguous prefix returns None
        rather than guessing, because acting on the wrong token is worse than
        asking again.
        """
        wanted = name.strip().lower()
        for char_name, uuid in self.characters.items():
            if char_name.lower() == wanted:
                return uuid
        matches = [u for n, u in self.characters.items() if wanted in n.lower()]
        return matches[0] if len(matches) == 1 else None

    def summary(self) -> str:
        by_layer: dict[str, int] = {}
        for layer in self.shape_layer.values():
            by_layer[layer] = by_layer.get(layer, 0) + 1
        layers = ", ".join(f"{k}={v}" for k, v in sorted(by_layer.items())) or "none"
        return (
            f"{len(self.shapes)} shape(s) across {len(self.floors)} floor(s) "
            f"[{layers}]"
        )


class GhostClient:
    def __init__(self, cfg: GhostConfig):
        self.cfg = cfg
        self.state = BoardState()
        self.sio = socketio.AsyncClient(logger=False, engineio_logger=False)
        self._session: aiohttp.ClientSession | None = None
        self._connected = asyncio.Event()
        self._board_ready = asyncio.Event()
        self._grid_known = False
        # Re-entrancy guard: a turn change can arrive twice (the DM's own emit
        # and the server's broadcast), and ticking a duration twice would halve
        # its length.
        self._turn_hook_busy = False
        # Set by the console, so anything the ghost notices on its own -- a
        # modifier wearing off -- reaches the combat log rather than only the
        # server log.
        self.on_narration: Callable[[str], Awaitable[None]] | None = None
        self._register_handlers()

    # ---- connection ---------------------------------------------------------

    async def login(self) -> None:
        """Authenticate and keep the session cookie for the socket handshake."""
        # unsafe=True is required, not optional: aiohttp's default cookie jar
        # silently discards cookies from IP-literal hosts such as 127.0.0.1, so
        # the session cookie never gets stored and the socket handshake arrives
        # unauthenticated -- which PlanarAlly answers with a `redirect` to / and
        # no further events, looking exactly like a protocol mismatch.
        session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
        try:
            async with session.post(
                f"{self.cfg.base_url}/api/login",
                json={"username": self.cfg.username, "password": self.cfg.password},
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(
                        f"login failed ({resp.status}): {await resp.text()}"
                    )
        except BaseException:
            # Don't leak the connector on a failed login. Without this, a bad
            # password produces the real error plus two "Unclosed client
            # session" tracebacks from the GC, which bury it.
            await session.close()
            raise

        self._session = session
        log.info("logged in as %s", self.cfg.username)

    async def session(self) -> aiohttp.ClientSession:
        """The logged-in HTTP session, for the parts of PA that aren't sockets
        (mod and asset uploads). Logs in on first use."""
        if self._session is None:
            await self.login()
        assert self._session is not None
        return self._session

    async def connect(self) -> None:
        if self._session is None:
            await self.login()
        cookies = self._session.cookie_jar.filter_cookies(
            URL(self.cfg.base_url)
        )
        # coded_value, not value: the session cookie is quoted and base64-ish,
        # and stripping the quotes makes the server reject it.
        cookie_header = "; ".join(
            f"{k}={v.coded_value}" for k, v in cookies.items()
        )
        if not cookie_header:
            raise RuntimeError(
                "no session cookie after login -- the socket would connect "
                "unauthenticated and receive only a redirect"
            )

        # The server reads user/room off the query string and matches them
        # against the Room table; unquote happens after the & split server-side,
        # so names containing & would break -- quote each value separately.
        query = (
            f"user={quote(self.cfg.room_creator, safe='')}"
            f"&room={quote(self.cfg.room_name, safe='')}"
        )
        await self.sio.connect(
            f"{self.cfg.base_url}?{query}",
            namespaces=[GAME_NAMESPACE],
            headers={"Cookie": cookie_header},
            transports=["websocket"],
        )
        await asyncio.wait_for(self._connected.wait(), timeout=10)

    async def load_board(self, timeout: float = 30) -> BoardState:
        """Ask for the board and wait until it has all arrived.

        Nothing is sent on connect alone -- the client has to request it. The
        server answers with Board.Locations.Set, one Board.Floor.Set per floor,
        Location.Set, and finally Location.Loaded, which is the only reliable
        signal that the whole board has been delivered.
        """
        self._board_ready.clear()
        self._grid_known = False
        self.reset_board_state()
        await self.sio.emit("Location.Load", namespace=GAME_NAMESPACE)
        await asyncio.wait_for(self._board_ready.wait(), timeout=timeout)

        # Falling back to a square 5ft grid on a hex board is wrong in a way
        # nothing downstream can detect -- every distance, movement budget and
        # ruler is quietly off. Say so rather than carrying on silently.
        if not self._grid_known:
            log.warning(
                "no grid settings received; assuming %s at %sft per cell. "
                "Distances may be wrong.", self.state.grid_type, self.state.unit_size
            )
        return self.state

    def reset_board_state(self) -> None:
        """Drop the perceived board.

        Any caller that emits Location.Load must do this first: the server
        replays every floor, and Board.Floor.Set appends, so a second load
        without a reset leaves the ghost believing in twice as many floors.
        """
        self.state.floors.clear()
        self.state.shapes.clear()
        self.state.shape_layer.clear()
        self.state.shape_floor.clear()
        self.state.characters.clear()
        self.state.character_ids.clear()
        self.state.current_floor = None
        # Or a location with no initiative of its own inherits the previous
        # one's order and reports somebody else's turn.
        self.state.initiative.clear()

    async def on_turn_advanced(self) -> None:
        """Count sheet-held durations down because a turn has gone by.

        The browser ticks PlanarAlly's own initiative effects; anything the
        character sheet mod owns -- a +2 that lasts two rounds -- is invisible to
        it, so the ghost does that half.

        Called from two places, and it has to be: the socket handler when a
        human advances the turn, and `initiative.next_turn` when the ghost does.
        The server echoes `Initiative.Turn.Update` with `skip_sid`, so the ghost
        never hears its own, and a version that only ticked on the broadcast
        would expire durations exclusively when somebody clicked.

        Imported inside the function rather than at module scope: `turns`
        imports `sheet`, which imports this module.
        """
        from . import turns  # noqa: PLC0415 - circular at import time

        if self._turn_hook_busy:
            return
        self._turn_hook_busy = True
        try:
            from . import ephemera  # noqa: PLC0415 - same cycle as turns

            lines = await turns.tick_durations(client=self, shapes=list(self.state.shapes))
            # Ruler marks, suggestion highlights and spell effects all count
            # their lives in turns, so they expire on the same beat.
            lines.extend(f"{label}." for label in await ephemera.tick(self))
            for line in lines:
                log.info("duration: %s", line)
            if lines and self.on_narration is not None:
                await self.on_narration(" ".join(lines))
        except Exception:
            # A failed tick must not take the socket handler down with it; the
            # next turn will try again.
            log.exception("could not tick durations")
        finally:
            self._turn_hook_busy = False

    async def close(self) -> None:
        if self.sio.connected:
            await self.sio.disconnect()
        if self._session is not None:
            await self._session.close()

    # ---- receiving ----------------------------------------------------------

    def _register_handlers(self) -> None:
        ns = GAME_NAMESPACE

        @self.sio.event(namespace=ns)
        async def connect():  # noqa: D401 - socket.io callback name is fixed
            log.info("socket connected to %s", ns)
            self._connected.set()

        @self.sio.event(namespace=ns)
        async def disconnect():
            log.info("socket disconnected")
            self._connected.clear()

        @self.sio.on("Board.Locations.Set", namespace=ns)
        async def locations_set(data):
            for loc in data or []:
                if isinstance(loc, dict) and "id" in loc:
                    self.state.locations[loc["id"]] = loc.get("name", "?")

        @self.sio.on("Board.Floor.Set", namespace=ns)
        async def floor_set(data):
            # One of these per floor. Each carries its layers, each layer its
            # shapes -- this is the bulk of what the ghost perceives.
            self.state.floors.append(data)
            if self.state.current_floor is None:
                self.state.current_floor = data.get("name")
            for layer in data.get("layers", []):
                for shape in layer.get("shapes", []):
                    uuid = shape.get("uuid")
                    if uuid:
                        self.state.shapes[uuid] = shape
                        self.state.shape_layer[uuid] = layer.get("name", "?")
                        self.state.shape_floor[uuid] = data.get("name", "?")

        @self.sio.on("Locations.Settings.Set", namespace=ns)
        async def location_settings(data):
            # Carries the active location's options, including grid type and
            # how many feet a cell is worth. Without these the ghost would have
            # to assume a 5ft square grid and would be a cell out on the hex
            # board this table actually uses.
            # Shape is {default: {...}, active: <location id>, locations: {id: {...}}}.
            # `active` is an *id*, not an options object -- treating it as one
            # raised "'int' object is not a mapping" and left the ghost on its
            # square/5ft defaults against a hex board at 7ft.
            options: dict[str, Any] = {}
            if isinstance(data, dict):
                options = dict(data.get("default") or {})
                active = data.get("active")
                locations = data.get("locations") or {}
                # Keys are ints server-side and strings once JSON-encoded.
                overrides = locations.get(str(active)) or locations.get(active)
                if isinstance(overrides, dict):
                    # Per-location options are *optional overrides*: None means
                    # "inherit the room default". A plain dict.update() treats
                    # those Nones as values and wipes the defaults -- which
                    # silently reverted the ghost to a square 5ft grid on a hex
                    # board, and every distance with it.
                    options.update({k: v for k, v in overrides.items() if v is not None})

            grid = options.get("grid_type")
            unit = options.get("unit_size")
            if grid:
                self.state.grid_type = str(grid)
            if unit:
                self.state.unit_size = float(unit)
            self._grid_known = bool(grid and unit)
            log.info("grid: %s at %s per cell", self.state.grid_type, self.state.unit_size)

        @self.sio.on("Characters.Set", namespace=ns)
        async def characters_set(data):
            # Sent once per full location load, and the only place names are
            # attached to shapes -- Board.Floor.Set carries uuids only.
            entries = [c for c in data or [] if "name" in c and "shapeId" in c]
            self.state.characters = {c["name"]: c["shapeId"] for c in entries}
            self.state.character_ids = {c["name"]: c["id"] for c in entries if "id" in c}
            log.info("characters: %s", ", ".join(sorted(self.state.characters)) or "none")

        @self.sio.on("Character.Created", namespace=ns)
        async def character_created(data):
            # Characters.Set only fires once, at full location load -- a
            # character created afterwards would otherwise never be found by
            # voice/console commands until the ghost reconnects.
            name, shape_id, char_id = data.get("name"), data.get("shapeId"), data.get("id")
            if name and shape_id:
                self.state.characters[name] = shape_id
            if name and char_id is not None:
                self.state.character_ids[name] = char_id
            log.info("character created: %s", name)

        @self.sio.on("Character.Renamed", namespace=ns)
        async def character_renamed(data):
            # self.state.characters is keyed by name, so a rename means
            # dropping whatever name this character id was previously known
            # under before adding the new one -- otherwise the old name would
            # keep resolving to the same shape forever.
            name, shape_id, char_id = data.get("name"), data.get("shapeId"), data.get("id")
            if char_id is None:
                return
            stale = [n for n, cid in self.state.character_ids.items() if cid == char_id]
            for n in stale:
                self.state.characters.pop(n, None)
                self.state.character_ids.pop(n, None)
            if name and shape_id:
                self.state.characters[name] = shape_id
            if name:
                self.state.character_ids[name] = char_id
            log.info("character renamed: %s", name)

        @self.sio.on("Character.Removed", namespace=ns)
        async def character_removed(char_id):
            stale = [n for n, cid in self.state.character_ids.items() if cid == char_id]
            for n in stale:
                self.state.characters.pop(n, None)
                self.state.character_ids.pop(n, None)
            log.info("character removed: %s", char_id)

        @self.sio.on("Location.Loaded", namespace=ns)
        async def location_loaded(_data=None):
            log.info("board received: %s", self.state.summary())
            self._board_ready.set()

            # Clear decorations a previous run stranded on the draw layer.
            # Folded into this handler rather than registered as a second one:
            # python-socketio keeps a single handler per event, so adding
            # another `Location.Loaded` silently *replaced* this one and the
            # ghost never became ready again.
            from . import ephemera  # noqa: PLC0415 - cycle at import time

            try:
                await ephemera.sweep_orphans(self)
            except Exception:  # noqa: BLE001
                log.exception("could not sweep old marks")

        @self.sio.on("Shape.Add", namespace=ns)
        async def shape_add(data):
            shape = data.get("shape", data)
            uuid = shape.get("uuid")
            if uuid:
                self.state.shapes[uuid] = shape
                self.state.shape_layer[uuid] = data.get("layer", "?")
                log.info("shape added: %s", uuid)

        @self.sio.on("Shape.Remove", namespace=ns)
        async def shape_remove(data):
            uuid = data if isinstance(data, str) else data.get("uuid")
            self.state.shapes.pop(uuid, None)
            self.state.shape_layer.pop(uuid, None)
            log.info("shape removed: %s", uuid)

        @self.sio.on("Shapes.Position.Update", namespace=ns)
        async def shape_moved(data):
            """Someone else moved something; keep our copy of the board honest.

            Plural and nested, matching what the server actually broadcasts. The
            singular form this used to listen for never fired, so the ghost's
            idea of where everything stood only ever updated from its own moves.
            """
            entries = data.get("shapes") if isinstance(data, dict) else data
            for entry in entries or []:
                uuid = entry.get("uuid")
                points = (entry.get("position") or {}).get("points") or []
                if uuid in self.state.shapes and points:
                    x, y = points[0][0], points[0][1]
                    self.state.shapes[uuid].update({"x": x, "y": y})
                    log.info("shape moved: %s -> (%s,%s)", uuid, x, y)

        @self.sio.on("Initiative.Set", namespace=ns)
        async def initiative_set(data):
            """The whole order, replaced wholesale.

            Broadcast to everyone *including* the sender, unlike most initiative
            events, which is what makes it usable as the ghost's source of
            truth. `Location.Load` sends one, so the order is primed on connect.
            """
            init = self.state.initiative
            init.round = int(data.get("round") or 0)
            init.turn = int(data.get("turn") or 0)
            init.sort = int(data.get("sort") or 0)
            init.is_active = bool(data.get("isActive"))
            init.order = [e["shape"] for e in (data.get("data") or []) if e.get("shape")]
            log.info("initiative: %d entries, round %d turn %d", len(init.order), init.round, init.turn)

        @self.sio.on("Initiative.Round.Update", namespace=ns)
        async def round_updated(data):
            self.state.initiative.round = int((data or {}).get("round") or 0)

        @self.sio.on("Initiative.Active.Set", namespace=ns)
        async def initiative_active(data):
            self.state.initiative.is_active = bool(data)

        @self.sio.on("Initiative.Sort.Set", namespace=ns)
        async def initiative_sort(data):
            self.state.initiative.sort = int(data or 0)

        @self.sio.on("Initiative.Remove", namespace=ns)
        async def initiative_removed(data):
            uuid = data if isinstance(data, str) else (data or {}).get("shape")
            init = self.state.initiative
            if uuid in init.order:
                gone = init.order.index(uuid)
                init.order.remove(uuid)
                # Removing someone before the current actor shifts everyone
                # after them down a slot; without this the ghost's idea of whose
                # turn it is silently slides by one.
                if gone < init.turn:
                    init.turn -= 1
                init.turn = max(0, min(init.turn, max(0, len(init.order) - 1)))

        @self.sio.on("Initiative.Add", namespace=ns)
        async def initiative_added(data):
            uuid = (data or {}).get("shape")
            if uuid and uuid not in self.state.initiative.order:
                # Appended, not sorted: the server appends too, and the browser
                # sends a Sort.Set afterwards if it wants an order.
                self.state.initiative.order.append(uuid)

        @self.sio.on("Initiative.Clear", namespace=ns)
        async def initiative_cleared(data=None):
            # Clear drops the *effects*, not the order -- but the round goes
            # back to 1 and the turn to the top.
            self.state.initiative.round = 1
            self.state.initiative.turn = 0

        @self.sio.on("Initiative.Wipe", namespace=ns)
        async def initiative_wiped(data=None):
            self.state.initiative.clear()

        @self.sio.on("Initiative.Turn.Update", namespace=ns)
        async def turn_advanced(data):
            """Someone else moved the turn on. Mirror it, then tick.

            Note the ghost does *not* hear its own turn updates: the server
            re-broadcasts this one with `skip_sid`. Anything that advances the
            turn from this side has to call `on_turn_advanced` itself, which is
            why the body below is a method rather than inline here.
            """
            turn = (data or {}).get("turn")
            if isinstance(turn, int):
                self.state.initiative.turn = turn
            await self.on_turn_advanced()

        @self.sio.on("*", namespace=ns)
        async def catch_all(event, data=None):
            # Deliberately noisy at DEBUG: the protocol is large and mostly
            # undocumented, so seeing the real event names is how we learn it.
            log.debug("event %s: %r", event, data)

    # ---- acting -------------------------------------------------------------

    async def emit(self, event: str, data: Any) -> None:
        """Send an event, unless running dry."""
        if self.cfg.dry_run:
            log.warning("[dry-run] would emit %s: %r", event, data)
            return
        await self.sio.emit(event, data, namespace=GAME_NAMESPACE)
        log.info("emitted %s", event)

    async def roll_dice(
        self,
        notation: str = "1d20",
        share_with: str = "all",
        as_player: str | None = None,
    ) -> "DiceRoll":
        """Roll dice and announce the result to the session.

        The roll happens here, not on the server -- PlanarAlly only relays the
        outcome. share_with is "all", "dm" or "none"; "none" means the server
        forwards it to nobody, which makes it useless from a headless client
        since we have no UI of our own to show it in.

        `as_player` attributes the roll to someone else, which is the point of a
        voice-driven table: a player says "roll me a d20" and the result should
        appear under *their* name, not the ghost's. The server does no checking
        here -- it copies `player` straight through to everyone (see
        api/socket/dice.py) -- so this works, but it also means dice results in
        PlanarAlly are only as trustworthy as the client that sent them. Fine
        for a co-operative table; worth knowing before relying on it.
        """
        from .dice import roll as roll_notation

        result = roll_notation(notation)
        attributed_to = as_player or self.cfg.username
        await self.emit(
            "Dice.Roll.Result",
            result.to_payload(attributed_to, share_with),
        )
        log.info(
            "rolled %s for %s -> %s %s",
            result.notation, attributed_to, result.total, result.long_result(),
        )
        return result

    async def move_shape(self, uuid: str, x: float, y: float, angle: float = 0.0) -> None:
        """Move a token. Coordinates are PlanarAlly world units, not pixels.

        The event is `Shapes.Position.Update` -- plural, with the payload nested
        under `position.points` -- because that is the only mover the server
        registers (see api/socket/shape/__init__.py). An earlier singular
        `Shape.Position.Update` carrying flat x/y was accepted by socket.io and
        then dropped on the floor: unknown events raise nothing, so every move
        "succeeded" and nothing on the board ever moved.
        """
        shape = self.state.shapes.get(uuid)
        if shape is None:
            raise KeyError(f"unknown shape {uuid}")
        await self.emit(
            "Shapes.Position.Update",
            {
                "temporary": False,
                "shapes": [
                    {"uuid": uuid, "position": {"angle": angle, "points": [[x, y]]}}
                ],
            },
        )
        shape.update({"x": x, "y": y})
