// Bridges the mic pipeline in voice/ (wake word -> speaker-ID turn gate ->
// faster-whisper) to the browser. ui_server.py already gates each command to
// the right player's enrolled voice before broadcasting it, so a message
// arriving here can be trusted to be that player speaking -- this module just
// has to get the text to whoever's listening.
//
// Built as a relative /voice-ws path (see vite.config.ts's proxy entry) rather
// than a hardcoded host:port, same reasoning as src/llm/config.ts: a phone or
// the projector browser needs no knowledge of the Pi's address.
//
// Bidirectional: the browser also SENDS a `current_player` message whenever
// whose turn it is changes. voice/play_game.py has no game-state model of its
// own -- once "roll the dice" and "move to X" are two separate utterances
// instead of one, only the browser (which runs the actual turn logic) knows
// when a turn really ends, so Python can't keep a reliable turn counter on
// its own the way the older test-harness loop did.
//
// Two message shapes come down the same socket, told apart by "kind" (see
// ui_server.py's broadcast_transcript/broadcast_status): a "transcript" is a
// finished, recognized command; a "status" is a live pipeline update ("waiting
// for the wake word", "recording now") so the UI can show a player when it's
// actually their moment to talk, not just the eventual result.

export type VoiceTranscript = {
  /** Empty during setup -- play_game.py no longer decides who's introducing
   * themselves vs. saying "begin" (see resolveSetupIntent, which now makes
   * that call from `text` alone). Always set during play. */
  player: string;
  text: string;
  /** Which phase of play_game.py's loop this came from. Absent means
   * "playing" -- older/simpler senders (e.g. test_turn_gate.py) don't set it. */
  phase?: 'setup' | 'playing';
};

export type VoiceStatusKind =
  | 'waiting_for_wake_word'
  | 'recording'
  | 'transcribing'
  /** A follow-up window after a command -- play_game.py is listening again
   * without requiring the wake word, up to a small cap (see MAX_FOLLOWUPS). */
  | 'listening_for_followup';

export type VoiceStatus = {
  status: VoiceStatusKind;
  /** Whose turn it is, if known -- absent during setup before anyone's enrolled. */
  player: string | null;
};

export type VoiceConnection = {
  send: (message: unknown) => void;
  close: () => void;
};

function voiceWsUrl(): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}/voice-ws`;
}

/**
 * Connects to the voice websocket. Calls `onTranscript` for each recognized
 * command, `onStatus` for each live pipeline update, and `onOpen` every time
 * the connection (re)establishes -- including reconnects, which matters
 * because a turn change that lands while the socket happens to be down would
 * otherwise leave play_game.py gating on a stale player until the next actual
 * turn change. Reconnects on drop (the Python process restarting, or not
 * having been started yet, shouldn't require a page reload).
 */
export function connectVoiceTranscripts(
  onTranscript: (msg: VoiceTranscript) => void,
  onStatus?: (msg: VoiceStatus) => void,
  onOpen?: () => void,
  onClose?: () => void,
): VoiceConnection {
  const RECONNECT_DELAY_MS = 2000;
  let closed = false;
  let socket: WebSocket | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    if (closed) return;
    socket = new WebSocket(voiceWsUrl());

    socket.onopen = () => onOpen?.();

    socket.onmessage = event => {
      let msg: { kind?: string };
      try {
        msg = JSON.parse(event.data);
      } catch {
        return; // Malformed payload -- nothing sensible to do with it.
      }
      if (msg.kind === 'status') {
        onStatus?.(msg as VoiceStatus);
      } else {
        // No "kind" at all shouldn't happen with the current sender, but
        // falling back to "transcript" keeps this tolerant of older payloads.
        onTranscript(msg as VoiceTranscript);
      }
    };

    socket.onclose = () => {
      onClose?.();
      if (!closed) retryTimer = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    socket.onerror = () => {
      socket?.close();
    };
  };

  connect();

  return {
    send(message: unknown) {
      // Dropped if not currently connected -- acceptable here because the
      // onOpen hook re-sends the latest known value on every reconnect, so a
      // missed send here doesn't strand Python on a stale value for long.
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message));
      }
    },
    close() {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    },
  };
}
