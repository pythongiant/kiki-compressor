#!/usr/bin/env python3
"""
MCP server exposing query-guided context compression as a tool.

Three backends, selected by QUITO_MODEL_KIND:
  - "reranker" : modern lightweight cross-encoder reranker, sentence/passage level (default)
  - "t5"       : QUITO-X cross-attention (FLAN-T5), token level (paper method)
  - "causal"   : QUITO self-attention (Qwen2-0.5B-Instruct), token level

The t5/causal paths need the cloned repo (https://github.com/Wenshansilvia/attention_compressor).
Put this file next to the repo's `quito/` package (and reranker_compressor.py beside it),
or set QUITO_REPO_DIR. The reranker path needs neither the repo nor matplotlib.
"""
import os
import sys
import threading

import anyio
from mcp.server.fastmcp import FastMCP

# Make the cloned repo + local modules importable
REPO_DIR = os.environ.get("QUITO_REPO_DIR", os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

MODEL_KIND = os.environ.get("QUITO_MODEL_KIND", "reranker").lower()   # reranker | t5 | causal
SIGMA = float(os.environ.get("QUITO_SIGMA", "1.0"))
RERANK_WINDOW = int(os.environ.get("QUITO_RERANK_WINDOW", "1"))
DEVICE = os.environ.get("QUITO_DEVICE") or None
TRUST_REMOTE = os.environ.get("QUITO_TRUST_REMOTE_CODE", "").lower() in ("1", "true", "yes")


def _default_ratio() -> float:
    """Default keep-ratio for compress_context, from QUITO_RATIO (fraction to KEEP, (0,1]).
    Falls back to 0.25 if unset, unparseable, or out of range."""
    try:
        r = float(os.environ.get("QUITO_RATIO", "0.25"))
    except ValueError:
        return 0.25
    return r if 0 < r <= 1 else 0.25


DEFAULT_RATIO = _default_ratio()

_DEFAULT_MODEL = {
    "reranker": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "t5": "google/flan-t5-base",
    "causal": "Qwen/Qwen2-0.5B-Instruct",
}
MODEL_PATH = os.environ.get("QUITO_MODEL", _DEFAULT_MODEL.get(MODEL_KIND, _DEFAULT_MODEL["reranker"]))

_compressor = None
_lock = threading.Lock()


def _build_quito(kind):
    # Lazy: only import the heavy quito package (and patch its bug) when actually used.
    from quito import utils as _utils
    if not hasattr(_utils, "get_sorted_ids"):
        def _get_sorted_ids(score):
            return sorted(range(len(score)), key=lambda i: score[i], reverse=True)
        _utils.get_sorted_ids = _get_sorted_ids
    from quito.compressor import Compressor, T5Compressor
    cls = T5Compressor if kind == "t5" else Compressor
    return cls(MODEL_PATH, sigma=SIGMA)


def _get_compressor():
    """Lazy, thread-safe singleton. Loads the model on first tool call, not at import."""
    global _compressor
    if _compressor is None:
        with _lock:
            if _compressor is None:
                if MODEL_KIND == "reranker":
                    from reranker_compressor import RerankerCompressor
                    _compressor = RerankerCompressor(
                        MODEL_PATH, window=RERANK_WINDOW,
                        device=DEVICE, trust_remote_code=TRUST_REMOTE,
                    )
                elif MODEL_KIND in ("t5", "causal"):
                    _compressor = _build_quito(MODEL_KIND)
                else:
                    raise ValueError(
                        f"QUITO_MODEL_KIND must be reranker|t5|causal, got {MODEL_KIND!r}"
                    )
    return _compressor


def _count(comp, text):
    tok = comp.tokenizer
    try:
        return len(tok(text, add_special_tokens=False).input_ids)
    except TypeError:
        return len(tok(text).input_ids)


def _ensure_punkt():
    import nltk
    for res in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{res}")
        except LookupError:
            try:
                nltk.download(res, quiet=True)
            except Exception:
                pass


def _run(doc, query, ratio, level):
    """Blocking work. Runs in a worker thread so it never stalls the event loop."""
    comp = _get_compressor()
    if MODEL_KIND == "reranker":
        out = comp.compress(doc=doc, query=query, ratio=ratio)   # 'level' n/a for a reranker
        eff_level = f"sentence(reranker,w={RERANK_WINDOW})"
    else:
        if level in ("sentence", "dynamic"):
            _ensure_punkt()
        if level == "sentence":
            out = comp.compress_sentence(doc=doc, query=query, ratio=ratio)
        elif level == "dynamic":
            out = comp.compress_sentence_token(doc=doc, query=query, ratio=ratio)
        else:
            out = comp.compress(doc=doc, query=query, ratio=ratio, word=True)
        eff_level = level
    return out, _count(comp, doc), _count(comp, out), eff_level


mcp = FastMCP("context-compressor")


@mcp.tool()
async def compress_context(
    doc: str,
    query: str,
    ratio: float = DEFAULT_RATIO,
    level: str = "phrase",
) -> str:
    """Focus a body of source text on a query: keep only the parts relevant to `query` and
    drop the rest. Returns the trimmed text (verbatim extracts, in original order) with a
    token-count footer.

    Use this to ground the answer to ANY query, not just when the user pastes a document.
    `doc` can be a pasted document, retrieved web-search / fetch results, file contents, search
    hits, or earlier conversation you want to focus. The general pattern is:
        gather relevant text  ->  compress_context(that text, the question)  ->  answer from it.

    This is an EXTRACTIVE filter, not a generator: it can only shrink text you give it, so `doc`
    must contain the source material. It cannot answer a question from nothing — if you have no
    source yet, gather some first (e.g. a web search) and pass it as `doc`.

    Args:
        doc: The source text to focus — any gathered context; the more there is, the more it helps.
        query: The question/instruction the kept text must still answer.
        ratio: Fraction of tokens to KEEP, in (0, 1]. 0.3 keeps ~30%. Lower is more aggressive.
               Omit it to use the server default (env QUITO_RATIO, default 0.25).
        level: Only used by the t5/causal backends:
               "phrase" (token level), "sentence" (whole salient sentences),
               "dynamic" (sentences + a partial trailing sentence).
               The reranker backend always works at sentence/passage level and ignores this.
    """
    if not doc or not doc.strip():
        return ("compress_context needs source text in `doc` — it focuses existing material on a "
                "query, it does not generate answers. Gather the relevant text first (web results, "
                "a file, a pasted document, or earlier context) and pass it as `doc`.")
    if not 0 < ratio <= 1:
        return "Error: ratio must be in (0, 1]."
    if level not in ("phrase", "sentence", "dynamic"):
        return f"Error: level must be one of phrase|sentence|dynamic, got {level!r}."

    out, n_in, n_out, eff = await anyio.to_thread.run_sync(_run, doc, query, ratio, level)
    pct = (n_out / n_in * 100) if n_in else 0.0
    return f"{out}\n\n---\n[compressed {n_in} -> {n_out} tokens ({pct:.0f}% kept), level={eff}]"


if __name__ == "__main__":
    # stdio transport (what Claude Desktop expects).
    # For a remote/multi-client server use: mcp.run(transport="streamable-http")
    mcp.run()
