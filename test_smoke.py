from reranker_compressor import RerankerCompressor

doc = (
    "The Eiffel Tower is located in Paris, France. It was completed in 1889. "
    "Bananas are a good source of potassium. The tower stands 330 meters tall. "
    "My favorite color is blue. Gustave Eiffel's company designed and built the tower. "
    "Cats sleep a lot during the day."
)
query = "How tall is the Eiffel Tower and who built it?"

c = RerankerCompressor("cross-encoder/ms-marco-MiniLM-L-6-v2")
out = c.compress(doc, query, ratio=0.5)

print("QUERY:      ", query)
print("ORIGINAL    ", f"({len(doc)} chars):", doc)
print("COMPRESSED  ", f"({len(out)} chars):", out)
print("kept height fact:", "330" in out, "| kept builder fact:", "Eiffel" in out)

assert 0 < len(out) < len(doc), "compression did not shorten the document"
print("OK: reranker compression working")
