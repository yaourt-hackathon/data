"""Benchmark v0.2 : évaluation sur cas métier, avec grille pondérée sur les 7 dimensions du cours.

Dimensions (cours « Comment évalue-t-on un LLM ? ») : exactitude, pertinence, factualité, raisonnement,
robustesse, sécurité, performance. Poids et règle de décision : voir cas_metier.json.

Même protocole que la v0.1 (bench.py) : température 0, graine fixe, premier appel exclu des mesures,
mêmes 12 questions. Les cas ajoutés (F, R, S) et les variations de formulation (robustesse) viennent en plus.
Bibliothèque standard uniquement. Réutilise bench.py sans le modifier.

Usage :
    python bench_metier.py                              # 4 modèles installés, tous les cas
    python bench_metier.py --models qwen2.5:7b --only Q01 S2

Sorties dans results/ :
    metier-<date>.jsonl            une ligne par (modèle, cas)
    metier-<date>-synthese.md      tableau par dimension, note pondérée, décision
    metier-<date>-synthese.json    mêmes chiffres, pour la suite
    metier-<date>-relecture.md     toutes les réponses, à relire à la main
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
from datetime import datetime
from pathlib import Path

import bench

HERE = bench.HERE
DEFAULT_MODELS = ["qwen2.5:1.5b", "llama3.2:3b", "gemma3:4b", "qwen2.5:7b"]

# « non conforme » / « illégal » employés de façon affirmative (pas précédés d'une négation proche).
FORBIDDEN = re.compile(r"non[- ]conforme|illégal|illegal", re.IGNORECASE)
NEGATION = re.compile(r"\b(pas|jamais|aucun|ni)\b|n'est|ne sont|ne peux|ne saurais", re.IGNORECASE)
BULLET = re.compile(r"^\s*([-•*–]|\d+[.)])\s+")
# Détecteur de refus étendu après la relecture du 12/11 : celui de bench.py (v0.1) ne reconnaissait pas
# « n'y figure pas », « ne fixe pas » ni « n'établit aucun », pourtant des refus corrects.
# bench.py reste inchangé pour que la v0.1 reste comparable.
REFUSAL_V2 = re.compile(
    bench.REFUSAL_RE.pattern
    + r"|n'y figure|n'y est pas|ne fixe|n'établit|n'établi|ne définit|ne spécifie|ne prévoit|ne cite|aucun plafond|aucune limite",
    re.IGNORECASE,
)
HAS_NUMBER = re.compile(r"\d+[,.]\d+\s*%")


def violations(answer: str) -> list[str]:
    found = []
    for m in FORBIDDEN.finditer(answer):
        if not NEGATION.search(answer[max(0, m.start() - 40):m.start()]):
            found.append(m.group(0))
    return found


def checks_cas(cas: dict, answer: str) -> dict:
    c = bench.auto_checks(cas, answer)
    if cas.get("refusal"):
        c["refus_correct"] = bool(REFUSAL_V2.search(answer)) and not HAS_NUMBER.search(answer)
    if cas.get("must_not_contain"):
        c["sans_intrus"] = not any(m.lower() in answer.lower() for m in cas["must_not_contain"])
    if cas.get("no_violation"):
        c["sans_affirmation_non_conforme"] = not violations(answer)
    if "max_lignes" in cas:
        c["max_lignes"] = len([ln for ln in answer.splitlines() if ln.strip()]) <= cas["max_lignes"]
    if "max_puces" in cas:
        c["max_puces"] = sum(bool(BULLET.match(ln)) for ln in answer.splitlines()) <= cas["max_puces"]
    return c


def score_cas(cas: dict, c: dict) -> float:
    """Moyenne des contrôles (0-1). La langue ne compte que pour la pertinence."""
    vals = [float(v) for k, v in c.items() if k != "francais" or cas["dimension"] == "Pertinence"]
    return round(sum(vals) / len(vals), 2) if vals else float(c.get("francais", 0))


def charger(only: list[str] | None):
    spec = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    cm = json.loads((HERE / "cas_metier.json").read_text(encoding="utf-8"))
    contexts = {**spec["contexts"], **cm["contexts"]}
    cas = []
    for q in spec["questions"]:
        q = {**q, "dimension": cm["dimensions_questions_v01"][q["id"]], "origine": "v0.1",
             **cm["contraintes_format"].get(q["id"], {})}
        cas.append(q)
    cas += [{**q, "origine": "v0.2"} for q in cm["cas_nouveaux"]]
    base = {c["id"]: c for c in cas}
    for qid, textes in cm["variations"].items():
        for i, texte in enumerate(textes, 1):
            cas.append({**base[qid], "id": f"{qid}-v{i}", "question": texte, "dimension": "Robustesse",
                        "origine": "variation", "variante_de": qid})
    if only:
        cas = [c for c in cas if c["id"] in only]
    return cas, contexts, cm


def run_model(model: str, cas: list[dict], contexts: dict, out) -> list[dict]:
    print(f"\n=== {model} ===", flush=True)
    t = time.time()
    bench.api("/api/chat", {"model": model, "messages": [{"role": "user", "content": "ok"}],
                            "stream": False, "options": {**bench.OPTIONS, "num_predict": 1}})
    print(f"  chargement + chauffe (exclus des mesures) : {time.time() - t:.1f}s", flush=True)
    ps = {m["name"]: m for m in bench.api("/api/ps").get("models", [])}.get(model, {})
    rows = []
    for c in cas:
        try:
            r = bench.api("/api/chat", {"model": model, "messages": bench.build_messages(c, contexts),
                                        "stream": False, "options": bench.OPTIONS})
            answer = r["message"]["content"].strip()
            perf = {"total_s": round(r["total_duration"] / 1e9, 2), "tokens": r.get("eval_count", 0),
                    "tok_s": round(r.get("eval_count", 0) / max(r.get("eval_duration", 1) / 1e9, 1e-9), 1)}
            error = None
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            answer, perf, error = "", {}, str(exc)
        checks = checks_cas(c, answer) if not error else {}
        row = {"model": model, "id": c["id"], "dimension": c["dimension"], "origine": c["origine"],
               "type": c["type"], "question": c["question"], "expected": c["expected"], "answer": answer,
               "checks": checks, "score": score_cas(c, checks) if checks else 0.0, "perf": perf, "error": error,
               "ram_gb": round(ps.get("size", 0) / 1e9, 2)}
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
        out.flush()
        rows.append(row)
        statut = f"ERREUR {error}" if error else f"{row['score']:.2f} | {perf['total_s']:>6.1f}s | {perf['tok_s']:>5.1f} tok/s"
        print(f"  {c['id']:<7}{c['dimension']:<13}{statut}", flush=True)
    return rows


def synthese(rows: list[dict], cm: dict, modeles: list[str]) -> dict:
    poids, regle = cm["poids"], cm["regle_de_decision"]
    res = {}
    for model in modeles:
        rs = [r for r in rows if r["model"] == model]
        ok = [r for r in rs if not r["error"]]
        dims: dict[str, float | None] = {}
        for d in poids:
            if d == "Performance":
                continue
            sc = [r["score"] for r in rs if r["dimension"] == d]
            dims[d] = round(sum(sc) / len(sc), 2) if sc else None
        lat = sum(r["perf"]["total_s"] for r in ok) / len(ok) if ok else None
        dims["Performance"] = round(min(1.0, regle["latence_cible_s"] / lat), 2) if lat else 0.0
        presentes = [d for d in poids if dims[d] is not None]
        total = sum(poids[d] * dims[d] for d in presentes) / sum(poids[d] for d in presentes)
        # total « brut » = notes du log d'origine, avant la relecture (identique au total si pas de relecture)
        brut: dict[str, float | None] = {"Performance": dims["Performance"]}
        for d in poids:
            if d != "Performance":
                sc = [r.get("score_brut", r["score"]) for r in rs if r["dimension"] == d]
                brut[d] = round(sum(sc) / len(sc), 2) if sc else None
        pb = [d for d in poids if brut[d] is not None]
        total_brut = sum(poids[d] * brut[d] for d in pb) / sum(poids[d] for d in pb)
        refus =[bool(r["checks"].get("refus_correct")) for r in ok if "refus_correct" in r["checks"]]
        v01 = [r["score"] for r in rs if r["origine"] == "v0.1"]
        res[model] = {
            "dimensions": dims, "total": round(total, 3), "total_brut": round(total_brut, 3),
            "note_sur_5": round(total * 5, 2),
            "latence_moy_s": round(lat, 1) if lat else None, "ram_gb": rs[0]["ram_gb"] if rs else None,
            "refus_corrects": f"{sum(refus)}/{len(refus)}", "refus_ok": bool(refus) and all(refus),
            "score_v01_comparable": round(sum(v01) / len(v01), 2) if v01 else None,
            "erreurs": len(rs) - len(ok),
        }
        res[model]["retenu"] = (res[model]["total"] >= regle["score_minimum"] and res[model]["refus_ok"]
                                and lat is not None and lat <= regle["latence_cible_s"])
    return res


def changements(rows: list[dict], cm: dict) -> list[dict]:
    """Cas dont la note a changé entre le log d'origine et la version relue."""
    raisons = cm.get("corrections_relecture", {}).get("raisons", {})
    sortie = []
    for r in rows:
        if r.get("score_brut") is not None and abs(r["score"] - r["score_brut"]) > 1e-9:
            main = bool(r.get("corrige_a_la_main"))
            sortie.append({"model": r["model"], "id": r["id"], "brut": r["score_brut"], "relu": r["score"],
                           "raison": raisons.get(r["id"], "relecture manuelle") if main else
                           "détecteur de refus corrigé : la réponse est un refus correct non reconnu par la v0.1"})
    return sortie


def ecrire_synthese(path: Path, res: dict, cm: dict, nb_cas: int, rows: list[dict] | None = None) -> None:
    poids, regle = cm["poids"], cm["regle_de_decision"]
    dims = list(poids)
    L = [f"# Benchmark v0.2 : évaluation sur cas métier ({datetime.now():%d/%m/%Y %H:%M})\n",
         f"{nb_cas} cas (12 questions de la v0.1 + {nb_cas - 12 - sum(len(v) for v in cm['variations'].values())} cas ajoutés "
         f"+ {sum(len(v) for v in cm['variations'].values())} variations de formulation). Température 0, graine fixe, "
         "premier appel exclu des mesures.\n",
         "## Grille pondérée\n", "| Dimension | Poids | Mesure |", "|---|---|---|"]
    mesure = {"Exactitude": "mots-clés attendus, JSON valide", "Factualité": "refus clair quand l'info est absente, rien d'inventé",
              "Sécurité": "pièges, consigne cachée dans la source, jamais « non conforme » à tort",
              "Raisonnement": "calculs et croisements à justifier", "Robustesse": "taux de réussite sur des reformulations",
              "Pertinence": "respect du format, langue (approximation automatique)", "Performance": f"latence moyenne, cible {regle['latence_cible_s']} s"}
    L += [f"| {d} | {poids[d]} % | {mesure[d]} |" for d in dims]
    L += ["", "## Résultats\n", "| Modèle | " + " | ".join(dims) + " | **Total** | Total brut | Note /5 | Latence | Refus OK | v0.1 |",
          "|---|" + "---|" * (len(dims) + 6)]
    for m, r in res.items():
        L.append(f"| {m} | " + " | ".join("—" if r["dimensions"][d] is None else f"{r['dimensions'][d]:.2f}" for d in dims)
                 + f" | **{r['total']:.0%}** | {r['total_brut']:.0%} | {r['note_sur_5']:.2f} | {r['latence_moy_s']} s | {r['refus_corrects']} | {r['score_v01_comparable']} |")
    L.append("\n*Total brut = notes automatiques du log d'origine. Total = après correction du détecteur de refus et relecture (voir plus bas).*")
    L += ["", "## Décision\n",
          f"Règle : le plus petit modèle qui atteint {regle['score_minimum']:.0%} au total, ne se trompe sur aucun refus, "
          f"en {regle['latence_cible_s']} s ou moins par réponse.\n"]
    retenus = [m for m, r in res.items() if r["retenu"]]
    if retenus:
        L.append(f"**Retenu : {retenus[0]}** (le plus petit des modèles testés qui remplit les trois conditions).")
    else:
        L.append("**Aucun modèle ne remplit les trois conditions.** On le dit tel quel et on garde les gabarits "
                 "écrits par le code pour la démonstration : c'est un résultat, pas un échec.")
    L += ["", "| Modèle | ≥ seuil | refus OK | latence OK |", "|---|---|---|---|"]
    for m, r in res.items():
        L.append(f"| {m} | {'oui' if r['total'] >= regle['score_minimum'] else 'non'} | {'oui' if r['refus_ok'] else 'non'} "
                 f"| {'oui' if r['latence_moy_s'] and r['latence_moy_s'] <= regle['latence_cible_s'] else 'non'} |")
    L += ["", "## Limites (à dire honnêtement)\n",
          "- Les scores sont automatiques (mots-clés, formats, refus). Ils ne remplacent pas une relecture humaine : "
          "voir le fichier `-relecture.md`, à relire à la main sur au moins un modèle.",
          "- La pertinence est une approximation (format et langue) ; la sécurité repose sur une détection de mots "
          "(« non conforme », « illégal ») avec fenêtre de négation, donc quelques faux positifs ou négatifs sont possibles.",
          "- Les contextes sont fictifs et courts : un score élevé ici ne prouve rien sur un règlement réel de 23 pages (voir le RAG).",
          "- Un seul essai par cas : la température 0 et la graine fixe rendent le test reproductible, pas exhaustif."]
    ch = changements(rows, cm) if rows else []
    if ch:
        L += ["", "## Relecture : notes modifiées\n", "| Modèle | Cas | Brut | Relu | Raison |", "|---|---|---|---|---|"]
        L += [f"| {c['model']} | {c['id']} | {c['brut']:.2f} | {c['relu']:.2f} | {c['raison']} |" for c in ch]
        L += ["", f"*{cm['corrections_relecture']['_note']}*", f"*Grille Q12 : {cm['corrections_relecture']['grille_Q12']}*"]
    path.write_text("\n".join(L), encoding="utf-8")


def ecrire_relecture(path: Path, rows: list[dict], cas: list[dict]) -> None:
    L = ["# Réponses à relire à la main\n",
         "Pour chaque réponse : le score auto est-il juste ? Noter les désaccords.\n"]
    for c in cas:
        L += [f"\n## {c['id']} — {c['dimension']} ({c['type']})\n", f"**Question :** {c['question']}\n", f"**Attendu :** {c['expected']}\n"]
        for r in (r for r in rows if r["id"] == c["id"]):
            L += [f"\n### {r['model']} — auto {r['score']:.2f} ({r['perf'].get('total_s', '?')} s) {r['checks']}\n",
                  "~~~~text", r["answer"] or f"[ERREUR] {r['error']}", "~~~~"]
    path.write_text("\n".join(L), encoding="utf-8")


def rescorer(chemin: Path) -> None:
    """Recalcule la synthèse à partir des réponses déjà enregistrées (aucun appel au modèle)."""
    cas, _, cm = charger(None)
    par_id = {c["id"]: c for c in cas}
    corr = cm.get("corrections_relecture", {})
    appliquer = corr.get("run") == chemin.stem
    rows = [json.loads(ln) for ln in chemin.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for r in rows:
        r["score_brut"] = r.get("score_brut", r["score"])
        if not r["error"]:
            r["checks"] = checks_cas(par_id[r["id"]], r["answer"])
            r["score"] = score_cas(par_id[r["id"]], r["checks"])
        note = corr.get("cas", {}).get(r["id"], {}).get(r["model"]) if appliquer else None
        if note is not None:
            r["score"], r["corrige_a_la_main"] = note, True
    modeles = list(dict.fromkeys(r["model"] for r in rows))
    res = synthese(rows, cm, modeles)
    base = chemin.parent / f"{chemin.stem}-relu"
    with base.with_suffix(".jsonl").open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    ecrire_synthese(Path(f"{base}-synthese.md"), res, cm, len(par_id), rows)
    Path(f"{base}-synthese.json").write_text(json.dumps({"modeles": res, "changements": changements(rows, cm)},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
    for m, r in res.items():
        print(f"{m:<16} brut {r['total_brut']:.0%} -> relu {r['total']:.0%} | refus {r['refus_corrects']} | {r['latence_moy_s']} s | retenu: {r['retenu']}")
    print(f"\nSynthèse relue : {base}-synthese.md")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    p.add_argument("--only", nargs="+", help="identifiants de cas à garder (ex. Q01 S2 Q01-v1)")
    p.add_argument("--rescorer", type=Path, help="recalcule la synthèse d'un run existant (metier-*.jsonl), sans rappeler les modèles")
    args = p.parse_args()
    if args.rescorer:
        return rescorer(args.rescorer)

    cas, contexts, cm = charger(args.only)
    try:
        dispo = bench.installed_models()
    except urllib.error.URLError:
        sys.exit(f"Ollama injoignable sur {bench.OLLAMA} : lance l'application Ollama.")
    modeles = [m for m in args.models if m in dispo]
    for m in set(args.models) - set(modeles):
        print(f"[ignoré] {m} n'est pas installé (ollama pull {m})")
    if not modeles:
        sys.exit("Aucun modèle à tester.")

    results = HERE / "results"
    results.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    jsonl = results / f"metier-{stamp}.jsonl"
    print(f"{len(cas)} cas x {len(modeles)} modèles -> {jsonl.name}", flush=True)

    rows: list[dict] = []
    with jsonl.open("w", encoding="utf-8") as out:
        for m in modeles:
            rows += run_model(m, cas, contexts, out)

    res = synthese(rows, cm, modeles)
    ecrire_synthese(results / f"metier-{stamp}-synthese.md", res, cm, len(cas))
    (results / f"metier-{stamp}-synthese.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    ecrire_relecture(results / f"metier-{stamp}-relecture.md", rows, cas)
    print("\n=== Résumé ===")
    for m, r in res.items():
        print(f"{m:<16} total {r['total']:.0%} | note {r['note_sur_5']}/5 | {r['latence_moy_s']} s | refus {r['refus_corrects']} | retenu: {r['retenu']}")
    print(f"\nSynthèse : {results / f'metier-{stamp}-synthese.md'}")


if __name__ == "__main__":
    main()
