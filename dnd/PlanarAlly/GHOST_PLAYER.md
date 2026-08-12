# Voice-driven D&D on PlanarAlly — project notes

Working notes for the voice pipeline that drives a PlanarAlly session. Written
from what's on this machine plus the workflow as described; the "open
questions" section is where my understanding still has gaps.

## The pipeline

```
wake word  ──▶ whisper ──▶ SLM intent ──▶ websocket ──▶ PlanarAlly API
(openWakeWord)  (STT)      (gemma3)      localhost:8000   as a "ghost player"
                                                              │
                                                              ▼
                                                         UI functions
                                                              │
                                     kokoro TTS ◀── SLM turn processing
```

Reusable from the board-game work in this repo, unchanged in shape:

| stage | what already exists |
|---|---|
| wake word | `voice/wakeword.py` — openWakeWord, `hey_jarvis`, ~80ms frames |
| speaker ID | `voice/speaker_id.py` — pyannote embeddings, 1:1 verification per player |
| STT | `voice/stt.py` — faster-whisper `distil-small.en`, VAD on, vocabulary bias |
| SLM | `scripts/llama-server.sh` + grammar-constrained JSON. **`--swa-full` is load-bearing**: without it gemma3 discards its own prompt cache every call and prefill costs ~15s |
| TTS | `voice/tts.py` — Kokoro ONNX, played via `pw-play`, 0.8s lead-in silence for the Bluetooth speaker |

The intent layer's shape carries over too (`src/llm/`): the model only ever
emits a small grammar-constrained JSON object chosen from enumerated options,
and deterministic code does everything consequential with it. Worth keeping —
a 4B model reliably loses to lexical similarity when asked to pick between
similar names, so exact-string matches should override it where they exist.

## PlanarAlly, as installed here

- `2026.1.2` (`v2026.1.2-72-gc677f979`), running from `server/` via `uv run planarally.py`, listening on **0.0.0.0:8000**
- Client is Vue; server is aiohttp + peewee + **socket.io**
- Save file: `server/data/planar.sqlite`

Current contents:

- user: **`sampo`**
- room: **`sanpo`** (creator `sampo`), invite code `7ea0ebf1-89ce-43d4-9200-e6b2d981a600`
- location: **`start`**, with 7 layers — `map`, `grid`, `tokens`, `dm`, `fow`, `fow-players`, `draw`
- 2 rect shapes on the tokens layer, at (1500, 250) and (1550, 300)
- game URL: `/game/sampo/sanpo`

### The mods are a different thing from the ghost player

`planarally-mods/` builds **client-side** mods: Vue/TS bundled by vite, zipped
with `mod.toml` into a `.pam`, imported through PA's UI. They run *in the
browser*, and the API they use (`packages/api`) is types for datablocks,
trackers, characters and shape settings.

So mods are the right tool for *UI surface* — a character sheet, a custom
tracker, a panel showing what the voice system heard. They are **not** how an
external process drives the game. That's the socket protocol below. The four
packages present: `api` (shared types), `simple-char-sheet` and
`obfuscated-trackers` (educational), `wildsea` (a real system integration).

Build is pnpm: `pnpm install && pnpm -r build-api && pnpm -r build`, then
`pnpm zip <name>`. `pnpm` is not on PATH on this machine and corepack pulls a
pnpm that needs Node 22 (we have 20), so with `node_modules` already installed
the per-package binaries work directly:

```
cd planarally-mods/packages/<name>
./node_modules/.bin/vue-tsc --noEmit -p tsconfig.app.json --composite false
./node_modules/.bin/vite build
cd ../.. && node scripts/zip-mod.js <name>
```

### Installing a rebuilt mod

`ghost/mods.py` does upload + relink over the ghost connection:

```python
from ghost import mods
await mods.install(client, "planarally-mods/packages/simple-char-sheet/dist-zip/simple-char-sheet.pam")
```

A `Mod` row is keyed by tag+name+version+**hash of the zip**, so *any* rebuild
creates a new row and the room keeps loading the old one until relinked.
Linking both is actively harmful — PA would load the mod twice, register the
tab twice, and have two instances writing the same DataBlocks — so `install`
unlinks other versions of the same tag first. Browsers already in the session
keep the old build until the tab is reloaded.

### Character editor (`scc` v0.3.0)

The Char Sheet tab is now a character editor. Data lives in DataBlocks, which is
what lets the ghost drive it:

| block | scope | holds |
|---|---|---|
| `sheet` | shape | abilities, race/background/class, HP/AC/speed, equipped weapons, description, `derived`, `trackerIds` |
| `catalogue` | room | weapons, races, backgrounds, classes — seeded from defaults, editable live |
| `presets` | room | reusable stat blocks, not tied to an asset |

**The rules live in exactly one place.** `rules.ts` computes attack and damage
notation and the mod writes the finished strings into `sheet.derived` on every
save. `ghost/sheet.py` reads those strings and rolls them; it contains no 5e
arithmetic. Two implementations would drift, and the first symptom would be a
voice-rolled attack quietly using the wrong modifier.

HP and AC are mirrored to real PA trackers. Tracker uuids are the **primary key
of the whole tracker table**, not per-shape, so a fixed id like `scc-hp` would
work for one token and then silently fail to insert; each shape gets a generated
uuid stored in `sheet.trackerIds`.

The pre-0.3.0 `data` block is read once and folded into the new sheet, then left
untouched on disk as a fallback.

```python
from ghost import sheet
uuid = client.state.find_shape("hamta")       # from Characters.Set
await sheet.roll_attack(client, uuid, "melee", as_player="sampo")
await sheet.damage(client, uuid, 7)            # temp HP first, then the token tracker
```

### What the vendored mod API gets wrong

`planarally-mods/packages/api` is a hand-written declaration of what
`client/src/mods/events.ts` passes, and it had drifted from it. Fixed locally:

- it declared `TrackerSystem.getOrCreate(...)`, **which does not exist** — any
  mod calling it would have thrown;
- it omitted `ui.modals`, `gameplay.activateTool`, `eventBus`, `hooks`, and
  every system beyond `characters`/`trackers`;
- `ApiCharacter` was missing `name`, `assetHash` and `assetId`, all of which the
  server sends.

Rebuild it with `packages/api/node_modules/.bin/tsc --noEmit && .../vite build`
before rebuilding a mod that depends on the new types.

Gotcha: a DataBlock's generic is constrained to `Record<string, unknown>`, and
only `type` aliases get TypeScript's implicit index signature. Declaring a
sheet as an `interface` fails with an opaque "index signature is missing".

## How a ghost player connects

Three steps, all verified against the server source rather than assumed:

1. **Log in** — `POST /api/login` with `{"username", "password"}` (not
   `/api/auth/login`; see `src/routes.py`). Session cookie via
   `aiohttp_security` (`src/api/http/auth.py`). The cookie jar must be built
   with `aiohttp.CookieJar(unsafe=True)` — the default jar silently discards
   cookies from IP-literal hosts like `127.0.0.1`, and the resulting
   unauthenticated socket just gets a `redirect` and no events.
2. **Be a member of the room** — `POST /api/invite` with `{"code": "<invite>"}`
   creates a `PlayerRoom` row with **`Role.PLAYER`** (`src/api/http/__init__.py`).
   This is required: `connect` rejects any socket whose user has no `PlayerRoom`
   for that room.
3. **Connect the socket** — socket.io namespace **`/planarally`**, query string
   `?user=sampo&room=sanpo`, carrying the session cookie
   (`src/api/socket/connection.py`). The server then joins the sid to the room
   and location channels and starts sending events.

`python-socketio` (with `AsyncClient`) is already installed in
`server/.venv`, so the ghost can be a small Python process alongside the voice
stack rather than a headless browser.

## Open questions

**Role: player or DM?** *Settled:* the ghost's `PlayerRoom` row was set to
`Role.DM`, since it has to see the whole board to answer questions about it.
An invite alone only grants `Role.PLAYER`, which means seeing the board through
fog of war.

**Read-only or acting?** Perceiving the map needs only the receive half.
Moving tokens means emitting shape events, which is where a mistake becomes
visible to everyone in the session — `GhostConfig.dry_run` logs intended emits
without sending them, and is worth leaving on while the intent parser is new.

**Dice attribution.** `Dice.Roll.Result` is a pure relay: the server never
rolls and never checks the `player` field, so `roll_dice(..., as_player=...)`
puts the result under someone else's name. That is what makes voice-only play
possible ("roll me a d20" showing up as *that* player's roll), and it also
means every dice result in PlanarAlly is only as trustworthy as the client that
sent it. The missing piece is a map from enrolled voices to PA usernames, which
the speaker-ID stage in `voice/speaker_id.py` can feed directly.

**Fixed board vs virtual.** The board-game work assumed a projector plus
physical pieces read by camera. If the D&D table keeps that, the AprilTag
findings apply directly, including that **the projector paints over tags and
wrecks their contrast** — measured on this rig. If the D&D version is
screen-only, the whole vision layer drops out.

## Client UX changes (fork of `client/`)

Mods can only register shape tabs and shape context-menu entries, so anything
else has to be a change to the Vue client. Rebuild with `npm run build` in
`client/`, which writes `server/static/vite/` and `server/templates/index.html`.
That script **deletes the served bundle before building**, so back both up first
— a failed build otherwise takes the running server down.

What was measured across `client/src` before the changes, not guessed:

- 43 distinct hardcoded hex colours, zero design tokens (`#82c8a0` × 64)
- 85 clickable `<div>`/`<span>`/`<li>` against 91 real `<button>`s
- 21 `aria-*` attributes total, against 151 `title=` tooltips
- 25 `outline: none` against 14 `:focus` rules
- ~20 keyboard shortcuts, none discoverable in-app

Changed:

- **`styles/tokens.css`** — semantic palette, radii, spacing, a global
  `:focus-visible` ring and a `prefers-reduced-motion` block. Additive, so
  unmigrated components are unaffected. Note `--pa-accent` (#82c8a0) is ~1.9:1
  on white: fine as a fill, never for text — that's what `--pa-accent-ink` is.
- **Asset browser** — no longer closes when a drag leaves it. That behaviour was
  a workaround for the panel covering the board, which made placing twenty
  assets mean opening the browser twenty times. There is now a **dock toggle**
  (persisted in `localStorage`) that pins it to the right edge, and the drag
  state is a reactive flag instead of `document.getElementById("layers").style`.
- **Toolbar** — Build/Play is a real `radiogroup` of two buttons instead of one
  `<div>` that toggled; FP/LOS/INI are labelled `aria-pressed` buttons instead
  of unlabelled abbreviations; tools are `<button>`s instead of `<a href="#">`;
  and the `--detailBottom: 7.8rem | 6.6rem` magic number is gone — the bar and
  its detail panel are flex siblings that measure themselves.
- **`?` overlay** — lists every binding, rendered from
  `game/input/keyboard/bindings.ts`, with an entry in the menu since `?` is
  itself undiscoverable. The table is documentation, not dispatch; adding a
  branch in `down.ts` means adding a row there.

### Creatures and cantrips (`scc` v0.4.0)

- **Beast class** (d10, STR/CON saves, Keen Smell) plus **natural weapons** —
  claws 2d6 slashing, bite 1d8 piercing, hooves 1d6 bludgeoning. Listed in
  their own group in the weapon picker so a creature isn't rummaging through a
  weapon rack, but not class-restricted.
- **Cantrips follow the ranged weapon rules**: attack roll vs AC, and
  disadvantage while a hostile creature is within 5 ft. Melee spell attacks
  (Shocking Grasp) are exempt — that's `derived.cantrip.closeRangeDisadvantage`,
  so the intent layer asks the sheet rather than hardcoding the rule.
  Cantrip damage scales at 5/11/17 and takes **no** ability modifier — easy to
  get wrong by copying the weapon path.
- Casting ability comes from the class (`spellcastingAbility`), overridable per
  sheet via `spellAbility`, which is what lets a bear cast without a caster
  class.
- Every attack now carries `attack`, `attackAdvantage` and `attackDisadvantage`
  as ready notation, so the ghost rolls advantage without doing arithmetic:

```python
await sheet.roll_attack(client, uuid, "melee",   bias="advantage",    as_player="sampo")
await sheet.roll_attack(client, uuid, "cantrip", bias="disadvantage", as_player="sampo")
```

`ghost/dice.py` parses the keep-highest/lowest form (`2d20kh1+5`) and shows the
discarded die in parentheses. `advantage()` / `disadvantage()` rewrite a plain
d20 roll and refuse anything that isn't a d20.

Both the catalogue and the sheet self-migrate: the catalogue backfills new
default entries by id under a `version` bump (edits and deletions are left
alone), and a sheet fills in any field a newer schema added. Without that, a
sheet saved by v0.3.0 has no `equipped.cantrip` and `v-model` throws.

### Advantage / disadvantage in PA's dice tool

The tool could already *express* `2d20kh1` — via Advanced → keep → highest → 1,
six steps, with the words "advantage" and "disadvantage" appearing nowhere.
`game/systems/dice/dx.ts` gained `getRollBias`/`setRollBias`, and DiceCore has
two toggle buttons. The state is **derived from the expression**, not stored
alongside it, so it stays honest when a roll is typed by hand or recalled from
history — and only the exact `2d20k[hl]1` shape counts as biased, so a
hand-built `4d20kh2` isn't mislabelled.

## Voice commands

The console is a text box standing in for the microphone. Today you type
`elf ranged attack on goblin`; later whisper writes the same string into the
same `Console.handle()` call and nothing downstream changes. Keeping the seam
there is what makes the chain testable without saying anything out loud.

```
server/.venv/bin/python -m ghost          # console on http://127.0.0.1:8770/
server/.venv/bin/python -m ghost --dry-run --no-speech
```

Password comes from `~/.config/planarally-ghost/password` (0600) or
`$GHOST_PASSWORD`. Deliberately not `/tmp` — that was cleared on a reboot and
took the previous copy with it.

| module | does |
|---|---|
| `grid.py` | cell ↔ pixel maths, ported from `client/src/core/grid`. Square + both hex orientations |
| `battlefield.py` | cell view of the board: occupants, walls, hazards |
| `movement.py` | BFS walk into reach, with the three stop conditions |
| `commands.py` | text → `Intent`. Deterministic, not model-driven |
| `actions.py` | executes an Intent, returns narration |
| `console.py` | the text box, and the entry point voice will share |
| `narrate.py` | optional Kokoro read-back, off the event loop |

**The grid maths is a port, not an integration.** If
`client/src/core/grid/index.ts` changes, `grid.py` is silently wrong and tokens
land a cell off. Round-trip tested against all three grid types.

**Parsing is deterministic on purpose.** The board-game half already learned
that a 4B model asked to choose between similar proper nouns loses to lexical
similarity; character names are exactly that case. The SLM belongs *in front*
of `parse()`, normalising free speech into one of its shapes. An unparsed
command says so rather than guessing — a mis-parse that attacks the wrong
creature costs the game.

### Dangerous terrain

PlanarAlly has no such concept. Shapes carry `movement_obstruction` (a wall)
and nothing about what standing somewhere costs you, so `battlefield.py`
defines it: a room DataBlock of shape uuids, plus name-keyword matching
(`lava`, `fire`, `spike`, `trap`, `pit`, …) so a DM who labels a hazard gets
the behaviour for free. A shape called "campfire" will match. That is the right
failure direction — refusing to walk somewhere is recoverable, walking a
character into a fire pit is not.

Hazards are **stopped at, not routed around** — the caller asked for "stop if
about to walk into dangerous terrain", and detouring through a corridor the
player never intended is a different action from the one they asked for. Walls
*are* routed around, because going around a wall is what walking is.

Melee therefore resolves as: plan → walk → if not in reach, hold the attack and
say why.

### Vision, measuring, hazards, and the combat log

**Line of sight.** `battlefield.opaque` is built from PlanarAlly's
`vision_obstruction`, and ranged attacks and cantrips are refused without it —
melee isn't checked, you're standing next to the thing. Creatures deliberately
do *not* block: in 5e they grant cover, which is a modifier the DM applies, not
a veto the ghost should be issuing. LOS is sampled in pixel space at quarter-cell
steps so one loop is correct for square and both hex orientations.

**Hazards now route around, and ask when they can't.** Two BFS passes: safe
first, and only if that can't arrive does it try again allowing hazards — and
then it *doesn't move*, it returns `NEEDS_CONFIRMATION` with the route and the
hazard's name, and the console asks. Answer `yes`/`no` (or the buttons). If
crossing wouldn't reach either, it doesn't offer the risk at all and just
reports the safe partial progress.

**Measuring.** `measure from elf to goblin` → distance in feet and cells, line
of sight, and a drawn ruler.

> PlanarAlly's ruler publishes its line and label as temporary shapes when
> "show public" is on, but **its grid-mode cell highlighting never syncs** — it
> is painted in a local `postDrawCallback` in `tools/variants/ruler.ts`. On a
> projected table the projector is a separate client, so those highlighted cells
> would simply be absent. `scene.draw_ruler` rebuilds the highlight as one
> translucent temporary rect per cell, which *does* sync — so it's strictly
> better than the built-in tool here: everyone sees the same counted squares.

**Combat log.** The console keeps intent and result as separate fields, not one
blob of prose. After a surprising turn the question is which half went wrong —
did it mishear the command, or misapply the rules — and that's only answerable
if both are visible. Served whole from `GET /log`; last 200 turns.

**Dual input.** The text box and a `Speak` button POST to the same endpoint with
a `source` tag. Speech is a convenience, never the only way in — a player tired
of repeating themselves types, and a demo doesn't die because the room is noisy.
The browser's recogniser is a stand-in; whisper replaces it by calling
`Console.handle(text, source="voice")` and nothing downstream changes.

**Building test geometry** — `scene.py`: `add_block` (walls / hazards),
`add_light` (a token with a vision-source aura), `add_floor`, `draw_ruler`.
Everything defaults to `temporary=True`: those shapes are tracked
per-connection, never written to the database, and vanish when the ghost
disconnects, so test geometry cannot litter a saved campaign. Pass
`permanent=True` to actually build. `bounding_cells()` keeps generated geometry
near the party.

One rect **per cell** rather than one wide rect: `size_x`/`size_y` are the only
footprint the ghost gets back over the socket, and a rect's real width lives in
the opaque `options` blob — so one shape per cell keeps what the ghost believes
and what the players see in agreement.

### Things the live board taught us

Five bugs that only surfaced against the real game, all fixed:

1. **`Locations.Settings.Set` has `active` as a location *id*, not an options
   object.** Treating it as a dict raised `'int' object is not a mapping`, and
   the ghost silently fell back to square/5ft — against a board that is
   **FLAT_HEX at 7 ft per cell**. Every distance would have been wrong. The
   per-location overrides live in `locations[str(active)]`.
2. **Rect footprints.** `size_x`/`size_y` are an *override* and are absent for
   normal shapes; the real extent is pixel `width`/`height`. Without the
   fallback a wall drawn seven cells long occupied one cell and the mover
   walked through it.
3. **Corner vs centre.** PA gives a rect's `x`/`y` as its top-left. On a square
   grid that corner floors into the shape's own cell, so reading it worked by
   luck. On hex it does not — a half-cell offset lands in a *neighbouring* hex,
   so a pillar registered one cell from where it was drawn and line-of-sight
   disagreed with the map. Cells are now sampled at their middles.
4. **The ghost was blind to its own geometry.** The server broadcasts
   `Shape.Add` with `skip_sid`, so the sender never hears its own shape, and
   temporary shapes are never persisted so `Location.Load` doesn't replay them
   either. `scene._add` now records into `client.state` as it emits.
5. **Narration named the wrong things.** Decorative shapes (the ghost's own
   ruler tiles) were reported as obstacles, and hazards were named as blocking
   *sight* — you can see over a lava pool. Only cells that actually block,
   obscure or harm are indexed, and the LOS message filters to opaque ones.

Confirmed working against `sanpo`:

```
> measure from big hamta to gobbo
    big hamta to gobbo: 42 feet (6 cells), no line of sight.
> big hamta ranged attack on gobbo
    big hamta has no line of sight to gobbo — the stone pillar is in the way.
> haltija ranged attack on gobbo with advantage
    haltija attacks gobbo with advantage: 16 to hit [(9), 14] +2.
    That hits AC 10 for 7 damage.
    gobbo drops to 0 hit points.
```

### The rest of what the password had blocked — and what it cost

Creating geometry, lights and floors had been written but never run. Running it
found that **none of it worked**, and that the previous session's "it works"
was wrong:

- **Every `Shape.Add` was being rejected.** `ApiCoreShape` requires `variants`,
  which was missing. `Shape.Add` is fire-and-forget — the server validates,
  logs, and tells the sender nothing — so the failure was invisible. Worse, the
  ghost's own local bookkeeping (added so it could see its own shapes) reported
  `blocked=1 opaque=1` from state that existed only in its head. **Local
  tracking masked a total server-side failure.** Anything emitted this way needs
  a read-back to be believed.
- **Auras needed `shape` and `flood_light`, and integer radii.** The light was
  never created either.
- **Aura `value`/`dim` are in campaign units (feet), not pixels.** Converting
  made a 20ft torch light 28ft of corridor. The existing lights on this board
  store `20|20`, which is what gave it away.
- **`Shapes.Remove` takes `{uuids, temporary}`,** not a bare list. A bare list
  is dropped silently, so a failed cleanup looks exactly like a successful one —
  which is how two test shapes were left on the live board.
- **Per-location settings clobbered the room defaults.** `ApiOptionalLocationOptions`
  uses `None` for "inherit", and a plain `dict.update()` treated those Nones as
  values, reverting the ghost to a square 5ft grid on a hex board at 7ft.
  `load_board` now warns loudly if grid settings never arrive, because being
  wrong here is undetectable downstream.

**A floor deletion stranded a character token.** `Floor.Remove` is
`delete_instance(recursive=True)`, and a shape's layer FK is nullable — so
peewee *nulls* it rather than cascading. The shapes are not deleted, they are
orphaned: `layer_id = NULL` renders nowhere, `Location.Load` never sends them,
and `Shapes.Layer.Change` refuses to move a shape that has no layer. There is
no route back through the app.

`gobbo` was lost this way and recovered with `ghost.repair_orphans` (dry-run by
default, `--apply` to write; only ever assigns a layer to shapes that have
none). `scene.remove_floor` now refuses to delete a floor with shapes on it
unless forced, and `BoardState.shape_floor` exists so it can tell.

Verified afterwards: 0 layerless shapes, one floor, all four characters on the
board, gobbo restored to 14/14.
