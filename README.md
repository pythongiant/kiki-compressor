# kiki-compressor

**Query-guided context compression, served over MCP.**

`kiki-compressor` is a local [Model Context Protocol](https://modelcontextprotocol.io) server
that shrinks a long document down to just the parts relevant to a question. Give it a `doc`,
a `query`, and a `ratio`, and it returns a compressed version of the document that still
answers the query — so you can fit more useful signal into a model's context window and spend
fewer tokens on noise.

It exposes a single tool, `compress_context`, that any MCP client (Claude Desktop, etc.) can
call.

---

## Why

Long contexts are expensive and dilute attention. Most of a retrieved document is usually
irrelevant to the specific question being asked. `kiki-compressor` does **query-aware** pruning:
instead of a generic summary, it keeps the spans that matter *for this query* and drops the rest,
preserving original wording and order.

## How it works

The default backend is a **cross-encoder reranker**. A reranker scores a `(query, passage)` pair
with a single relevance number, so compression happens at the **sentence / passage level**:

1. Split the document into sentences (NLTK `punkt`), optionally grouped into N-sentence windows.
2. Score every unit against the query with the cross-encoder.
3. Greedily keep the highest-scoring units up to a token budget (`ratio` × total tokens).
4. Re-emit the kept units **in their original order**.

The result is verbatim, query-relevant text — never paraphrased or hallucinated.

### Backends

Selected with the `QUITO_MODEL_KIND` environment variable:

| Kind        | Level            | Default model                          | Needs the clone? |
|-------------|------------------|----------------------------------------|------------------|
| `reranker`  | sentence/passage | `cross-encoder/ms-marco-MiniLM-L-6-v2` | no (default)     |
| `t5`        | token            | `google/flan-t5-base`                  | yes              |
| `causal`    | token            | `Qwen/Qwen2-0.5B-Instruct`             | yes              |

`t5` and `causal` are the token-level [QUITO / QUITO-X](https://github.com/Wenshansilvia/attention_compressor)
attention-based methods. They're optional — the reranker backend needs nothing beyond the core
dependencies.

---

## Requirements

- **Python 3.10+** (the code uses `str | None` annotations)
- macOS / Linux / Windows
- ~80 MB download on first run for the default MiniLM reranker

## Setup

```bash
# 1. Virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# 2. Core dependencies
pip install "mcp[cli]" sentence-transformers nltk numpy

# 3. (Optional) extras for the t5/causal backends
pip install scipy matplotlib sentencepiece

# 4. Sentence tokenizer data
python -m nltk.downloader punkt punkt_tab
```

Verify it works:

```bash
python test_smoke.py
```

Expected: it prints the original and compressed text and ends with
`OK: reranker compression working`.

---

## Using it with Claude Desktop

Add the server to your `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "kiki-compressor": {
      "command": "/ABSOLUTE/PATH/TO/context-compressor-mcp/.venv/bin/python",
      "args": ["/ABSOLUTE/PATH/TO/context-compressor-mcp/server.py"],
      "env": {
        "QUITO_MODEL_KIND": "reranker",
        "QUITO_MODEL": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "QUITO_RERANK_WINDOW": "1"
      }
    }
  }
}
```

> `command` **must** point at the venv's Python so the installed dependencies resolve.
> Restart Claude Desktop after editing the config for the `compress_context` tool to appear.

The server speaks stdio by default. For a remote/multi-client deployment, swap `mcp.run()` for
`mcp.run(transport="streamable-http")` in `server.py`.

---

## The `compress_context` tool

```
compress_context(doc, query, ratio=0.5, level="phrase") -> str
```

| Argument | Type    | Default    | Meaning                                                            |
|----------|---------|------------|--------------------------------------------------------------------|
| `doc`    | str     | —          | The long context to compress.                                      |
| `query`  | str     | —          | The question the compressed context must still answer.             |
| `ratio`  | float   | `0.5`      | Fraction of tokens to **keep**, in `(0, 1]`. `0.3` ≈ keep 30%.     |
| `level`  | str     | `"phrase"` | `phrase` \| `sentence` \| `dynamic`. Only used by `t5`/`causal`; the reranker ignores it. |

It returns the compressed text plus a footer, e.g.:

```
The tower stands 330 meters tall. Gustave Eiffel's company designed and built the tower.

---
[compressed 58 -> 21 tokens (36% kept), level=sentence(reranker,w=1)]
```

### Example

> **query:** "How tall is the Eiffel Tower and who built it?"
>
> **doc:** *"The Eiffel Tower is located in Paris, France. It was completed in 1889. Bananas
> are a good source of potassium. The tower stands 330 meters tall. My favorite color is blue.
> Gustave Eiffel's company designed and built the tower. Cats sleep a lot during the day."*
>
> **→** *"The tower stands 330 meters tall. Gustave Eiffel's company designed and built the tower."*

The bananas, favorite color, and cats are dropped; the two query-relevant facts survive.

---

## Configuration reference

All configuration is via environment variables (set them in the MCP config `env` block).

| Variable                  | Default                                | Notes                                                       |
|---------------------------|----------------------------------------|-------------------------------------------------------------|
| `QUITO_MODEL_KIND`        | `reranker`                             | `reranker` \| `t5` \| `causal`.                             |
| `QUITO_MODEL`             | per-kind default (see table above)     | Any HuggingFace model id.                                   |
| `QUITO_RERANK_WINDOW`     | `1`                                    | Sentences per scored unit (`1` = pure sentence).            |
| `QUITO_DEVICE`            | auto                                   | `cuda` / `mps` / `cpu`.                                     |
| `QUITO_TRUST_REMOTE_CODE` | `false`                                | Needed by some custom rerankers (e.g. jina-reranker-v2).    |
| `QUITO_SIGMA`             | `1.0`                                  | QUITO smoothing (t5/causal only).                           |
| `QUITO_REPO_DIR`          | this directory                         | Path to the `attention_compressor` clone (t5/causal only).  |

### Reranker model options

- `cross-encoder/ms-marco-MiniLM-L-6-v2` — default, small and fast.
- `BAAI/bge-reranker-base` — multilingual.
- `jinaai/jina-reranker-v1-tiny-en` — tiny (also set `QUITO_TRUST_REMOTE_CODE=1`).

---

## Optional: token-level QUITO / QUITO-X backends

```bash
git clone https://github.com/Wenshansilvia/attention_compressor.git
```

Then in the MCP config `env` block set `QUITO_MODEL_KIND` to `t5` or `causal` and
`QUITO_REPO_DIR` to the absolute path of the clone. `server.py` patches a known bug in the
upstream repo at runtime, so no edits to the clone are needed.

---

## Project layout

```
context-compressor-mcp/
├── server.py                # MCP server: the compress_context tool + backend dispatch
├── reranker_compressor.py   # RerankerCompressor (default cross-encoder backend)
├── test_smoke.py            # quick end-to-end sanity check
├── README.md
└── attention_compressor/    # optional QUITO-X clone (t5/causal backends)
```

## Credits

The token-level backends wrap [QUITO / QUITO-X](https://github.com/Wenshansilvia/attention_compressor).
The reranker backend uses [sentence-transformers](https://www.sbert.net/) cross-encoders.
