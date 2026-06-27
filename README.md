# kiki-compressor

**Query-guided context compression — pay for the tokens that matter, drop the rest.**

`kiki-compressor` is a local [Model Context Protocol](https://modelcontextprotocol.io) server
that cuts how many tokens you feed a model. Hand it a body of text (`doc`), the `query` it has to
serve, and how much to keep (`ratio`); it returns only the query-relevant slice — usually a small
fraction of the original token count, with the answer still recoverable. Fewer input tokens means
**lower cost, more headroom in the context window, and less noise diluting attention**.

It exposes a single tool, `compress_context`, that any MCP client (Claude Desktop, Claude Code,
…) can call.

---

## What it saves (and what it doesn't)

Input tokens are the cost you control. A retrieved document, a transcript, a wall of search
results — you pay for every token and it crowds your context window, yet most of it is irrelevant
to the question at hand. `kiki-compressor` does **query-aware** pruning: it keeps the spans that
matter *for this query* and drops the rest, so the text you send onward is a fraction of the size.
`ratio` is the dial — keep `0.3` and you send ~70% fewer context tokens.

Be precise about where the savings land:

- **It cuts input / context tokens** — what you send *into* a model — **not** the model's generated
  output. Output length is up to the model.
- **The savings are real when the compressed text is forwarded to a model**: RAG prompts, agent
  loops, summarize-then-reason pipelines, stuffing retrieved chunks into a request. Compressing
  text a model *already* read in the same turn doesn't refund that turn — there the payoff is focus
  and a smaller artifact to reuse downstream.
- **It is extractive**, so the kept tokens are verbatim — never paraphrased or hallucinated.

## How it works

The default backend is a **cross-encoder reranker**. A reranker scores a `(query, passage)` pair
with a single relevance number, so compression happens at the **sentence / passage level**:

1. Split the document into sentences (NLTK `punkt`), optionally grouped into N-sentence windows.
2. Score every unit against the query with the cross-encoder.
3. Greedily keep the highest-scoring units up to a **token budget** (`ratio` × total tokens) — the
   budget *is* the token target, so the output lands at roughly `ratio` × the original size.
4. Re-emit the kept units **in their original order**.

The kept text is verbatim and query-relevant — never paraphrased or hallucinated — and the tool's
footer reports the exact before → after token counts so you can see the saving.

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

### Automatic install (recommended)

From the project directory, run the installer for your OS:

```bash
# macOS / Linux
./install_claude_desktop.sh

# Windows (PowerShell)
.\install_claude_desktop.ps1
```

By default the installer sets up **all three** targets:

1. **Claude Desktop** — backs up your config and merges in a `kiki-compressor` entry pointing at
   the venv's Python (other MCP servers untouched).
2. **Claude Code** — registers the same server via the `claude` CLI (`mcp add-json`, user scope,
   so it's available in every project).
3. **The [`compress-and-answer`](#the-compress-and-answer-skill) skill** — copied to
   `~/.claude/skills` (read by Claude Code).

Useful flags (forwarded to `add_to_claude_desktop.py`):

- `--dry-run` — print what it would do, change nothing
- `--no-desktop` / `--no-claude-code` / `--no-skill` — skip any target
- `--claude-code-scope local|user|project` — Claude Code config scope (default `user`)
- `--skills-dir PATH` — install the skill somewhere other than `~/.claude/skills`
- `--model-kind t5 --repo-dir ./attention_compressor` — install a token-level backend instead
- `--name`, `--model`, `--window`, `--device` — override individual settings
- `--help` — full list

Afterwards: **restart Claude Desktop**, and in **Claude Code** reconnect MCP (`/mcp`, or restart)
for the `compress_context` tool to load. The skill lands in `~/.claude/skills` (read by Claude
Code); for **Claude Desktop**, also add it via Settings → Capabilities/Skills, pointing at
`skills/compress-and-answer`.

### Manual install

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

## The compress-and-answer skill

The bundled skill ([`skills/compress-and-answer`](skills/compress-and-answer/SKILL.md), installed
by the script above) tells the assistant to reach for the compressor on **any** query — not only
when you paste a document — and to use it **first**, so that subsequent thinking runs over the
trimmed extract. It encodes the **gather → compress → reason → answer** pattern:

1. **Gather** source text for the query (the conversation, files, or a fresh web search / fetch).
2. **Compress it first**: `compress_context(doc=<gathered text>, query=<question>)` — before any
   extended analysis.
3. **Reason** over the *compressed* extract; carry it forward, leave the raw material behind.
4. **Answer** from the reduced context.

This matters because the tool is **extractive** — it can only shrink text you give it, so it can't
answer from an empty `doc`. The skill makes "use it for everything" actually work by gathering
material first. (If there's genuinely nothing to gather — a greeting, a bare arithmetic fact — the
skill says to answer directly.) A skill biases the model toward this; it's guidance, not a hard
switch. For guaranteed compression on every call, invoke the tool/script programmatically instead.

---

## The `compress_context` tool

```
compress_context(doc, query, ratio=0.5, level="phrase") -> str
```

| Argument | Type    | Default    | Meaning                                                            |
|----------|---------|------------|--------------------------------------------------------------------|
| `doc`    | str     | —          | The source text to trim — any context you'd otherwise send in full.|
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

The bananas, favorite color, and cats are dropped; the two query-relevant facts survive — and the
context you'd forward is **64% smaller** in tokens (36% kept) for that query.

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

The token-level backends live in the [`attention_compressor`](https://github.com/Wenshansilvia/attention_compressor)
**git submodule**. After cloning this repo, fetch it with:

```bash
git submodule update --init
```

(If you're setting it up fresh outside this repo, a plain
`git clone https://github.com/Wenshansilvia/attention_compressor.git` works too.)

Then in the MCP config `env` block set `QUITO_MODEL_KIND` to `t5` or `causal` and, if needed,
`QUITO_REPO_DIR` to the absolute path of the submodule. `server.py` patches a known bug in the
upstream repo at runtime, so no edits to the submodule are needed. The installer can do this
for you: `./install_claude_desktop.sh --model-kind t5 --repo-dir ./attention_compressor`.

---

## Benchmarks (from the QUITO / QUITO-X papers)

Read these through the token lens: **how few tokens can you keep before answer quality drops?**
They are **reported by the original authors** for the token-level QUITO / QUITO-X methods — i.e.
kiki-compressor's optional `t5` and `causal` backends, *not* the default reranker — and the
downstream readers / datasets differ from paper to paper. Reproduced here for context; see the
papers for full tables and setup.

### QUITO — [CCIR 2024](https://arxiv.org/abs/2408.00274)

Query attention from a **0.5B** model (`Qwen2-0.5B-Instruct`) prunes the context — versus
baselines that lean on 7–13B compressors. Downstream reader: `Longchat-13B-16k`.

**NaturalQuestions (accuracy, ↑):**

| Compression | Selective-Context | LLMLingua | LongLLMLingua | **QUITO** |
|-------------|:-----------------:|:---------:|:-------------:|:---------:|
| 2×          | 53.2              | 38.7      | 41.2          | **58.9**  |
| 4×          | 38.2              | 32.1      | 33.6          | **50.7**  |

(2× compression = keep ~half the tokens; 4× = keep ~a quarter.) On **ASQA** at 2×, QUITO (dynamic
sentence level) reports **40.0 EM / 23.8 DisambigF1**, ahead of the same baselines. The headline:
a 0.5B query-guided filter holds quality while dropping the most tokens — and its edge *widens* as
you cut deeper (4×), exactly where token savings matter most.

### QUITO-X — [EMNLP 2025 Findings](https://arxiv.org/abs/2408.10497)

Reframes compression as an **Information Bottleneck** problem and scores tokens with the
**cross-attention of a 60M `FLAN-T5-small`** encoder–decoder. Evaluated on **CoQA, Quoref, DROP,
SQuAD** against Selective-Context (GPT-2 124M), LLMLingua / LongLLMLingua (Llama-2-7B),
LLMLingua2 (XLM-RoBERTa-large 355M), and QUITO (Qwen2-0.5B).

- **~25% more compression** than the prior state of the art at matched QA quality — i.e. it keeps
  meaningfully fewer tokens for the same answers, using a model orders of magnitude smaller than
  the 7B baselines.
- The authors report that the compressed context can **match or even exceed the full (uncompressed)
  context** in some settings. Even at an aggressive **0.25 retention**, it preserves most of the
  full-context score — e.g. with LLaMA3-8B as reader, Quoref **86.8** (vs **93.1** full context) and
  CoQA **75.5** (vs **79.3** full context).

> Caveat: exact cell values above were extracted from the published papers/tables; treat them as
> indicative and consult the source PDFs for the authoritative, complete results.

---

## Project layout

```
context-compressor-mcp/
├── server.py                  # MCP server: the compress_context tool + backend dispatch
├── reranker_compressor.py     # RerankerCompressor (default cross-encoder backend)
├── test_smoke.py              # quick end-to-end sanity check
├── add_to_claude_desktop.py   # cross-platform Claude Desktop installer (does the work)
├── install_claude_desktop.sh  # macOS/Linux installer wrapper
├── install_claude_desktop.ps1 # Windows installer wrapper
├── skills/                    # optional "compress-and-answer" Claude skill
│   └── compress-and-answer/SKILL.md
├── README.md
└── attention_compressor/      # QUITO/QUITO-X submodule (optional t5/causal backends)
```

## Credits

The token-level backends wrap [QUITO / QUITO-X](https://github.com/Wenshansilvia/attention_compressor)
(Wang et al.). The reranker backend uses [sentence-transformers](https://www.sbert.net/) cross-encoders.

If you use the token-level backends, please cite the original work:

```bibtex
@article{wang2024quito,
  author  = {Wang, Wenshan and Wang, Yihang and Fan, Yixing and Liao, Huaming and Guo, Jiafeng},
  title   = {QUITO: Accelerating Long-Context Reasoning through Query-Guided Context Compression},
  journal = {arXiv preprint arXiv:2408.00274},
  year    = {2024}
}

@article{wang2024quitox,
  author  = {Wang, Yihang and Huang, Xu and Tian, Bowen and Su, Yueyang and Yu, Lei and Liao, Huaming and Fan, Yixing and Guo, Jiafeng and Cheng, Xueqi},
  title   = {QUITO-X: A New Perspective on Context Compression from the Information Bottleneck Theory},
  journal = {arXiv preprint arXiv:2408.10497},
  year    = {2024}
}
```
