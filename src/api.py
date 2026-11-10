"""API Note de tête — version factice pour le Gate 1.
Les réponses ont la forme définitive ; les chiffres sont fictifs (champ "factice": true)."""
from datetime import date
from fastapi import FastAPI, HTTPException, Query

app = FastAPI(
    title="API Note de tête",
    description="Équipe 7 · Yaourt — exposition des marques aux nouveaux allergènes (UE 2023/1545). "
                "Version factice : formes définitives, données fictives.",
    version="0.1.0",
)

MARQUES = {
    "maison-verte": {
        "marque": "Maison Verte", "nb_produits": 31, "nb_probable": 9, "nb_possible": 6,
        "nb_indetermine": 4, "nb_non_detecte": 12, "urgence": "haute",
        "produits": [
            {"code_barre": "0000000000001", "nom": "Eau de toilette Fleur d'oranger", "niveau": "probable",
             "substances": ["menthol", "camphor"], "type_rincage": "non_rince"},
            {"code_barre": "0000000000002", "nom": "Gel douche Lavande", "niveau": "possible",
             "substances": ["linalool"], "type_rincage": "rince"},
        ],
    },
    "atelier-nord": {
        "marque": "Atelier Nord", "nb_produits": 14, "nb_probable": 2, "nb_possible": 3,
        "nb_indetermine": 1, "nb_non_detecte": 8, "urgence": "moyenne", "produits": [],
    },
}

SOURCE = {"reglement": "UE 2023/1545", "catalogue": "Open Beauty Facts (ODbL)",
          "echeance_produits_en_rayon": "2028-07-31"}


@app.get("/health", tags=["Technique"])
def health():
    """Vérifie que l'API répond."""
    return {"status": "ok", "factice": True}


@app.get("/marques", tags=["Exposition"])
def marques():
    """Liste des marques suivies, triées par nombre de produits « probable »."""
    lignes = [{"id": k, "marque": v["marque"], "nb_produits": v["nb_produits"],
               "nb_probable": v["nb_probable"], "urgence": v["urgence"]} for k, v in MARQUES.items()]
    return {"factice": True, "date_maj": str(date.today()),
            "marques": sorted(lignes, key=lambda x: -x["nb_probable"])}


@app.get("/exposition", tags=["Exposition"])
def exposition(marque: str = Query(..., description="Identifiant de la marque, ex. maison-verte")):
    """Diagnostic d'une marque : « exposition probable », jamais « non conforme »."""
    m = MARQUES.get(marque.lower())
    if m is None:
        raise HTTPException(status_code=404, detail=f"Marque inconnue : {marque}")
    return {"factice": True, "date_maj": str(date.today()), "source": SOURCE, **m}
