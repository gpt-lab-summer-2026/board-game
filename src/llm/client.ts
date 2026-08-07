import {
  LLM_BASE_URL,
  LLM_SAMPLING,
  LLM_TIMEOUT_MS,
} from './config';

export type ChatMessage = {
  role: 'system' | 'user' | 'assistant';
  content: string;
};

export class LlmError extends Error {}

/** True once the model has finished loading. 503 while it's still loading. */
export async function health(): Promise<boolean> {
  try {
    const res = await fetch(`${LLM_BASE_URL}/health`, {
      credentials: 'omit',
      signal: AbortSignal.timeout(2000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Sends a grammar-constrained chat completion and returns the parsed JSON
 * object the model produced.
 *
 * `response_format: {type:'json_object', schema}` is the flat form. The nested
 * `{type:'json_schema', json_schema:{schema}}` form works too but has one more
 * level to get wrong; both end up in the same GBNF conversion server-side.
 *
 * credentials stays 'omit': llama.cpp sets Access-Control-Allow-Credentials on
 * its OPTIONS response but not on the actual POST, so 'include' would fail the
 * browser's check on a cross-origin setup.
 */
export async function postChatJson(
  schema: unknown,
  messages: ChatMessage[],
  signal?: AbortSignal,
): Promise<unknown> {
  const timeout = AbortSignal.timeout(LLM_TIMEOUT_MS);
  const combined = signal
    ? AbortSignal.any([signal, timeout])
    : timeout;

  let res: Response;
  try {
    res = await fetch(
      `${LLM_BASE_URL}/v1/chat/completions`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'omit',
        signal: combined,
        body: JSON.stringify({
          messages,
          ...LLM_SAMPLING,
          response_format: {
            type: 'json_object',
            schema,
          },
        }),
      },
    );
  } catch (cause) {
    // AbortSignal.timeout fires TimeoutError; a user cancel fires AbortError.
    const name = (cause as Error)?.name;
    if (name === 'TimeoutError') {
      throw new LlmError(
        'The language model took too long to answer.',
      );
    }
    if (name === 'AbortError') {
      throw new LlmError('Cancelled.');
    }
    throw new LlmError(
      "Couldn't reach the language model. Is scripts/llama-server.sh running?",
    );
  }

  if (!res.ok) {
    // 503 specifically means the model is still loading -- worth saying so,
    // because it resolves itself and looks identical to a crash otherwise.
    throw new LlmError(
      res.status === 503
        ? 'The language model is still loading, try again in a moment.'
        : `Language model returned ${res.status}.`,
    );
  }

  const body = (await res.json()) as {
    choices?: { message?: { content?: string } }[];
  };
  const content = body?.choices?.[0]?.message?.content;
  if (typeof content !== 'string') {
    throw new LlmError(
      'Language model returned an unexpected response shape.',
    );
  }

  try {
    return JSON.parse(content);
  } catch {
    // Shouldn't happen under a grammar, but truncation at max_tokens can cut a
    // reply before the grammar reaches an accepting state.
    throw new LlmError(
      'Language model returned malformed JSON.',
    );
  }
}
