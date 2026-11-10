"""API Note de tête — lit le MART (par marque) et le GOLD (par produit). Aucune règle ici."""
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

RACINE = Path(__file__).resolve().parent.parent
MART = RACINE / "data/04_mart/mrt_notedetete_fct_exposition_marque.csv"
GOLD = RACINE / "data/03_gold/gld_fct_exposition_produit.csv"

Niveau = Literal["probable", "possible", "indetermine", "non_detecte"]
Urgence = Literal["faible", "moyenne", "haute"]
Rincage = Literal["rince", "non_rince", "indetermine"]


class Erreur(BaseModel):
    detail: str = Field(..., examples=["Marque inconnue : xyz"])


class Sante(BaseModel):
    status: str = Field(..., examples=["ok"])
    factice: bool
    mart_present: bool
    gold_present: bool


class MarqueResume(BaseModel):
    id: str = Field(..., description="Identifiant à passer à /exposition", examples=["florame"])
    marque: str
    nb_produits: int = Field(..., description="Produits analysables (silver)")
    nb_probable: int = Field(..., description="Produits en exposition probable")
    urgence: Urgence = Field(..., description="haute si plus de 25 % de probables, moyenne si au moins 1")


class ListeMarques(BaseModel):
    factice: bool
    date_maj: str = Field(..., examples=["2026-11-10"])
    marques: list[MarqueResume]


class Source(BaseModel):
    reglement: str = Field(..., examples=["UE 2023/1545"])
    catalogue: str = Field(..., examples=["Open Beauty Facts (ODbL)"])
    echeance_produits_en_rayon: str = Field(..., examples=["2028-07-31"])
    statut_liste_allergenes: str = Field(..., examples=["a_verifier_eurlex"])


class Produit(BaseModel):
    code_barre: str = Field(..., examples=["3516170018624"])
    nom: str
    niveau: Niveau
    substances: list[str] = Field(..., description="Allergènes de la NOUVELLE liste lus sur l'étiquette")
    anciens_allergenes: list[str] = Field(..., description="Allergènes de l'ancienne liste lus sur l'étiquette")
    type_rincage: Rincage
    motif: str = Field(..., description="Pourquoi ce niveau")
    date_fiche: str = Field(..., description="Dernière mise à jour de la fiche Open Beauty Facts")


class Exposition(BaseModel):
    factice: bool
    date_maj: str
    source: Source
    marque: str
    nb_produits: int
    nb_probable: int
    nb_possible: int
    nb_indetermine: int
    nb_non_detecte: int
    urgence: Urgence
    produits: list[Produit]


app = FastAPI(
    title="API Note de tête",
    description="Équipe 7 · Yaourt — exposition des marques aux nouveaux allergènes (UE 2023/1545). "
                "Données réelles Open Beauty Facts. Liste d'allergènes provisoire, à vérifier sur EUR-Lex. "
                "On parle d'« exposition probable », jamais de « non-conformité ».",
    version="0.3.0",
)

SOURCE = {"reglement": "UE 2023/1545", "catalogue": "Open Beauty Facts (ODbL)",
          "echeance_produits_en_rayon": "2028-07-31", "statut_liste_allergenes": "a_verifier_eurlex"}
ERREURS = {404: {"model": Erreur, "description": "Marque inconnue"},
           503: {"model": Erreur, "description": "Données absentes : lancer le pipeline"}}


def lire(chemin):
    if not chemin.exists():
        raise HTTPException(status_code=503, detail=f"Données absentes : {chemin.name}. Lancer le pipeline.")
    return pd.read_csv(chemin, dtype={"code": str}).fillna("")


@app.get("/health", tags=["Technique"], response_model=Sante)
def health():
    """Vérifie que l'API répond et que les données sont là."""
    return {"status": "ok", "factice": False, "mart_present": MART.exists(), "gold_present": GOLD.exists()}


@app.get("/marques", tags=["Exposition"], response_model=ListeMarques, responses={503: ERREURS[503]})
def marques():
    """Marques suivies, triées par nombre de produits « probable »."""
    mart = lire(MART)
    lignes = [{"id": r["marque"], "marque": r["marque"], "nb_produits": int(r["nb_produits"]),
               "nb_probable": int(r["nb_probable"]), "urgence": r["urgence"]} for _, r in mart.iterrows()]
    return {"factice": False, "date_maj": str(mart["date_calcul"].iloc[0]), "marques": lignes}


@app.get("/exposition", tags=["Exposition"], response_model=Exposition, responses=ERREURS)
def exposition(marque: str = Query(..., description="Identifiant de la marque", examples=["florame"])):
    """Diagnostic d'une marque, avec chaque produit, son niveau et la substance trouvée."""
    mart, gold = lire(MART), lire(GOLD)
    ligne = mart[mart["marque"] == marque.lower()]
    if ligne.empty:
        raise HTTPException(status_code=404, detail=f"Marque inconnue : {marque}")
    m = ligne.iloc[0]
    produits = gold[gold["marque"] == marque.lower()].sort_values("nb_nouvelles", ascending=False)
    return {
        "factice": False, "date_maj": str(m["date_calcul"]), "source": SOURCE,
        "marque": m["marque"], "nb_produits": int(m["nb_produits"]), "nb_probable": int(m["nb_probable"]),
        "nb_possible": int(m["nb_possible"]), "nb_indetermine": int(m["nb_indetermine"]),
        "nb_non_detecte": int(m["nb_non_detecte"]), "urgence": m["urgence"],
        "produits": [{"code_barre": p["code"], "nom": p["nom"], "niveau": p["niveau"],
                      "substances": [s for s in p["nouvelles_substances"].split("|") if s],
                      "anciens_allergenes": [s for s in p["anciennes_substances"].split("|") if s],
                      "type_rincage": p["type_rincage"], "motif": p["motif"], "date_fiche": str(p["date_fiche"])}
                     for _, p in produits.iterrows()],
    }