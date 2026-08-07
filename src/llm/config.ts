// Connection + sampling settings for the local gemma3 server.
//
// The base URL is relative by default so the browser only ever talks to the
// origin it was served from -- vite.config.ts proxies /llm through to
// llama-server. That means a phone or the projector browser needs no knowledge
// of the Pi's address or the server's port. Override with VITE_LLM_BASE_URL to
// point at a llama-server on another host.
// Optional chaining because import.meta.env only exists under Vite -- without it
// this module throws on import in a plain node runtime, which is where the
// out-of-browser checks run.
export const LLM_BASE_URL: string =
  import.meta.env?.VITE_LLM_BASE_URL ?? '/llm';

export const LLM_SAMPLING = {
  // Low, not zero: the grammar already restricts output to valid tokens, so
  // there's nothing to gain from sampling variety -- we want the single best
  // reading of what the player said.
  temperature: 0.15,
  top_p: 0.9,
  // The whole reply is ~20 tokens ({"action","heading","mode"}). This is a
  // runaway guard, not a target.
  max_tokens: 64,
} as const;

// Measured on this Pi: a call takes ~25-31s without prompt-cache reuse, and
// llama-server's own read/write timeout defaults to 3600s, so this ceiling is
// entirely client-side. Keep well clear of real latency -- an earlier 30s
// value sat *below* it and turned slow-but-successful calls into failures.
export const LLM_TIMEOUT_MS = 60_000;
