import { findMoves } from '../game/FindMoves';
import { deriveMove } from '../game/rules';
import type { EdgeKind } from '../game/boardDataRestructure';
import { spaceById } from '../game/boardDataRestructure';
import { LlmError, postChatJson } from './client';
import {
  chooseDestination,
  spaceLabel,
} from './heading';
import { matchCityName } from './names';
import {
  SYSTEM_PROMPT,
  buildUserBlock,
  cityIds,
} from './prompt';
import {
  EDGE_KINDS,
  INTENT_ACTIONS,
  buildIntentSchema,
} from './schema';
import { MODE_NOT_STATED } from './schema';
import type { RawIntent } from './schema';

export type ResolvedIntent =
  | {
      kind: 'move';
      destinationId: string;
      mode: EdgeKind;
      cost: number;
      heading: string;
      /**
       * Every space walked through, starting at the player's current position
       * and ending at destinationId. The caller needs this to notice cities
       * passed on the way -- stopping at one to look at its card is a decision
       * only the player can make.
       */
      path: string[];
      steps: number;
      /** Filled in when the player stops short of the city they named. */
      note: string | null;
    }
  | { kind: 'unclear'; message: string };

const UNCLEAR_TEXT: Record<string, string> = {
  no_heading:
    "I didn't catch which place you're heading for. Name a city on the board.",
  ambiguous:
    "I couldn't tell which place you meant. Try naming the city on its own.",
  not_a_move:
    "That didn't sound like a move. Say where you're heading, e.g. \"heading for Hakametsä\".",
};

const schema = buildIntentSchema(cityIds);

/**
 * Turn a free-text move into a concrete destination.
 *
 * The model only ever names a heading and a mode; every rule decision below it
 * -- how far the dice carries you, what it costs, which squares are legal, which
 * one you actually land on -- is deterministic. Output that is grammar-valid is
 * still re-checked here, because a grammar can't prevent a reply being truncated
 * at max_tokens mid-object.
 */
export async function resolveMoveIntent(args: {
  transcript: string;
  currentPlaceId: string;
  money: number;
  lastRoll: number | null;
  uiMode: EdgeKind;
  signal?: AbortSignal;
}): Promise<ResolvedIntent> {
  const transcript = args.transcript.trim();
  if (transcript === '') {
    return {
      kind: 'unclear',
      message: 'Say where you want to go first.',
    };
  }

  let raw: unknown;
  try {
    raw = await postChatJson(
      schema,
      [
        { role: 'system', content: SYSTEM_PROMPT },
        {
          role: 'user',
          content: buildUserBlock({
            transcript,
            currentCityLabel: spaceLabel(args.currentPlaceId),
            uiMode: args.uiMode,
            lastRoll: args.lastRoll,
          }),
        },
      ],
      args.signal,
    );
  } catch (cause) {
    if (cause instanceof LlmError) {
      return { kind: 'unclear', message: cause.message };
    }
    throw cause;
  }

  const parsed = raw as Partial<RawIntent> | null;
  const action = parsed?.action;

  // An exact name/id occurrence in what the player said outranks the model's
  // pick -- see matchCityName. Computed before the unclear check below so it can
  // rescue the "no_heading" case: the model itself agreed this was move-shaped
  // text but missed the place name, which small models do more than you'd like
  // on combined utterances like "roll the dice and move towards X". It does NOT
  // rescue "not_a_move" or "ambiguous" -- a city merely being mentioned ("is it
  // my turn, I'm at Tammela?") isn't reason enough to move a piece when the
  // model was confident this wasn't a move attempt at all.
  const exact = matchCityName(transcript);

  if (!action || !INTENT_ACTIONS.includes(action)) {
    return {
      kind: 'unclear',
      message: UNCLEAR_TEXT.not_a_move,
    };
  }

  if (action === 'unclear') {
    const reason = parsed?.unclear_reason ?? '';
    if (!(reason === 'no_heading' && exact)) {
      return {
        kind: 'unclear',
        message: UNCLEAR_TEXT[reason] ?? UNCLEAR_TEXT.not_a_move,
      };
    }
  }

  const heading = exact ?? parsed?.heading;
  if (
    typeof heading !== 'string' ||
    !cityIds.includes(heading)
  ) {
    return {
      kind: 'unclear',
      message: UNCLEAR_TEXT.no_heading,
    };
  }

  // MODE_NOT_STATED (or anything unrecognised) means the player didn't say how
  // they're travelling, so the mode they already picked in the UI stands. Never
  // infer one: sea costs 100 and flight costs 300, so a guess spends real money.
  const mode: EdgeKind =
    parsed?.mode &&
    parsed.mode !== MODE_NOT_STATED &&
    EDGE_KINDS.includes(parsed.mode as EdgeKind)
      ? (parsed.mode as EdgeKind)
      : args.uiMode;

  const derived = deriveMove(mode, args.money, args.lastRoll);
  if (!derived.ok) {
    return { kind: 'unclear', message: derived.error };
  }

  if (heading === args.currentPlaceId) {
    return {
      kind: 'unclear',
      message: `You're already at ${spaceLabel(heading)}.`,
    };
  }

  const moves = findMoves(args.currentPlaceId, derived.steps, [
    mode,
  ]);
  const candidateIds = [...moves.keys()];
  if (candidateIds.length === 0) {
    return {
      kind: 'unclear',
      message: `There's no ${mode} route out of ${spaceLabel(args.currentPlaceId)} with ${derived.steps} step(s).`,
    };
  }

  const destinationId = chooseDestination(
    candidateIds,
    heading,
    [mode],
  );
  if (destinationId === null) {
    return {
      kind: 'unclear',
      message: `You can't get to ${spaceLabel(heading)} by ${mode} from here.`,
    };
  }

  const arrived = destinationId === heading;
  const path = moves.get(destinationId) ?? [args.currentPlaceId];
  const viaCities = path
    .slice(1, -1)
    .filter(id => spaceById[id]?.kind === 'city')
    .map(spaceLabel);

  let note: string | null = null;
  if (!arrived) {
    note = `Heading for ${spaceLabel(heading)} — got as far as ${
      spaceById[destinationId]?.kind === 'city'
        ? spaceLabel(destinationId)
        : 'an unnamed spot on the route'
    }.`;
  }
  if (viaCities.length > 0) {
    const via = `Passing through ${viaCities.join(', ')}.`;
    note = note ? `${note} ${via}` : via;
  }

  return {
    kind: 'move',
    destinationId,
    mode,
    cost: derived.cost,
    heading,
    path,
    steps: derived.steps,
    note,
  };
}
