import { LlmError, postChatJson } from './client';
import { buildSetupSchema, SETUP_KINDS } from './schema';

export type ResolvedSetup =
  | { kind: 'begin' }
  | { kind: 'names'; names: string[] }
  | { kind: 'unclear'; message: string };

/**
 * Classifies one setup-phase utterance: the "let's begin" cue, or one or more
 * players introducing themselves (e.g. "player 1, Alice, player 2, Bob", or
 * just "I'm Alice"). This used to be decided in Python by a regex over the
 * raw transcript (voice/play_game.py's old _BEGIN_RE) -- a real player could
 * say "begin" and have it misheard as a name, or vice versa, with no way to
 * recover. Moving the decision here follows the same principle resolveMoveIntent
 * already established: Python transcribes and relays; the browser is what
 * decides what a transcript *means*, using the model instead of a keyword
 * match that breaks the moment the wording (or the transcription) isn't exact.
 */
export async function resolveSetupIntent(
  transcript: string,
  signal?: AbortSignal,
): Promise<ResolvedSetup> {
  const trimmed = transcript.trim();
  if (trimmed === '') {
    return {
      kind: 'unclear',
      message: 'Didn\'t catch that -- say your name to join, or "begin" once everyone has.',
    };
  }

  const schema = buildSetupSchema();
  let raw: unknown;
  try {
    raw = await postChatJson(
      schema,
      [
        {
          role: 'system',
          content:
            'You are listening during setup for a board game. A player either ' +
            'says "begin" (or a clear equivalent like "start" or "let\'s go") to ' +
            'start the game, or introduces one or more players by name (e.g. ' +
            '"player 1, Alice, player 2, Bob" or just "I\'m Alice"). Classify the ' +
            'kind as "begin", "names" (listing every name mentioned, in the order ' +
            'said), or "unclear" if it\'s neither.',
        },
        { role: 'user', content: `The player said: "${trimmed}"` },
      ],
      signal,
    );
  } catch (cause) {
    if (cause instanceof LlmError) {
      return { kind: 'unclear', message: cause.message };
    }
    throw cause;
  }

  const parsed = raw as { kind?: string; names?: unknown } | null;
  const kind = parsed?.kind;
  if (!kind || !SETUP_KINDS.includes(kind as (typeof SETUP_KINDS)[number])) {
    return { kind: 'unclear', message: "Didn't catch that -- try again." };
  }

  if (kind === 'begin') return { kind: 'begin' };

  if (kind === 'names') {
    const names = Array.isArray(parsed?.names)
      ? parsed.names.filter((n): n is string => typeof n === 'string' && n.trim() !== '')
      : [];
    if (names.length === 0) {
      return { kind: 'unclear', message: "Didn't catch a name -- try again." };
    }
    return { kind: 'names', names };
  }

  return { kind: 'unclear', message: "Didn't catch that -- try again." };
}
