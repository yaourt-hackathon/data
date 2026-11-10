"""API Note de tête — lit le MART (par marque) et le GOLD (par produit). Aucune règle ici."""
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

RACINE = Path(__file__).resolve().parent.parent
MART = RACINE / "data/04_mart/mrt_notedetete_fct_exposition_marque.csv"
GOLD = RACINE / "data/03_gold/gld_fct_exposition_produit.csv"

app = FastAPI(
    title="API Note de tête",
    description="Équipe 7 · Yaourt — exposition des marques aux nouveaux allergènes (UE 2023/1545). "
                "Données réelles Open Beauty Facts. Liste d'allergènes provisoire, à vérifier sur EUR-Lex. "
                "On parle d'« exposition probable », jamais de « non-conformité ».",
    version="0.2.0",
)

SOURCE = {"reglement": "UE 2023/1545", "catalogue": "Open Beauty Facts (ODbL)",
          "echeance_produits_en_rayon": "2028-07-31", "statut_liste_allergenes": "a_verifier_eurlex"}


def lire(chemin):
    if not chemin.exists():
        raise HTTPException(status_code=503, detail=f"Données absentes : {chemin.name}. Lancer le pipeline.")
    return pd.read_csv(chemin, dtype={"code": str}).fillna("")


@app.get("/health", tags=["Technique"])
def health():
    """Vérifie que l'API répond et que les données sont là."""
    return {"status": "ok", "factice": False, "mart_present": MART.exists(), "gold_present": GOLD.exists()}


@app.get("/marques", tags=["Exposition"])
def marques():
    """Marques suivies, triées par nombre de produits « probable »."""
    mart = lire(MART)
    lignes = [{"id": r["marque"], "marque": r["marque"], "nb_produits": int(r["nb_produits"]),
               "nb_probable": int(r["nb_probable"]), "urgence": r["urgence"]} for _, r in mart.iterrows()]
    return {"factice": False, "date_maj": mart["date_calcul"].iloc[0], "marques": lignes}


@app.get("/exposition", tags=["Exposition"])
def exposition(marque: str = Query(..., description="Identifiant de la marque, ex. florame")):
    """Diagnostic d'une marque, avec chaque produit, son niveau et la substance trouvée."""
    mart, gold = lire(MART), lire(GOLD)
    ligne = mart[mart["marque"] == marque.lower()]
    if ligne.empty:
        raise HTTPException(status_code=404, detail=f"Marque inconnue : {marque}")
    m = ligne.iloc[0]
    produits = gold[gold["marque"] == marque.lower()].sort_values("nb_nouvelles", ascending=False)
    return {
        "factice": False, "date_maj": m["date_calcul"], "source": SOURCE,
        "marque": m["marque"], "nb_produits": int(m["nb_produits"]), "nb_probable": int(m["nb_probable"]),
        "nb_possible": int(m["nb_possible"]), "nb_indetermine": int(m["nb_indetermine"]),
        "nb_non_detecte": int(m["nb_non_detecte"]), "urgence": m["urgence"],
        "produits": [{"code_barre": p["code"], "nom": p["nom"], "niveau": p["niveau"],
                      "substances": [s for s in p["nouvelles_substances"].split("|") if s],
                      "anciens_allergenes": [s for s in p["anciennes_substances"].split("|") if s],
                      "type_rincage": p["type_rincage"], "motif": p["motif"], "date_fiche": p["date_fiche"]}
                     for _, p in produits.iterrows()],
    }
