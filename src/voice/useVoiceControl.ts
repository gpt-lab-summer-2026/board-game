import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
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
  hasPendingCard: boolean;
  /** Mirrors the JSX's own pendingMove-panel condition (remainingSteps > 0) --
   * see App.tsx's "Continue moving" / "Stop here" buttons. */
  hasPendingMove: boolean;
  lastRoll: number | null;
  moveMode: EdgeKind;
  /** Resolves a move, exactly like typing into the "type a move" box + clicking Ask. */
  askClick: (transcript: string) => void;
  /** "Continue" during an enslaved turn. */
  onContinueSlaveTurn: () => void;
  /** Pay/wait/skip an unclaimed card, exactly like the three buttons do. */
  onResolveCard: (action: 'pay' | 'wait' | 'skip') => void;
  /** "Continue moving" after declining a card passed en route. */
  onContinueMove: () => void;
  /** "Stop here" after declining a card passed en route. */
  onStopMove: () => void;
  /** Called with a hint message when a voice command was heard clearly enough
   * to route (right player, right turn) but didn't match anything the current
   * state accepts -- e.g. "say roll to escape" during a capture. Without this,
   * an unrecognized command in these narrow-menu states just silently did
   * nothing, which looks identical to the mic not having heard anything at all. */
  onUnrecognizedVoiceCommand: (hint: string) => void;
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
 * Returns the connection/status info a caller would want to render (e.g. a
 * "listening for Alice..." indicator); everything else is side effects.
 */
export function useVoiceControl({
  gameState,
  setGameState,
  currentPlayer,
  llmPending,
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

  const handleVoiceTranscript = (msg: VoiceTranscript) => {
    if (msg.phase === 'setup') {
      // The very first setup event -- necessarily an unrecognized voice, since
      // nobody's enrolled yet -- doubles as "start": there's no reason to make
      // players say a magic word before introducing themselves.
      if (gameState === 'notStarted') setGameState('starting');
      if (msg.event === 'player_joined') {
        gameStatsRef.current?.addPlayerByName(msg.player);
      } else if (/\b(start|begin)\b/i.test(msg.text)) {
        gameStatsRef.current?.triggerBegin();
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

    const isRollCommand = /\broll/i.test(msg.text);

    // Captured (escape roll) and waiting-for-card (claim roll) turns only ever
    // take a roll -- there's no move/ask input in either state -- so a "roll"
    // utterance is the only thing worth routing.
    if (
      currentPlayer.status?.type === 'captured' ||
      currentPlayer.status?.type === 'waitingForCard'
    ) {
      if (isRollCommand) rollDiceRef.current?.roll();
      else onUnrecognizedVoiceCommand('Didn\'t catch that -- say "roll" to roll the dice.');
      return;
    }

    // Enslaved turn: only "continue" (the turn's only button) does anything.
    if (currentPlayer.status?.type === 'slave') {
      if (/\bcontinue\b/i.test(msg.text)) onContinueSlaveTurn();
      else onUnrecognizedVoiceCommand('Didn\'t catch that -- say "continue".');
      return;
    }

    // A pending unclaimed card: pay/wait/skip, mirroring the three buttons.
    if (hasPendingCard) {
      if (/\b(buy|pay)\b/i.test(msg.text)) onResolveCard('pay');
      else if (/\bwait\b/i.test(msg.text)) onResolveCard('wait');
      else if (/\b(skip|leave|decline)\b/i.test(msg.text)) onResolveCard('skip');
      else onUnrecognizedVoiceCommand('Didn\'t catch that -- say "pay", "wait", or "skip".');
      return;
    }

    // Declined a card passed en route: only "continue"/"stop" do anything here.
    if (hasPendingMove) {
      if (/\bcontinue\b/i.test(msg.text)) onContinueMove();
      else if (/\bstop\b/i.test(msg.text)) onStopMove();
      else onUnrecognizedVoiceCommand('Didn\'t catch that -- say "continue" or "stop".');
      return;
    }

    const canRollNow =
      lastRoll === null &&
      (moveMode === 'land' ||
        (moveMode === 'sea' && currentPlayer.money >= 100));
    if (canRollNow && isRollCommand) {
      rollDiceRef.current?.roll();
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
      msg => handleVoiceTranscriptRef.current(msg),
      msg => setVoiceStatus(msg),
      // Re-sends on every (re)connect, not just the initial one -- a turn
      // change that lands while the socket happens to be down would otherwise
      // leave play_game.py gating on a stale player until the next actual
      // turn change (see transcript.ts's onOpen doc comment).
      () => {
        setConnected(true);
        if (currentPlayerNameRef.current) {
          connection.send({
            type: 'current_player',
            player: currentPlayerNameRef.current,
          });
        }
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

  // Tells play_game.py whose turn it is now, every time that changes.
  useEffect(() => {
    currentPlayerNameRef.current =
      gameState === 'gameOn' && currentPlayer ? currentPlayer.name : null;
    if (currentPlayerNameRef.current) {
      voiceConnectionRef.current?.send({
        type: 'current_player',
        player: currentPlayerNameRef.current,
      });
    }
  }, [gameState, currentPlayer]);

  return { connected, voiceStatus };
}
