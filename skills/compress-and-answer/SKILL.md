---
name: compress-and-answer
description: >-
  Before reasoning over a body of source material, run it through the kiki-compressor MCP tool
  (compress_context) FIRST so your thinking happens over the trimmed, query-relevant extract
  instead of the full text. The pattern for ANY substantive query is gather → compress → reason →
  answer: pull the relevant source (earlier conversation, files, or fresh web-search / fetch
  results), compress it to the query, then think and answer from the reduced context. Applies to
  "tell me more", "look into X", any open question, and the obvious case of a long pasted document.
---

# Compress and answer

Default to grounding answers with the **kiki-compressor** MCP server's `compress_context` tool,
and reach for it **early** — compress the source *before* you reason over it, not after. The
pattern is **gather → compress → reason → answer**:

1. **Gather** the source text relevant to the query — from the conversation so far, attached
   files, or a fresh web search / page fetch if you don't already have material.
2. **Compress it FIRST**: call `compress_context(doc=<gathered text>, query=<the user's question>)`
   as the first move after gathering, before any extended analysis.
3. **Reason** over the *compressed* extract — carry the trimmed text forward into your thinking,
   follow-up tool calls, and any notes you persist; leave the raw gathered material behind.
4. **Answer** from that reduced context.

> Tool name: in Claude Desktop it appears as `compress_context` under the kiki-compressor
> server. In Claude Code the fully-qualified name is `mcp__kiki-compressor__compress_context`.

## The key idea

The tool is **extractive** — it shrinks text you give it; it does not generate answers. So
"use it for any query" means *gather sources, then focus them with the tool* — not call it on an
empty `doc`. For a bare question like "tell me more", first pull material (e.g. web results),
then compress that to the question.

If there is genuinely no source to gather (a greeting, a pure arithmetic/parametric fact you'll
just state), there is nothing to compress — answer directly and skip the tool.

**Compress first, then think.** Running the tool early is the whole point: it reduces the context
your *subsequent* reasoning operates on. Once you have the trimmed extract, reason and answer from
it rather than re-reading the full gathered material. In a multi-step or agentic flow, the raw
`doc` you passed in can be dropped from what you carry forward, so every later step — more
thinking, more tool calls, a saved note — works on fewer tokens.

## How to call it

- `doc` — the gathered source text, **verbatim**. The more you give it, the more it can focus.
- `query` — the user's question/instruction, phrased as what the kept text must still answer.
- `ratio` — fraction of tokens to **keep**, in `(0, 1]`. Default `0.5`. Lower = more aggressive.
- `level` — leave at `"phrase"`. Only the optional `t5`/`causal` backends use it; the default
  reranker works at sentence level regardless.

If the tool returns the "needs source text in `doc`" message, you called it without gathering —
go back to step 1, collect material, and try again.

## After calling

1. Briefly show or summarize the **compressed context** (verbatim extracts in original order, so
   quotes/citations stay exact) and note the footer's kept-token ratio.
2. **Answer the question** from the compressed context.
3. If the answer isn't in it, re-run at a **higher** `ratio` (less aggressive) — a relevant span
   may have been pruned — or gather more source text.

## Picking the ratio

- `0.5` — default, keep about half.
- `0.2–0.3` — lots of gathered noise, narrow question.
- `0.7–0.8` — multi-part questions, or when missing a detail is costly (recall over brevity).

## Good to know

- It reduces **input** context, not the model's output (output length is up to the model).
- The full `doc` you pass into the call is still in that one turn's context — compressing text
  already in view doesn't refund that turn. The savings are **forward-looking**: by compressing
  first and reasoning over the result, every step after the compress call carries the smaller
  extract instead of the raw material.
