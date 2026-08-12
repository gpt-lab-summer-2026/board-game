import { LlmError, postChatJson } from './client';
import { buildActionSchema } from './schema';

export type ResolvedAction =
  | { kind: 'action'; action: string }
  | { kind: 'unclear'; message: string };

/**
 * Classifies a spoken command against a fixed menu of valid actions for
 * whatever the current game state actually accepts (e.g. ["pay", "wait",
 * "skip"] at an unclaimed card, or just ["continue"] during an enslaved
 * turn). Used for every narrow-menu voice interaction in useVoiceControl.ts
 * so a player doesn't have to say an exact keyword -- "I'll take it", "let's
 * wait and see", "nah, skip that one" should all resolve the same as the
 * literal word would, the same way resolveMoveIntent already tolerates
 * phrasing around a move instead of requiring an exact city name alone.
 */
export async function resolveActionIntent(
  transcript: string,
  validActions: readonly string[],
  signal?: AbortSignal,
): Promise<ResolvedAction> {
  const trimmed = transcript.trim();
  if (trimmed === '') {
    return {
      kind: 'unclear',
      message: `Didn't catch that -- try saying one of: ${validActions.join(', ')}.`,
    };
  }

  const schema = buildActionSchema(validActions);
  let raw: unknown;
  try {
    raw = await postChatJson(
      schema,
      [
        {
          role: 'system',
          content:
            'You are interpreting one spoken command in a board game. ' +
            'Reply with exactly one of the allowed actions if the player ' +
            'clearly meant it, even if their wording differs from the ' +
            'action\'s name, or "unclear" if you genuinely cannot tell. ' +
            'Do not guess when unsure.',
        },
        {
          role: 'user',
          content: `Allowed actions: ${validActions.join(', ')}.\nThe player said: "${trimmed}"`,
        },
      ],
      signal,
    );
  } catch (cause) {
    if (cause instanceof LlmError) {
      return { kind: 'unclear', message: cause.message };
    }
    throw cause;
  }

  const action = (raw as { action?: string } | null)?.action;
  if (typeof action === 'string' && validActions.includes(action)) {
    return { kind: 'action', action };
  }
  return {
    kind: 'unclear',
    message: `Didn't catch that -- try saying one of: ${validActions.join(', ')}.`,
  };
}
