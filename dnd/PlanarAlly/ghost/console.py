"""A text box for commands, standing in for the microphone.

This is the injection point for the voice pipeline. Today a human types
"elf ranged attack on goblin"; later whisper writes the same string into the
same `handle()` call and nothing downstream changes. Keeping the seam here --
rather than wiring speech straight into the executor -- is what makes the whole
chain testable without saying anything out loud.

It is served by aiohttp on the ghost's own event loop, not the stdlib threading
server used by `voice/ui_server.py`, because handling a command means awaiting
socket round-trips to PlanarAlly.

Unauthenticated and bound to localhost by default: it can move other people's
tokens and change their hit points, so it should not be reachable from the LAN
without a good reason.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from aiohttp import web

from .actions import Outcome, Pending, execute
from .client import GhostClient
from .sheet import read_sheet as sheet_read
from .commands import Action, ParseError, parse

log = logging.getLogger(__name__)

Narrator = Callable[[str], Awaitable[None]]

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ghost console</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #ffffff; --fg: #1c1c1c; --muted: #5c5c5c;
    --surface: #f5f5f5; --line: #dddddd;
    --brand: #7c253e; --ok: #1f7a4d; --bad: #a82929; --ask: #d98324;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #16161a; --fg: #ececf0; --muted: #a0a0a8;
            --surface: #22222a; --line: #33333d; }
  }
  * { box-sizing: border-box; }
  body { font: 16px/1.5 system-ui, -apple-system, sans-serif; margin: 0;
         padding: 1.5rem; max-width: 54rem; margin-inline: auto;
         background: var(--bg); color: var(--fg); }
  h1 { font-size: .8rem; letter-spacing: .1em; text-transform: uppercase;
       color: var(--muted); margin: 0 0 .75rem; }
  .bar { display: flex; gap: .5rem; align-items: stretch; }
  input[type=text] { flex: 1; padding: .65rem .9rem; font: inherit;
      border: solid 2px var(--brand); border-radius: 8px;
      background: var(--bg); color: var(--fg); }
  button { padding: .65rem 1.1rem; font: inherit; font-weight: 700;
      cursor: pointer; border: solid 2px var(--brand); border-radius: 8px;
      background: var(--brand); color: #fff; }
  button.ghost { background: transparent; color: var(--fg); }
  button.ghost[aria-pressed=true] { background: var(--bad); border-color: var(--bad); color: #fff; }
  button:disabled { opacity: .45; cursor: default; }
  :focus-visible { outline: solid 2px #2b6cb0; outline-offset: 2px; }
  .hint { color: var(--muted); font-size: .85rem; margin: .5rem 0 0; }
  .ask { margin-top: .9rem; padding: .7rem .9rem; border-radius: 8px;
         border-left: solid 4px var(--ask); background: var(--surface); }
  .ask .row { display: flex; gap: .5rem; margin-top: .5rem; }

  h2 { font-size: .8rem; letter-spacing: .1em; text-transform: uppercase;
       color: var(--muted); margin: 1.75rem 0 .5rem;
       border-bottom: solid 1px var(--line); padding-bottom: .3rem; }
  #log { display: flex; flex-direction: column-reverse; gap: .5rem; }
  .entry { border: solid 1px var(--line); border-left: solid 4px var(--muted);
           border-radius: 8px; padding: .6rem .8rem; background: var(--surface); }
  .entry.ok  { border-left-color: var(--ok); }
  .entry.bad { border-left-color: var(--bad); }
  .entry.ask { border-left-color: var(--ask); }
  .entry header { display: flex; gap: .5rem; align-items: baseline;
                  flex-wrap: wrap; margin: 0; padding: 0; background: none; }
  .n { color: var(--muted); font-variant-numeric: tabular-nums; font-size: .8rem; }
  .cmd { font-weight: 700; }
  .src { font-size: .7rem; text-transform: uppercase; letter-spacing: .06em;
         padding: .05rem .4rem; border-radius: 999px;
         border: solid 1px var(--line); color: var(--muted); }
  .intent { margin: .35rem 0 .1rem; font-size: .85rem; color: var(--muted);
            font-family: ui-monospace, monospace; }
  .result { margin: 0; padding-left: .9rem; border-left: solid 2px var(--line); }
  .result div + div { margin-top: .1rem; }
  .empty { color: var(--muted); font-style: italic; }
</style>
</head>
<body>
  <h1>Ghost console</h1>

  <form id="f" class="bar" autocomplete="off">
    <label for="cmd" style="position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)">Command</label>
    <input id="cmd" type="text" placeholder="elf ranged attack on goblin" autofocus>
    <button id="go" type="submit">Run</button>
    <!-- Dual input. Speech is a convenience here, never the only way in: a
         player tired of repeating themselves can type, and a demo does not die
         because the room is noisy. -->
    <button id="mic" class="ghost" type="button" aria-pressed="false"
            title="Dictate a command">Speak</button>
  </form>
  <p class="hint">Try <code>help</code>, or <code>measure from elf to goblin</code>.
     Typing and speech go through exactly the same pipeline.</p>

  <div id="ask" class="ask" hidden>
    <div id="ask-text"></div>
    <div class="row">
      <button id="yes" type="button">Yes, walk into it</button>
      <button id="no" class="ghost" type="button">No</button>
    </div>
  </div>

  <h2>Combat log</h2>
  <div id="log" aria-live="polite"><div class="empty">Nothing yet.</div></div>

<script>
const $ = (id) => document.getElementById(id);
const form = $('f'), input = $('cmd'), go = $('go'), mic = $('mic');
const logEl = $('log'), askEl = $('ask'), askText = $('ask-text');

function describeIntent(i) {
  if (!i) return 'not understood';
  const bits = [i.action];
  if (i.kind) bits.push(i.kind);
  if (i.actor) bits.push('actor=' + i.actor);
  if (i.target) bits.push('target=' + i.target);
  if (i.bias && i.bias !== 'normal') bits.push(i.bias);
  return bits.join('   ');
}

function render(entries) {
  logEl.textContent = '';
  if (!entries.length) {
    const e = document.createElement('div');
    e.className = 'empty'; e.textContent = 'Nothing yet.';
    logEl.appendChild(e);
    askEl.hidden = true;
    return;
  }
  let awaiting = null;
  for (const en of entries) {
    const el = document.createElement('div');
    el.className = 'entry ' + (en.awaiting ? 'ask' : en.ok ? 'ok' : 'bad');

    const head = document.createElement('header');
    const n = document.createElement('span');
    n.className = 'n'; n.textContent = '#' + en.n;
    const cmd = document.createElement('span');
    cmd.className = 'cmd'; cmd.textContent = en.command;
    const src = document.createElement('span');
    src.className = 'src'; src.textContent = en.source;
    head.append(n, cmd, src);

    // Intent and result are separate rows on purpose: when a turn surprises
    // you, the first question is whether it misheard you or misapplied the
    // rules, and that is only answerable if both halves are visible.
    const intent = document.createElement('div');
    intent.className = 'intent'; intent.textContent = describeIntent(en.intent);

    const result = document.createElement('div');
    result.className = 'result';
    for (const line of en.lines) {
      const d = document.createElement('div'); d.textContent = line;
      result.appendChild(d);
    }
    el.append(head, intent, result);
    logEl.appendChild(el);
    if (en.awaiting) awaiting = en;
  }
  if (awaiting) {
    askText.textContent = awaiting.lines[awaiting.lines.length - 1] || 'Confirm?';
    askEl.hidden = false;
  } else {
    askEl.hidden = true;
  }
}

async function send(cmd, source) {
  if (!cmd) return;
  go.disabled = true;
  try {
    await fetch('command', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd, source: source }) });
    await refresh();
  } catch (err) {
    alert('Could not reach the ghost: ' + err);
  } finally {
    go.disabled = false; input.focus();
  }
}

async function refresh() {
  try {
    const r = await fetch('log');
    render((await r.json()).entries || []);
  } catch (err) { /* the ghost may be restarting; the next poll will catch up */ }
}

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const cmd = input.value.trim();
  input.value = '';
  send(cmd, 'text');
});
$('yes').addEventListener('click', () => send('yes', 'text'));
$('no').addEventListener('click', () => send('no', 'text'));

// Browser speech recognition, standing in until whisper is wired in. It POSTs
// to the same endpoint, so nothing downstream can tell the two apart.
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SR) {
  mic.disabled = true;
  mic.title = 'This browser has no speech recognition; whisper will fill this in';
} else {
  const rec = new SR();
  rec.lang = 'en-GB'; rec.interimResults = false; rec.continuous = false;
  let listening = false;
  mic.addEventListener('click', () => { listening ? rec.stop() : rec.start(); });
  rec.addEventListener('start', () => {
    listening = true; mic.setAttribute('aria-pressed', 'true'); mic.textContent = 'Listening';
  });
  rec.addEventListener('end', () => {
    listening = false; mic.setAttribute('aria-pressed', 'false'); mic.textContent = 'Speak';
  });
  rec.addEventListener('result', (e) => {
    const said = e.results[0][0].transcript.trim();
    input.value = said;
    send(said, 'voice');
  });
}

refresh();
setInterval(refresh, 4000);
</script>
</body>
</html>
"""


class Console:
    def __init__(
        self,
        client: GhostClient,
        host: str = "127.0.0.1",
        port: int = 8770,
        narrator: Narrator | None = None,
    ):
        self.client = client
        self.host = host
        self.port = port
        # Where kokoro plugs in. Left injectable so the console runs with no
        # audio stack present, which is most of the time while developing.
        self.narrator = narrator
        self._runner: web.AppRunner | None = None
        # An action held back on a yes/no. Single-slot on purpose: a queue
        # of pending questions is a way to answer the wrong one.
        self._pending: Pending | None = None
        self.log: list[dict] = []
        self._seq = 0
        # Let the client push its own observations into this log.
        client.on_narration = self._note

    async def handle(self, text: str, source: str = "text") -> Outcome:
        """Parse and run one command. The voice pipeline calls this too.

        Anything that is not already valid syntax is handed to the cluster to be
        translated, so the panel on the board accepts "back the elf off to the
        southwest" as readily as the exact command. Exact syntax never reaches
        the cluster: it parses locally in microseconds, and a two-second round
        trip to be told what we already knew would make the common path the slow
        one.
        """
        original = text
        try:
            intent = parse(text)
        except ParseError as first_error:
            translated = await self._translate(original, source)
            if translated is not None:
                return translated
            return self._record(text, source, None, Outcome(False, [str(first_error)]))

        # Parsing is not the same as making sense. The grammar is deliberately
        # permissive about names -- it has to be, it does not know who is on the
        # board -- so "back the elf off from the hamster, head southwest" parses
        # happily into a retreat by a character called "back elf off from
        # hamster,". That used to fail with a baffling not-found error while the
        # translator, which would have got it right, was never consulted. If the
        # names do not resolve, treat it as prose rather than as a command.
        if source.endswith("+nl") is False and self._unresolved(intent):
            translated = await self._translate(original, source)
            if translated is not None:
                return translated

        # A yes/no only means something while a question is open, and it
        # answers *that* question -- it is never a command in its own right.
        held, self._pending = self._pending, None
        accept = False
        if intent.action in (Action.CONFIRM, Action.CANCEL):
            if held is None:
                return self._record(text, source, intent, Outcome(False, ["Nothing to confirm."]))

            # Either answer ends the question, so either answer clears its
            # marker. A highlight left behind outlives the thing it was asking
            # about and turns into scenery nobody can account for.
            await self._clear_markers(held)

            if intent.action is Action.CANCEL:
                return self._record(
                    text, source, intent,
                    Outcome(True, [f"Held. {held.question} -- not doing it."]),
                )

            if held.move_to:
                return self._record(text, source, held.then or held.intent,
                                    await self._walk_then_act(held))

            intent, accept = held.intent, True

        log.info("command: %s -> %s", text, intent)

        # The HTTP server outlives the socket: PlanarAlly restarting, or a
        # network blip, leaves the console answering while every command
        # fails with "/planarally is not a connected namespace". Reconnect
        # rather than making someone notice and restart the process.
        if not await self._ensure_connected():
            return self._record(
                text, source, intent,
                Outcome(False, ["Lost the connection to PlanarAlly and could not get it back."]),
            )

        try:
            outcome = await execute(self.client, intent, accept_hazard=accept)
        except Exception as e:  # noqa: BLE001 - a bad command must not kill the console
            log.exception("command failed")
            return self._record(text, source, intent, Outcome(False, [f"That went wrong: {e}"]))

        self._pending = outcome.pending

        if self.narrator is not None and outcome.lines:
            try:
                await self.narrator(outcome.text)
            except Exception:  # noqa: BLE001 - narration is not worth failing over
                log.exception("narration failed")
        return self._record(text, source, intent, outcome)

    async def _ensure_connected(self) -> bool:
        if self.client.sio.connected:
            return True
        log.warning("socket is down; reconnecting")
        try:
            await self.client.connect()
            # Board state went stale the moment the socket dropped, and
            # acting on stale positions is worse than refusing.
            await self.client.load_board()
        except Exception:  # noqa: BLE001
            log.exception("reconnect failed")
            return False
        log.info("reconnected")
        return True

    async def _on_state(self, request: web.Request) -> web.Response:
        """The board as facts, for whatever is writing the commands.

        Serves both shapes: `?format=text` returns the table meant to be pasted
        into a prompt, and the default JSON is for anything that wants to do its
        own thing with it. The text form is the point -- it exists so the model
        stops having to invent distances.
        """
        from . import worldstate

        try:
            state = await worldstate.snapshot(self.client)
        except Exception as exc:  # noqa: BLE001 - a broken snapshot must not 500 the console
            log.exception("could not build world state")
            return web.json_response({"error": str(exc)}, status=503)

        if request.query.get("format") == "text":
            return web.Response(text=worldstate.render(state), content_type="text/plain")
        return web.json_response(state)

    async def _clear_markers(self, held: Pending) -> None:
        if not held.marker_uuids:
            return
        from . import scene

        try:
            await scene.clear_shapes(self.client, held.marker_uuids, temporary=False)
        except Exception:  # noqa: BLE001 - a stuck marker is not worth losing the answer
            log.exception("could not clear the suggestion marker")

    async def _walk_then_act(self, held: Pending) -> Outcome:
        """Accepting a counter-proposal: go there, then do the thing.

        Re-planned rather than replayed. The route was worked out when the
        question was asked, and between then and now somebody may have moved
        into it -- walking a stale path would shove a token through whoever
        arrived. Asking again for the same destination costs one search and
        cannot walk through anybody.
        """
        from .actions import _build_field, execute
        from .movement import plan_direction  # noqa: F401 - kept for symmetry
        from . import suggest

        actor, target = held.actor_uuid, held.target_uuid
        field = await _build_field(self.client)

        sheet_data = await sheet_read(self.client, actor)
        speed = float((sheet_data or {}).get("speed") or 30)
        spot = suggest.spot_with_sight(
            field, actor, target, field.cells_for_speed(speed), await self._sides()
        )
        if spot is None:
            return Outcome(False, ["That spot is no longer available."])

        from .movement import MovePlan, StopReason, walk

        await walk(self.client, field, actor, MovePlan(spot.path, StopReason.ARRIVED, reached=True))
        moved = Outcome(True, [f"Moved {spot.feet} feet into position."])

        follow = held.then or held.intent
        try:
            after = await execute(self.client, follow)
        except Exception as e:  # noqa: BLE001
            log.exception("follow-up action failed")
            return moved.say(f"Then it went wrong: {e}")

        for line in after.lines:
            moved.say(line)
        moved.ok = after.ok
        self._pending = after.pending
        return moved

    async def _sides(self) -> dict[str, str]:
        from . import worldstate

        factions = await worldstate._factions(self.client)
        return {u: worldstate._side(factions, u) for u in self.client.state.shapes}

    def _unresolved(self, intent) -> bool:
        """True when the intent names somebody who is not on the board."""
        for name in (intent.actor, intent.target):
            if name and self.client.state.find_shape(name) is None:
                return True
        return False

    async def _translate(self, said: str, source: str) -> Outcome | None:
        """Try the cluster. None means "no translation available, report the parse error".

        Every gate that can refuse runs *before* execution, and in this order:
        the model may only answer on one of two channels, the command must name
        people the player actually said, and -- the strongest of the three --
        whoever is acting must be whoever's turn it is. The turn check settles
        what string matching only guesses at: when the order says it is the
        elf's turn, an attack by the hamster is wrong however confidently it was
        produced.
        """
        # Local imports: worldstate reaches into actions, which imports this
        # module, so a top-level import would close the loop.
        from . import nlguard, translate as nl, worldstate

        if nl.cluster_url() is None:
            return None
        if not await self._ensure_connected():
            return None

        result = await nl.translate(self.client, said)
        channel, payload = result["channel"], result["payload"]

        if channel == "error":
            log.warning("translation failed: %s", payload)
            return None
        if channel == "ask":
            return self._record(said, source, None, Outcome(True, [f"[?] {payload}"]))
        if channel == "untagged":
            return self._record(
                said, source, None,
                Outcome(False, [f"I did not understand that. The model said: {payload[:120]}"]),
            )

        characters = list(self.client.state.characters)
        refusal = nl.vet_names(payload, said, characters)
        if refusal:
            return self._record(said, source, None, Outcome(False, [refusal]))

        try:
            intent = parse(payload)
        except ParseError as e:
            return self._record(said, source, None, Outcome(False, [f"{payload!r}: {e}"]))

        active = (await worldstate.snapshot(self.client)).get("turn_of")
        clash = nlguard.wrong_turn(intent.action.value, intent.actor, active)
        if clash:
            return self._record(said, source, intent, Outcome(False, [clash]))

        log.info("translated %r -> %r", said, payload)
        outcome = await self.handle(payload, f"{source}+nl")
        # Show what it was understood as, or a surprising result is impossible
        # to tell apart from a mistranslation. `_record` copies the lines when
        # it builds the entry, so the log has to be amended as well -- mutating
        # only the returned Outcome left the panel showing a result with no
        # sign of what produced it.
        echo = f"[{payload}]"
        outcome.lines.insert(0, echo)
        if self.log:
            self.log[-1]["lines"] = list(outcome.lines)
            self.log[-1]["command"] = said
        return outcome

    async def _note(self, text: str) -> None:
        """Log something the ghost noticed rather than something it was told.

        Shares the log with commands so the sequence reads in the order it
        happened -- a bonus expiring between two attacks belongs between them,
        not in a separate list nobody is watching.
        """
        self._seq += 1
        self.log.append(
            {
                "n": self._seq,
                "source": "ghost",
                "command": None,
                "intent": None,
                "ok": True,
                "awaiting": False,
                "lines": [text],
            }
        )
        del self.log[:-200]

    def _record(self, text, source, intent, outcome: Outcome) -> Outcome:
        """Append to the combat log.

        Intent and result are stored separately rather than as one blob of
        prose, because the useful question after a surprising turn is which
        half went wrong: did it mishear the command, or misapply the rules?
        """
        self._seq += 1
        entry = {
            "n": self._seq,
            "source": source,
            "command": text,
            "intent": None if intent is None else {
                "action": intent.action.value,
                "actor": intent.actor,
                "target": intent.target,
                "kind": intent.kind.value if intent.kind else None,
                "bias": intent.bias,
            },
            "ok": outcome.ok,
            "awaiting": outcome.pending is not None,
            "lines": list(outcome.lines),
        }
        self.log.append(entry)
        # A session's worth of turns, no more; this is a live view, not an
        # archive, and it is served whole on every poll.
        del self.log[:-200]
        return outcome

    async def start(self) -> None:
        # PlanarAlly is served from :8000 and this console from :8770, so
        # every call the in-game panel makes is cross-origin. Without these
        # headers the browser blocks the response and the panel looks dead.
        @web.middleware
        async def cors(request: web.Request, handler):
            if request.method == "OPTIONS":
                response = web.Response(status=204)
            else:
                response = await handler(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            return response

        app = web.Application(middlewares=[cors])
        app.router.add_route("OPTIONS", "/{tail:.*}", lambda _r: web.Response(status=204))
        app.router.add_get("/", lambda _r: web.Response(text=PAGE, content_type="text/html"))
        app.router.add_post("/command", self._on_command)
        app.router.add_get("/log", lambda _r: web.json_response({"entries": self.log}))
        app.router.add_get("/characters", lambda _r: web.json_response({"characters": list(self.client.state.characters)}))
        app.router.add_get("/state", self._on_state)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.host, self.port).start()
        log.info("console on http://%s:%d/", self.host, self.port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    async def _on_command(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return web.json_response({"ok": False, "error": "expected JSON"}, status=400)

        text = str(body.get("command", "")).strip()
        if not text:
            return web.json_response({"ok": False, "error": "empty command"}, status=400)

        source = str(body.get("source", "text"))
        await self.handle(text, source=source)
        return web.json_response({"entries": self.log[-1:]})
