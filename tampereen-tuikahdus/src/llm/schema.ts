import type { EdgeKind } from '../game/boardDataRestructure';

// The model's entire job: name a heading city and a transport mode, or say it
// couldn't tell. Deterministic code does everything else (see intent.ts).
export const INTENT_ACTIONS = ['move', 'unclear'] as const;
export type IntentAction = (typeof INTENT_ACTIONS)[number];

export const EDGE_KINDS: readonly EdgeKind[] = [
  'land',
  'sea',
  'flight',
] as const;

// An explicit named value, not '' , for "the player didn't say how they travel".
// Measured: with an '' sentinel the model answered "land" every time even when
// the player named no mode and the UI was set to sea or flight -- which would
// silently override the player's own button and change what the move costs. A
// named option it has to actively choose is followed far more reliably.
export const MODE_NOT_STATED = 'not_stated';

export const UNCLEAR_REASONS = [
  '',
  'no_heading',
  'ambiguous',
  'not_a_move',
] as const;
export type UnclearReason = (typeof UNCLEAR_REASONS)[number];

/** What the model is asked to emit. Every field is grammar-constrained. */
export type RawIntent = {
  action: IntentAction;
  heading: string;
  mode: EdgeKind | typeof MODE_NOT_STATED;
  unclear_reason?: UnclearReason;
};

/**
 * llama.cpp converts this to a GBNF grammar, so the model physically cannot
 * emit a city or mode outside these enums.
 *
 * Note `required` lists action/heading/mode rather than action alone. A schema
 * that only requires `action` still admits `{"action":"move"}` with no
 * destination at all -- grammar-valid but semantically empty, which is exactly
 * the hole the Python version had. The '' sentinel in each enum keeps "the
 * player didn't say" expressible without making the field optional.
 */
export function buildIntentSchema(cityIds: readonly string[]) {
  return {
    type: 'object',
    additionalProperties: false,
    required: ['action', 'heading', 'mode'],
    properties: {
      action: { type: 'string', enum: [...INTENT_ACTIONS] },
      heading: { type: 'string', enum: [...cityIds, ''] },
      mode: {
        type: 'string',
        enum: [...EDGE_KINDS, MODE_NOT_STATED],
      },
      unclear_reason: {
        type: 'string',
        enum: [...UNCLEAR_REASONS],
      },
    },
  };
}

/**
 * For every narrow-menu voice interaction (pay/wait/skip at a card, continue
 * during a capture/enslavement, continue/stop after declining a card en
 * route, ...): a fixed, small set of valid actions for the *current* state,
 * plus 'unclear'. One schema shape reused everywhere instead of a bespoke one
 * per state -- see src/voice/action.ts.
 */
export function buildActionSchema(validActions: readonly string[]) {
  return {
    type: 'object',
    additionalProperties: false,
    required: ['action'],
    properties: {
      action: { type: 'string', enum: [...validActions, 'unclear'] },
    },
  };
}

export const SETUP_KINDS = ['begin', 'names', 'unclear'] as const;
export type SetupKind = (typeof SETUP_KINDS)[number];

/**
 * Setup-phase classification: is this utterance the "let's begin" cue, or one
 * or more players introducing themselves? Free-text names can't be enumerated
 * up front the way cities/actions are, so `names` stays an open string array
 * rather than an enum -- see src/llm/setup.ts.
 */
export function buildSetupSchema() {
  return {
    type: 'object',
    additionalProperties: false,
    required: ['kind'],
    properties: {
      kind: { type: 'string', enum: [...SETUP_KINDS] },
      names: { type: 'array', items: { type: 'string' } },
    },
  };
}
