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
  if (!action || !INTENT_ACTIONS.includes(action)) {
    return {
      kind: 'unclear',
      message: UNCLEAR_TEXT.not_a_move,
    };
  }

  if (action === 'unclear') {
    const reason = parsed?.unclear_reason ?? '';
    return {
      kind: 'unclear',
      message: UNCLEAR_TEXT[reason] ?? UNCLEAR_TEXT.not_a_move,
    };
  }

  // An exact name/id occurrence in what the player said outranks the model's
  // pick -- see matchCityName. Only applied to an already-decided move: if the
  // model said "unclear", a city merely being mentioned ("is it my turn, I'm at
  // Tammela?") is not reason enough to move a piece.
  const exact = matchCityName(transcript);
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

  const candidateIds = [
    ...findMoves(args.currentPlaceId, derived.steps, [
      mode,
    ]).keys(),
  ];
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
  return {
    kind: 'move',
    destinationId,
    mode,
    cost: derived.cost,
    heading,
    note: arrived
      ? null
      : `Heading for ${spaceLabel(heading)} — got as far as ${
          spaceById[destinationId]?.kind === 'city'
            ? spaceLabel(destinationId)
            : 'an unnamed spot on the route'
        }.`,
  };
}
