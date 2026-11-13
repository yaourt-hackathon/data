"""Benchmark des modèles d'embeddings (Ollama) : retrouver le bon passage.

Questions en français, passages en anglais et en français (avec pièges).
Mesures : réussite top-1, réussite top-3, MRR, vitesse (textes/s), chargement, mémoire.

Usage :
    python bench_embed.py
    python bench_embed.py --models embeddinggemma bge-m3
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

from bench import api, installed_models

HERE = Path(__file__).resolve().parent
DEFAULT_MODELS = ["nomic-embed-text", "embeddinggemma", "bge-m3"]

# Préfixes recommandés par les auteurs de chaque modèle (requête, document)
PREFIXES = {
    "nomic-embed-text": ("search_query: ", "search_document: "),
    "embeddinggemma": ("task: search result | query: ", "title: none | text: "),
}


def norm_name(model: str) -> str:
    return model.split(":")[0]


def embed(model: str, texts: list[str]) -> list[list[float]]:
    return api("/api/embed", {"model": model, "input": texts})["embeddings"]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def run_model(model: str, corpus: dict) -> dict:
    q_prefix, d_prefix = PREFIXES.get(norm_name(model), ("", ""))
    ids = list(corpus["passages"])
    docs = [d_prefix + corpus["passages"][i] for i in ids]
    questions = [q_prefix + q["q"] for q in corpus["questions"]]

    t = time.time()
    embed(model, ["chauffe"])
    load_s = time.time() - t
    ps = {m["name"]: m for m in api("/api/ps").get("models", [])}
    ram = next((m.get("size", 0) for n, m in ps.items() if n.startswith(norm_name(model))), 0)

    t = time.time()
    doc_vecs = embed(model, docs)
    q_vecs = embed(model, questions)
    elapsed = time.time() - t

    top1 = top3 = 0
    rr = 0.0
    details = []
    for q, qv in zip(corpus["questions"], q_vecs):
        ranking = sorted(ids, key=lambda i: -cosine(qv, doc_vecs[ids.index(i)]))
        rank = ranking.index(q["expected"]) + 1
        top1 += rank == 1
        top3 += rank <= 3
        rr += 1 / rank
        details.append({"q": q["q"], "expected": q["expected"], "rank": rank, "top3": ranking[:3]})
    n = len(corpus["questions"])
    return {
        "model": model, "top1": top1, "top3": top3, "n": n, "mrr": round(rr / n, 3),
        "texts_per_s": round((len(docs) + n) / elapsed, 1), "load_s": round(load_s, 2),
        "ram_gb": round(ram / 1e9, 2), "details": details,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    args = p.parse_args()

    corpus = json.loads((HERE / "embed_corpus.json").read_text(encoding="utf-8"))
    available = {norm_name(m) for m in installed_models()} | installed_models()
    models = [m for m in args.models if m in available]
    for m in set(args.models) - set(models):
        print(f"[ignoré] {m} n'est pas installé (ollama pull {m})")

    results = []
    for m in models:
        r = run_model(m, corpus)
        results.append(r)
        print(f"{m:<18} top-1 {r['top1']:>2}/{r['n']}  top-3 {r['top3']:>2}/{r['n']}  MRR {r['mrr']:.3f}  "
              f"{r['texts_per_s']:>6.1f} textes/s  chargement {r['load_s']:.1f}s  RAM {r['ram_gb']:.2f} Go", flush=True)
        for d in r["details"]:
            if d["rank"] > 1:
                print(f"    rang {d['rank']:>2} : {d['q']}  (attendu {d['expected']}, obtenu {d['top3']})")

    out = HERE / "results" / f"embed-{datetime.now():%Y%m%d-%H%M}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRésultats : {out}")


if __name__ == "__main__":
    main()
