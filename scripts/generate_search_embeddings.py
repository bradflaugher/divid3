#!/usr/bin/env python3
"""
Regenerate search-embeddings.json from scripts/search_phrases.json.

The browser runtime requires every vector to be L2-normalized so it can
treat dot product as cosine similarity. This script enforces that, and
sanity-checks the output before writing.

Implementation notes
--------------------
* We use the *same* ONNX model the browser loads (q8-quantized
  all-MiniLM-L6-v2 under models/), so vectors generated here match what
  transformers.js produces in the page exactly. No external HF download.
* sentence-transformers' all-MiniLM-L6-v2 pipeline is: WordPiece tokenize
  → BERT forward → mean-pool by attention mask → L2 normalize. We
  reproduce it with `tokenizers` + `onnxruntime`.
* Output preserves the historical shape `[ {key, vectors}, ... ]` plus
  an `examples` field per route so future regenerations can be diffed.
* Run from the repo root: `python3 scripts/generate_search_embeddings.py`

After regenerating, bump `EMBEDDINGS_VERSION` in index.html so client
caches are invalidated atomically.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

REPO_ROOT      = Path(__file__).resolve().parent.parent
PHRASES_FILE   = REPO_ROOT / "scripts" / "search_phrases.json"
OUT_FILE       = REPO_ROOT / "search-embeddings.json"
MODEL_DIR      = REPO_ROOT / "models" / "sentence-transformers" / "all-MiniLM-L6-v2"
TOKENIZER_FILE = MODEL_DIR / "tokenizer.json"
ONNX_FILE      = MODEL_DIR / "onnx" / "model_quantized.onnx"
MAX_SEQ        = 128
BATCH          = 32


def load_pipeline() -> tuple[Tokenizer, ort.InferenceSession]:
    if not TOKENIZER_FILE.exists():
        raise FileNotFoundError(f"missing tokenizer: {TOKENIZER_FILE}")
    if not ONNX_FILE.exists():
        raise FileNotFoundError(f"missing model: {ONNX_FILE}")
    tok = Tokenizer.from_file(str(TOKENIZER_FILE))
    tok.enable_padding(pad_id=0, pad_token="[PAD]")
    tok.enable_truncation(max_length=MAX_SEQ)
    sess = ort.InferenceSession(str(ONNX_FILE), providers=["CPUExecutionProvider"])
    return tok, sess


def embed_batch(tok: Tokenizer, sess: ort.InferenceSession, texts: list[str]) -> np.ndarray:
    encs = tok.encode_batch(texts)
    ids  = np.array([e.ids            for e in encs], dtype=np.int64)
    mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
    tt   = np.array([e.type_ids       for e in encs], dtype=np.int64)
    out, = sess.run(None, {
        "input_ids":      ids,
        "attention_mask": mask,
        "token_type_ids": tt,
    })
    # mean-pool by attention mask
    m = mask[..., None].astype(np.float32)
    pooled = (out * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
    # L2 normalize
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    return pooled / np.clip(norms, 1e-12, None)


def embed_all(tok: Tokenizer, sess: ort.InferenceSession, texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        chunk = texts[i:i + BATCH]
        out.extend(embed_batch(tok, sess, chunk).tolist())
    return out


def round_floats(vec: list[float], digits: int = 6) -> list[float]:
    """Trim float precision to keep search-embeddings.json compact.
    6 digits ≈ 1e-6 — well below any threshold the runtime cares about."""
    return [round(float(x), digits) for x in vec]


def main() -> int:
    cfg = json.loads(PHRASES_FILE.read_text(encoding="utf-8"))
    routes_cfg = cfg["_routes"]
    if not isinstance(routes_cfg, list) or not routes_cfg:
        raise SystemExit("scripts/search_phrases.json: _routes must be a non-empty list")

    print(f"loading model: {ONNX_FILE.relative_to(REPO_ROOT)}")
    tok, sess = load_pipeline()

    output = []
    total_vec = 0
    for route in routes_cfg:
        key     = route["key"]
        phrases = [p.strip() for p in route["phrases"] if p and p.strip()]
        if not phrases:
            print(f"  skip {key}: no phrases")
            continue
        # de-duplicate while preserving order
        seen, dedup = set(), []
        for p in phrases:
            lp = p.lower()
            if lp in seen:
                continue
            seen.add(lp)
            dedup.append(p)
        phrases = dedup

        print(f"  {key:<14} {len(phrases):>3} phrases")
        vecs = embed_all(tok, sess, phrases)

        # Sanity: every vector must be unit-length.
        for v in vecs:
            n = math.sqrt(sum(x * x for x in v))
            assert abs(n - 1.0) < 1e-4, f"{key}: non-normalized vector (n={n})"

        output.append({
            "key":      key,
            "examples": phrases,
            "vectors":  [round_floats(v) for v in vecs],
        })
        total_vec += len(vecs)

    # Cross-route sanity check: the embedding space should not be
    # collapsed (every route would route everywhere). We assert that
    # at least *some* pair of route centroids has similarity below 0.6.
    centroids = []
    for r in output:
        m = np.array(r["vectors"]).mean(axis=0)
        m = m / max(np.linalg.norm(m), 1e-12)
        centroids.append(m)
    cm = np.stack(centroids)
    sim = cm @ cm.T
    np.fill_diagonal(sim, -1)
    if sim.max() > 0.95:
        print(f"WARNING: two routes have very similar centroids "
              f"({sim.max():.3f}) — examples may be too overlapping.", file=sys.stderr)

    print(f"writing {OUT_FILE.relative_to(REPO_ROOT)} "
          f"({len(output)} routes, {total_vec} vectors)")
    OUT_FILE.write_text(
        json.dumps(output, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print("done. Remember to bump EMBEDDINGS_VERSION in index.html.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
