import type { VoiceControlStatus } from './useVoiceControl';

/** Turns the hook's raw {connected, voiceStatus} into one line a player can
 * glance at to know whether/when to speak. */
function describe({ connected, voiceStatus }: VoiceControlStatus): string {
  if (!connected) return 'not connected (is voice/play_game.py running?)';
  if (!voiceStatus) return 'connected';

  switch (voiceStatus.status) {
    case 'waiting_for_wake_word':
      return voiceStatus.player
        ? `say "hey jarvis", ${voiceStatus.player} -- it's your turn`
        : 'waiting for a player to join -- say "hey jarvis" + your name';
    case 'recording':
      return voiceStatus.player
        ? `recording ${voiceStatus.player}'s command...`
        : 'recording...';
    case 'transcribing':
      return 'transcribing...';
  }
}

/**
 * `thinking` is App.tsx's own llmPending, not part of the hook's status --
 * every kind of voice classification (setup, roll/continue/pay-wait-skip,
 * and moves) shares that one flag, so surfacing it here shows "thinking" for
 * all of them instead of only the move-resolution path that used to be the
 * only place it was visible.
 */
function VoiceIndicator({
  voice,
  thinking,
}: {
  voice: VoiceControlStatus;
  thinking: boolean;
}) {
  return (
    <div className={`voice-indicator ${voice.connected ? 'connected' : 'disconnected'}`}>
      <p className='voice-indicator-status'>
        🎤 Voice: {describe(voice)}
      </p>
      {voice.lastTranscript && (
        <p className='voice-indicator-heard'>
          Heard: “{voice.lastTranscript}”
        </p>
      )}
      {thinking && (
        <p className='voice-indicator-thinking'>🤔 Thinking…</p>
      )}
    </div>
  );
}

export default VoiceIndicator;
