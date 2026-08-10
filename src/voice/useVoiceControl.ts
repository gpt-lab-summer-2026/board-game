import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { resolveActionIntent } from '../llm/action';
import { resolveSetupIntent } from '../llm/setup';
import { matchCityName } from '../llm/names';
import type { GameState, GameStatsHandle } from '../game/GameStats';
import type { EdgeKind } from '../game/boardDataRestructure';
import type { PlayerStatus } from '../game/rules';
import RollDice from '../game/RollDice';
import {
  connectVoiceTranscripts,
  type VoiceConnection,
  type VoiceStatus,
  type VoiceTranscript,
} from './transcript';

// Matches a leading roll instruction up through its connector ("and"/"then"/a
// comma), e.g. "Roll the dice and move towards X" -> strips "Roll the dice
// and ", leaving "move towards X". Deliberately doesn't require the literal
// word "roll" to be spelled exactly right on its own -- see stripRollPrefix.
const ROLL_PREFIX_RE = /^.*?\broll\w*\b.*?(?:,|\band\b|\bthen\b)\s*/i;

/**
 * "Roll the dice and move towards Rautatieasema" -> "move towards
 * Rautatieasema", for handing to resolveMoveIntent (see its call site in this
 * file). Best-effort: if there's no recognizable connector after "roll" --
 * unusual phrasing, or the whole roll instruction got mis-transcribed into
 * something that doesn't contain "roll" at all -- this returns the text
 * unchanged, same as if this function didn't exist.
 */
function stripRollPrefix(text: string): string {
  let stripped = text.replace(ROLL_PREFIX_RE, '');
  // A second connector can be left over -- "roll the dice, THEN head for X"
  // strips through the comma first (leftmost match wins), leaving "then" stuck
  // to the front of what should be a clean move phrase.
  stripped = stripped.replace(/^(?:and|then)\s+/i, '');
  return stripped.trim() === '' ? text : stripped;
}

type VoiceControlPlayer = {
  name: string;
  money: number;
  status: PlayerStatus;
};

type UseVoiceControlArgs = {
  gameState: GameState;
  setGameState: (state: GameState) => void;
  currentPlayer: VoiceControlPlayer | undefined;
  llmPending: boolean;
  setLlmPending: (pending: boolean) => void;
  hasPendingCard: boolean;
  /** Mirrors the JSX's own pendingMove-panel condition (remainingSteps > 0) --
   * see App.tsx's "Continue moving" / "Stop here" buttons. */
  hasPendingMove: boolean;
  lastRoll: number | null;
  moveMode: EdgeKind;
  /** Resolves a move, exactly like typing into the "type a move" box + clicking Ask.
   * rollOverride lets a caller that just rolled hand over the real value directly,
   * instead of relying on lastRoll -- see App.tsx's askClick doc comment for why. */
  askClick: (transcript: string, rollOverride?: number) => void;
  /** "Continue" during an enslaved turn. */
  onContinueSlaveTurn: () => void;
  /** Pay/wait/skip an unclaimed card, exactly like the three buttons do. */
  onResolveCard: (action: 'pay' | 'wait' | 'skip') => void;
  /** "Continue moving" after declining a card passed en route. */
  onContinueMove: () => void;
  /** "Stop here" after declining a card passed en route. */
  onStopMove: () => void;
  /** Called with a message whenever a voice command was heard clearly enough
   * to classify but didn't resolve to anything actionable in the current
   * state -- e.g. the model itself said "unclear". Without this, that case
   * looked identical to the mic not having heard anything at all. */
  onUnrecognizedVoiceCommand: (message: string) => void;
  gameStatsRef: RefObject<GameStatsHandle | null>;
  rollDiceRef: RefObject<RollDice | null>;
};

export type VoiceControlStatus = {
  /** Whether the websocket to voice/play_game.py is currently connected. */
  connected: boolean;
  /** The latest live pipeline update (see transcript.ts's VoiceStatus), for
   * showing a player when it's actually their moment to talk. Null before
   * anything's arrived, e.g. before play_game.py is even running. */
  voiceStatus: VoiceStatus | null;
};

/**
 * Wires the browser up to voice/play_game.py over its websocket (see
 * transcript.ts). Handles both directions:
 *  - RECEIVING a recognized command and routing it to whatever it should do
 *    (join a player, begin the game, roll, or resolve a move) depending on
 *    the current game phase; and receiving live status updates.
 *  - SENDING whose turn it is now, every time that changes -- Python has no
 *    game-state model of its own, so this is the only way it learns who to
 *    gate the mic to next (see transcript.ts's top comment for why).
 *
 * Every ambiguous decision -- is this utterance a name or "begin"? does "I'll
 * take it" mean pay? -- goes through the model (resolveSetupIntent /
 * resolveActionIntent) rather than a keyword match, the same way moves already
 * go through resolveMoveIntent: a regex only matches the exact words it was
 * written for, and breaks the moment a transcription is a little off or a
 * player phrases things differently. The one deliberate exception is the
 * plain "roll" check on a normal turn, just below -- moves already pay for an
 * LLM call via askClick, so doubling that latency on the single most common
 * utterance to catch a case "roll" already matches almost verbatim isn't
 * worth it.
 *
 * Returns the connection/status info a caller would want to render (e.g. a
 * "listening for Alice..." indicator); everything else is side effects.
 */
export function useVoiceControl({
  gameState,
  setGameState,
  currentPlayer,
  llmPending,
  setLlmPending,
  hasPendingCard,
  hasPendingMove,
  lastRoll,
  moveMode,
  askClick,
  onContinueSlaveTurn,
  onResolveCard,
  onContinueMove,
  onStopMove,
  onUnrecognizedVoiceCommand,
  gameStatsRef,
  rollDiceRef,
}: UseVoiceControlArgs): VoiceControlStatus {
  const voiceConnectionRef = useRef<VoiceConnection | null>(null);
  // Mirrors currentPlayer.name for the websocket's onOpen callback, which fires
  // later, outside of render -- a plain closure over currentPlayer captured
  // when the connection was made would go stale the moment the turn changes.
  const currentPlayerNameRef = useRef<string | null>(null);

  const [connected, setConnected] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);

  const handleVoiceTranscript = async (msg: VoiceTranscript) => {
    // Wraps one model call: sets llmPending for its duration so nothing else
    // (another voice command, a button) fires while it's in flight, mirroring
    // how askClick already guards its own move-resolution call.
    const classify = async <T>(work: () => Promise<T>): Promise<T> => {
      setLlmPending(true);
      try {
        return await work();
      } finally {
        setLlmPending(false);
      }
    };

    if (msg.phase === 'setup') {
      if (llmPending) return;
      // The very first setup event -- necessarily the first player introducing
      // themselves, since nobody's enrolled yet -- doubles as "start": there's
      // no reason to make players say a magic word before introducing themselves.
      if (gameState === 'notStarted') setGameState('starting');

      const result = await classify(() => resolveSetupIntent(msg.text));
      if (result.kind === 'begin') {
        gameStatsRef.current?.triggerBegin();
      } else if (result.kind === 'names') {
        for (const name of result.names) {
          gameStatsRef.current?.addPlayerByName(name);
        }
      } else {
        onUnrecognizedVoiceCommand(result.message);
      }
      return;
    }

    // Playing phase. play_game.py already gated the broadcast to the right
    // player's enrolled voice (verified against whatever player this hook last
    // pushed over the websocket -- see the effect below), so the only thing
    // left to check here is that it's actually their turn in the *game* state.
    if (
      gameState !== 'gameOn' ||
      !currentPlayer ||
      currentPlayer.name !== msg.player ||
      llmPending
    ) {
      return;
    }

    // Captured (escape roll) and waiting-for-card (claim roll) turns only ever
    // take a roll -- there's no move/ask input in either state.
    if (
      currentPlayer.status?.type === 'captured' ||
      currentPlayer.status?.type === 'waitingForCard'
    ) {
      const result = await classify(() => resolveActionIntent(msg.text, ['roll']));
      if (result.kind === 'action') rollDiceRef.current?.roll();
      else onUnrecognizedVoiceCommand(result.message);
      return;
    }

    // Enslaved turn: only "continue" (the turn's only button) does anything.
    if (currentPlayer.status?.type === 'slave') {
      const result = await classify(() => resolveActionIntent(msg.text, ['continue']));
      if (result.kind === 'action') onContinueSlaveTurn();
      else onUnrecognizedVoiceCommand(result.message);
      return;
    }

    // A pending unclaimed card: pay/wait/skip, mirroring the three buttons.
    if (hasPendingCard) {
      const result = await classify(() =>
        resolveActionIntent(msg.text, ['pay', 'wait', 'skip']),
      );
      if (result.kind === 'action') {
        onResolveCard(result.action as 'pay' | 'wait' | 'skip');
      } else {
        onUnrecognizedVoiceCommand(result.message);
      }
      return;
    }

    // Declined a card passed en route: only "continue"/"stop" do anything here.
    if (hasPendingMove) {
      const result = await classify(() =>
        resolveActionIntent(msg.text, ['continue', 'stop']),
      );
      if (result.kind === 'action') {
        (result.action === 'continue' ? onContinueMove : onStopMove)();
      } else {
        onUnrecognizedVoiceCommand(result.message);
      }
      return;
    }

    // Normal turn: a plain "roll" check, not a model call -- see this hook's
    // own doc comment for why this one case stays a fast keyword match.
    const canRollNow =
      lastRoll === null &&
      (moveMode === 'land' ||
        (moveMode === 'sea' && currentPlayer.money >= 100));
    if (canRollNow && /\broll/i.test(msg.text)) {
      // "roll the dice and head for Hakametsä" in one breath: matchCityName is
      // the same free, local (no model call) exact-name check askClick already
      // relies on downstream, reused here just to notice a destination is ALSO
      // named in this utterance. If one is, roll, wait for the real number (not
      // the fire-and-forget onRoll path -- see RollDice.roll's doc comment),
      // then resolve the rest of the same sentence as a move using that number
      // directly. If it's just "roll the dice" alone, this is unchanged: fire
      // the roll and stop, exactly as before.
      if (matchCityName(msg.text)) {
        const rolled = await rollDiceRef.current?.roll();
        if (typeof rolled === 'number') {
          // resolveMoveIntent's prompt was written and exampled entirely on
          // clean move phrases ("fly toward Turtola", "go to X") -- it's never
          // seen "roll the dice and move to X" as input. Rather than teach a
          // small (4B) model a whole new sentence shape it's liable to get
          // right only some of the time, strip the roll instruction first so
          // it only ever sees exactly the phrasing it already handles well.
          askClick(stripRollPrefix(msg.text), rolled);
        }
      } else {
        rollDiceRef.current?.roll();
      }
      return;
    }

    // Anything else is a move attempt -- resolveMoveIntent (the LLM) decides
    // whether it actually understood it, and its own "unclear" result already
    // surfaces a message (see askClick/setLlmMessage in App.tsx), so there's
    // no separate "didn't understand" case to add here.
    askClick(msg.text);
  };
  // Re-assigned every render so the websocket callback (wired up once, below)
  // always dispatches into the latest closure instead of a stale one from
  // whenever the connection was opened. Assigning in its own effect, not
  // inline during render, is what React 19 requires for a ref write.
  const handleVoiceTranscriptRef = useRef(handleVoiceTranscript);
  useEffect(() => {
    handleVoiceTranscriptRef.current = handleVoiceTranscript;
  });

  // Opens the websocket once for the component's lifetime.
  useEffect(() => {
    const connection = connectVoiceTranscripts(
      msg => {
        void handleVoiceTranscriptRef.current(msg);
      },
      msg => setVoiceStatus(msg),
      // Re-sends on every (re)connect, not just the initial one -- a turn
      // change (or a restart clearing it back to null) that lands while the
      // socket happens to be down would otherwise leave play_game.py gating
      // on a stale player until the next actual change (see transcript.ts's
      // onOpen doc comment). Sends unconditionally, including null: play_game.py
      // restarting fresh while this tab stays open (or the other way around)
      // is exactly the case where Python's and the browser's idea of who's
      // current can otherwise disagree indefinitely.
      () => {
        setConnected(true);
        connection.send({
          type: 'current_player',
          player: currentPlayerNameRef.current,
        });
      },
      () => {
        setConnected(false);
        setVoiceStatus(null);
      },
    );
    voiceConnectionRef.current = connection;
    return () => {
      voiceConnectionRef.current = null;
      connection.close();
    };
  }, []);

  // Tells play_game.py whose turn it is now, every time that changes -- ALSO
  // when it becomes null (leaving gameOn, e.g. a restart). Only sending on a
  // real player and staying silent otherwise was the actual bug behind a
  // restarted game still showing the previous game's player: Python has no
  // way to know "there's no one now" if it's never told that explicitly, so
  // it just kept believing whoever was last reported was still current.
  useEffect(() => {
    currentPlayerNameRef.current =
      gameState === 'gameOn' && currentPlayer ? currentPlayer.name : null;
    voiceConnectionRef.current?.send({
      type: 'current_player',
      player: currentPlayerNameRef.current,
    });
  }, [gameState, currentPlayer]);

  return { connected, voiceStatus };
}
