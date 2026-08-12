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
    case 'listening_for_followup':
      return voiceStatus.player
        ? `still listening to ${voiceStatus.player} -- no need to say "hey jarvis" again yet`
        : 'still listening...';
  }
}

function VoiceIndicator({ voice }: { voice: VoiceControlStatus }) {
  return (
    <p className={`voice-indicator ${voice.connected ? 'connected' : 'disconnected'}`}>
      🎤 Voice: {describe(voice)}
    </p>
  );
}

export default VoiceIndicator;
