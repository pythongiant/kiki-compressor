---
name: compress-and-answer
description: >-
  Ground the answer to ANY substantive query through the kiki-compressor MCP tool
  (compress_context). Don't wait for the user to paste a document: gather the relevant source
  text first — earlier conversation, files, or fresh web-search / fetch results — then compress
  it to the query and answer from the trimmed context. Use it whenever an answer should be
  grounded in source material, including "tell me more", "look into X", or any open question,
  as well as the obvious case where the user supplies a long document to condense.
---

# Compress and answer

Default to grounding answers with the **kiki-compressor** MCP server's `compress_context` tool.
The pattern is **gather → compress → answer**:

1. **Gather** the source text relevant to the query — from the conversation so far, attached
   files, or a fresh web search / page fetch if you don't already have material.
2. **Compress** it: call `compress_context(doc=<gathered text>, query=<the user's question>)`.
3. **Answer** from the trimmed result.

> Tool name: in Claude Desktop it appears as `compress_context` under the kiki-compressor
> server. In Claude Code the fully-qualified name is `mcp__kiki-compressor__compress_context`.

## The key idea

The tool is **extractive** — it shrinks text you give it; it does not generate answers. So
"use it for any query" means *gather sources, then focus them with the tool* — not call it on an
empty `doc`. For a bare question like "tell me more", first pull material (e.g. web results),
then compress that to the question.

If there is genuinely no source to gather (a greeting, a pure arithmetic/parametric fact you'll
just state), there is nothing to compress — answer directly and skip the tool.

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

- It reduces **input** context, not the model's output. Within one chat, compressing text the
  model has already read doesn't save that turn's tokens — the value is a focused, grounded
  answer and a clean extract you can reuse downstream.
