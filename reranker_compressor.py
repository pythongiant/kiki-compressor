#!/usr/bin/env python3
"""
RerankerCompressor: query-guided context compression using a cross-encoder reranker.

A reranker scores a (query, passage) pair with one relevance number, so this
compresses at the SENTENCE / PASSAGE level (not token level): split the doc into
units, score each against the query, keep the highest-scoring units up to a token
budget, and re-emit them in their original order.
"""
import numpy as np


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


class RerankerCompressor:
    def __init__(
        self,
        model_path: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        window: int = 1,
        max_length: int = 512,
        device: str | None = None,
        trust_remote_code: bool = False,
        batch_size: int = 64,
    ):
        """
        model_path: any cross-encoder / reranker loadable by sentence-transformers.
        window:     number of consecutive sentences scored as one unit (1 = pure sentence).
        device:     "cuda" / "mps" / "cpu" / None (auto).
        trust_remote_code: needed by some custom rerankers (e.g. jina-reranker-v2).
        """
        from sentence_transformers import CrossEncoder

        self.model_path = model_path
        self.window = max(1, int(window))
        self.batch_size = batch_size

        kw = dict(max_length=max_length, device=device)
        try:
            self.model = CrossEncoder(model_path, trust_remote_code=trust_remote_code, **kw)
        except TypeError:  # older sentence-transformers without the kwarg
            self.model = CrossEncoder(model_path, **kw)
        self.tokenizer = self.model.tokenizer

    def __repr__(self):
        return f"<RerankerCompressor model={self.model_path}, window={self.window}>"

    def _split(self, doc: str):
        _ensure_punkt()
        import nltk
        try:
            sents = nltk.sent_tokenize(doc)
        except Exception:
            sents = [doc]
        sents = [s for s in sents if s.strip()] or [doc]
        if self.window <= 1:
            return sents
        return [" ".join(sents[i:i + self.window]) for i in range(0, len(sents), self.window)]

    def _ntok(self, text: str) -> int:
        return max(1, len(self.tokenizer(text, add_special_tokens=False).input_ids))

    def compress(self, doc: str, query: str, ratio: float = 0.5) -> str:
        units = self._split(doc)
        if len(units) <= 1:
            return doc

        scores = self.model.predict(
            [[query, u] for u in units],
            batch_size=self.batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        scores = np.asarray(scores, dtype=float)
        if scores.ndim > 1:           # models with num_labels > 1
            scores = scores[:, -1]

        toks = [self._ntok(u) for u in units]
        budget = sum(toks) * ratio
        order = np.argsort(-scores)   # most relevant first

        keep = [False] * len(units)
        used = 0
        for i in order:
            if used + toks[i] > budget and used > 0:
                break
            keep[i] = True
            used += toks[i]

        out = [u for u, k in zip(units, keep) if k]
        if not out:
            out = [units[int(order[0])]]
        return " ".join(out)
