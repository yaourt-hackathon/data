"""Benchmark de LLM locaux (Ollama) sur des questions métier avec contexte fourni.

Aucune dépendance : bibliothèque standard uniquement.

Usage :
    python bench.py                                  # tous les modèles par défaut installés
    python bench.py --models llama3.2:3b qwen2.5:7b
    python bench.py --only Q01 Q07                   # quelques questions seulement

Sorties dans results/ :
    run-<date>.jsonl     une ligne par (modèle, question) : réponse + contrôles auto + perfs
    run-<date>.md        réponses côte à côte, à faire noter par une IA (ou un humain)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLLAMA = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_MODELS = ["qwen2.5:1.5b", "llama3.2:3b", "qwen2.5:7b"]
OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 4096, "num_predict": 600}

SYSTEM_PROMPT = """Tu es l'assistant des commerciaux de Givaudan (parfums et arômes).
Règles :
- Réponds UNIQUEMENT à partir des sources fournies, même si tes connaissances générales disent autre chose.
- Si l'information n'est pas dans les sources, dis clairement qu'elle n'y figure pas. N'invente aucune valeur.
- Réponds en français, de façon concise et précise (chiffres, dates, noms de produits)."""

REFUSAL_RE = re.compile(
    r"ne (mentionne|précise|contient|donne|fournit|indique|figure|parle)|n'(est|apparaît|y a) pas"
    r"|pas (d'information|mentionn|précisé|indiqué|disponible|dans les sources)|aucune (information|donnée|mention)"
    r"|ne figure|absent|not (mention|provided|specified)|je ne (sais|dispose|peux)"
    r"|n'ai (pas|aucune) (trouvé|information|accès)",
    re.IGNORECASE,
)
FR_WORDS = {"le", "la", "les", "des", "est", "et", "pour", "dans", "une", "du", "sont", "pas", "avec"}
EN_WORDS = {"the", "is", "and", "for", "in", "are", "with", "of", "to", "not", "this"}


def api(path: str, payload: dict | None = None, timeout: int = 900) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(OLLAMA + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def installed_models() -> set[str]:
    return {m["name"] for m in api("/api/tags")["models"]}


def build_messages(q: dict, contexts: dict) -> list[dict]:
    sources = "\n\n".join(contexts[c] for c in q["contexts"])
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Sources :\n\n{sources}\n\nQuestion : {q['question']}"},
    ]


def extract_json(text: str):
    m = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def auto_checks(q: dict, answer: str) -> dict:
    low = answer.lower()
    checks: dict = {}
    if q.get("must_contain"):
        hits = [any(alt.lower() in low for alt in group) for group in q["must_contain"]]
        checks["mots_cles"] = round(sum(hits) / len(hits), 2)
    if q.get("json"):
        checks["json_valide"] = extract_json(answer) is not None
    if q.get("refusal"):
        has_number = bool(re.search(r"\d+[,.]\d+\s*%", answer))
        checks["refus_correct"] = bool(REFUSAL_RE.search(answer)) and not has_number
    words = re.findall(r"[a-zà-ÿ']+", low)
    fr, en = sum(w in FR_WORDS for w in words), sum(w in EN_WORDS for w in words)
    checks["francais"] = fr >= en
    return checks


def auto_score(checks: dict) -> float:
    """Score auto 0-1 : moyenne des contrôles disponibles (hors langue, comptée à part)."""
    vals = [float(v) for k, v in checks.items() if k != "francais"]
    return round(sum(vals) / len(vals), 2) if vals else float(checks["francais"])


def run_model(model: str, questions: list[dict], contexts: dict, out, runs: int = 1) -> list[dict]:
    print(f"\n=== {model} ===", flush=True)
    t = time.time()
    api("/api/chat", {"model": model, "messages": [{"role": "user", "content": "ok"}],
                      "stream": False, "options": {**OPTIONS, "num_predict": 1}})
    print(f"  chargement + chauffe : {time.time() - t:.1f}s", flush=True)
    ps = {m["name"]: m for m in api("/api/ps").get("models", [])}.get(model, {})

    rows = []
    for run, q in ((run, q) for run in range(1, runs + 1) for q in questions):
        try:
            r = api("/api/chat", {"model": model, "messages": build_messages(q, contexts),
                                  "stream": False, "options": OPTIONS})
            answer = r["message"]["content"].strip()
            perf = {
                "total_s": round(r["total_duration"] / 1e9, 2),
                "prompt_s": round(r.get("prompt_eval_duration", 0) / 1e9, 2),
                "tokens": r.get("eval_count", 0),
                "tok_s": round(r.get("eval_count", 0) / max(r.get("eval_duration", 1) / 1e9, 1e-9), 1),
            }
            error = None
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            answer, perf, error = "", {}, str(exc)
        checks = auto_checks(q, answer) if not error else {}
        row = {
            "model": model, "run": run, "id": q["id"], "type": q["type"], "question": q["question"],
            "expected": q["expected"], "answer": answer, "checks": checks,
            "auto_score": auto_score(checks) if checks else 0.0, "perf": perf, "error": error,
            "ram_gb": round(ps.get("size", 0) / 1e9, 2), "vram_gb": round(ps.get("size_vram", 0) / 1e9, 2),
        }
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
        out.flush()
        rows.append(row)
        status = f"ERREUR {error}" if error else f"auto {row['auto_score']:.2f} | {perf['total_s']:>6.1f}s | {perf['tok_s']:>5.1f} tok/s"
        print(f"  {q['id']}{f' (essai {run})' if runs > 1 else ''} {q['type']:<18} {status}", flush=True)
    return rows


def stability(rows: list[dict]) -> float | None:
    """Part des questions dont toutes les réponses (sur plusieurs essais) sont identiques."""
    by_q: dict[str, set[str]] = {}
    for r in rows:
        by_q.setdefault(r["id"], set()).add(r["answer"])
    if not any(r.get("run", 1) > 1 for r in rows):
        return None
    return round(sum(len(a) == 1 for a in by_q.values()) / len(by_q), 2)


def summarize(all_rows: list[dict]) -> None:
    print("\n=== Résumé ===")
    print(f"{'modèle':<16}{'score auto':>11}{'refus OK':>10}{'latence moy':>13}{'tok/s':>8}{'RAM Go':>8}{'VRAM Go':>9}{'stabilité':>11}")
    for model in dict.fromkeys(r["model"] for r in all_rows):
        rs = [r for r in all_rows if r["model"] == model and not r["error"]]
        if not rs:
            print(f"{model:<16} aucune réponse")
            continue
        refus = [r["checks"]["refus_correct"] for r in rs if "refus_correct" in r["checks"]]
        stab = stability(rs)
        print(f"{model:<16}{sum(r['auto_score'] for r in rs) / len(rs):>11.2f}"
              f"{f'{sum(refus)}/{len(refus)}':>10}"
              f"{sum(r['perf']['total_s'] for r in rs) / len(rs):>12.1f}s"
              f"{sum(r['perf']['tok_s'] for r in rs) / len(rs):>8.1f}{rs[0]['ram_gb']:>8.1f}{rs[0]['vram_gb']:>9.1f}"
              f"{'—' if stab is None else f'{stab:.0%}':>11}")


def write_review_sheet(path: Path, all_rows: list[dict], questions: list[dict]) -> None:
    lines = ["# Réponses à noter\n",
             "Grille par réponse (0-2 chacun) : **exactitude**, **fidélité aux sources** (rien d'inventé), "
             "**complétude**, **utilité pour un commercial**.\n"]
    for q in questions:
        lines += [f"\n## {q['id']} — {q['type']}\n", f"**Question :** {q['question']}\n",
                  f"**Attendu :** {q['expected']}\n"]
        for r in (r for r in all_rows if r["id"] == q["id"] and r.get("run", 1) == 1):
            lines += [f"\n### {r['model']}  (auto {r['auto_score']:.2f}, {r['perf'].get('total_s', '?')}s)\n",
                      "~~~~text", r["answer"] or f"[ERREUR] {r['error']}", "~~~~"]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    p.add_argument("--only", nargs="+", help="identifiants de questions à garder (ex. Q01 Q07)")
    p.add_argument("--questions", default=str(HERE / "questions.json"))
    p.add_argument("--runs", type=int, default=1, help="essais par question (mesure de stabilité si > 1)")
    args = p.parse_args()

    spec = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    questions = [q for q in spec["questions"] if not args.only or q["id"] in args.only]

    try:
        available = installed_models()
    except urllib.error.URLError:
        sys.exit(f"Ollama injoignable sur {OLLAMA} : lance l'application Ollama.")
    models = [m for m in args.models if m in available]
    for m in set(args.models) - set(models):
        print(f"[ignoré] {m} n'est pas installé (ollama pull {m})")
    if not models:
        sys.exit("Aucun modèle à tester.")

    results = HERE / "results"
    results.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    jsonl = results / f"run-{stamp}.jsonl"
    print(f"{len(questions)} questions x {len(models)} modèles -> {jsonl.name}")

    all_rows = []
    with jsonl.open("w", encoding="utf-8") as out:
        for model in models:
            all_rows += run_model(model, questions, spec["contexts"], out, args.runs)

    summarize(all_rows)
    md = jsonl.with_suffix(".md")
    write_review_sheet(md, all_rows, questions)
    print(f"\nRésultats : {jsonl}\nFeuille à noter : {md}")


if __name__ == "__main__":
    main()
