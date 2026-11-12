"""API Note de tête — lit le MART et le GOLD. Aucune règle ici : tout est calculé par pipeline.py.

Règle de livraison : on ajoute des routes et des champs, on ne renomme ni ne retire rien
(l'application génère son client à partir de /openapi.json).
"""
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

RACINE = Path(__file__).resolve().parent.parent
MART = RACINE / "data/04_mart/mrt_notedetete_fct_exposition_marque.csv"
GOLD = RACINE / "data/03_gold/gld_fct_exposition_produit.csv"
EVENEMENTS = RACINE / "data/03_gold/gld_dim_evenements.csv"
COMPTES = RACINE / "data/03_gold/gld_dim_comptes.csv"
TEXTES_IA = RACINE / "data/03_gold/gld_fct_textes_ia.csv"
APPELS = RACINE / "data/04_mart/mrt_liste_appels.csv"
FICHE = RACINE / "data/04_mart/mrt_fiche_compte.csv"

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
    appels_present: bool = Field(False, description="La liste d'appels est calculée")


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


Confiance = Literal["faible", "moyenne", "bonne"]


class Evenement(BaseModel):
    evenement_id: str = Field(..., examples=["EVT-001"])
    type: str = Field(..., examples=["reglementation"])
    titre: str
    resume: str
    source_nom: str = Field(..., examples=["Règlement (UE) 2023/1545"])
    source_url: str
    date_publication: str
    date_echeance: str = Field(..., description="Vide s'il n'y a pas d'échéance")
    statut_validation: Literal["valide", "test"] = Field(..., description="« test » : événement d'essai, pas un fait réel")
    nb_comptes_a_appeler: int = Field(0, description="Comptes présents dans la liste d'appels")


class ListeEvenements(BaseModel):
    date_maj: str
    evenements: list[Evenement]


class Appel(BaseModel):
    rang: int = Field(..., description="Rang dans son groupe (clients ou prospects)")
    compte_id: str = Field(..., examples=["CPT-001"])
    nom_compte: str
    statut: Literal["client", "prospect"] = Field(..., description="Fictif : inventé pour la démonstration")
    score: int = Field(..., description="5 x probable (max 10) + 2 x possible (max 10) + 30 x part de probable")
    raison_classement: str = Field(..., description="Phrase écrite par le code à partir des nombres")
    fait: str = Field(..., description="Le fait à dire au client, avec sa source")
    question: str = Field(..., description="La question à poser")
    origine_textes: Literal["gabarit", "llm_valide"] = Field(..., description="gabarit : écrit par le code. llm_valide : écrit par le LLM local et relu par une personne")
    nb_produits_analyses: int
    nb_probable: int
    nb_possible: int
    part_probable: float
    confiance: Confiance = Field(..., description="faible si moins de 10 produits analysés, bonne à partir de 20")


class ListeAppels(BaseModel):
    date_maj: str
    crm_fictif: bool = Field(..., description="Toujours vrai : les comptes et leur statut sont inventés")
    evenement: Evenement
    clients: list[Appel]
    prospects: list[Appel]


class ProduitTouche(BaseModel):
    code_barre: str
    marque: str
    nom: str
    niveau: Literal["probable", "possible"]
    elements_directs: list[str] = Field(..., description="Ingrédients visés lus sur l'étiquette")
    elements_indices: list[str] = Field(..., description="Ingrédients proches lus sur l'étiquette")
    type_rincage: Rincage
    date_fiche: str
    reference_parfum: str = Field(..., description="Référence fictive du parfum vendu pour ce produit, vide sinon")


class EvenementCompte(BaseModel):
    evenement_id: str
    titre: str
    rang: int
    score: int
    fait: str
    question: str
    produits: list[ProduitTouche]


class Compte(BaseModel):
    date_maj: str
    crm_fictif: bool
    compte_id: str
    nom_compte: str
    statut: Literal["client", "prospect"]
    pays: str
    segment: str
    commercial: str = Field(..., description="Un code, jamais un nom de personne", examples=["KAM-01"])
    dernier_contact: str
    marques: list[str]
    nb_produits_analyses: int
    classe_ca: str = Field(..., description="A, B ou C. Fictif. Vide pour un prospect")
    nb_parfums: int = Field(..., description="Parfums vendus au compte (fictif)")
    quantite_kg_annee: int = Field(..., description="Quantité vendue la dernière année (fictif)")
    evenements: list[EvenementCompte]


app = FastAPI(
    title="API Note de tête",
    description="Équipe 7 · Yaourt — d'un événement à une liste d'appels de clients et de prospects. "
                "Les comptes, leur statut et les ventes sont fictifs. "
                "Données réelles Open Beauty Facts. Liste d'allergènes provisoire, à vérifier sur EUR-Lex. "
                "On parle d'« exposition probable », jamais de « non-conformité ».",
    version="0.4.0",
)

SOURCE = {"reglement": "UE 2023/1545", "catalogue": "Open Beauty Facts (ODbL)",
          "echeance_produits_en_rayon": "2028-07-31", "statut_liste_allergenes": "a_verifier_eurlex"}
ERREURS = {404: {"model": Erreur, "description": "Marque inconnue"},
           503: {"model": Erreur, "description": "Données absentes : lancer le pipeline"}}


def lire(chemin):
    if not chemin.exists():
        raise HTTPException(status_code=503, detail=f"Données absentes : {chemin.name}. Lancer le pipeline.")
    # Tout en texte, comme les scripts du pipeline : une case vide reste une chaîne vide,
    # et les codes-barres gardent leurs zéros. Les nombres sont convertis au moment de répondre.
    return pd.read_csv(chemin, dtype=str, keep_default_na=False, encoding="utf-8")


@app.get("/", include_in_schema=False)
def racine():
    """L'adresse de base ouvre directement Swagger."""
    return RedirectResponse("/docs")


@app.get("/health", tags=["Technique"], response_model=Sante)
def health():
    """Vérifie que l'API répond et que les données sont là."""
    return {"status": "ok", "factice": False, "mart_present": MART.exists(), "gold_present": GOLD.exists(),
            "appels_present": APPELS.exists()}


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


def liste(cellule):
    return [x for x in str(cellule).split("|") if x]


def evenement_json(e, appels):
    return {"evenement_id": e["evenement_id"], "type": e["type"], "titre": e["titre"], "resume": e["resume"],
            "source_nom": e["source_nom"], "source_url": e["source_url"], "date_publication": e["date_publication"],
            "date_echeance": e["date_echeance"], "statut_validation": e["statut_validation"],
            "nb_comptes_a_appeler": int((appels["evenement_id"] == e["evenement_id"]).sum())}


def textes_valides():
    """Textes du LLM relus par une personne : {(evenement, compte, type): texte}. Vide tant que le fichier n'existe pas."""
    if not TEXTES_IA.exists():
        return {}
    t = pd.read_csv(TEXTES_IA, dtype=str).fillna("")
    t = t[t["statut_validation"] == "valide"]
    return {(r["evenement_id"], r["compte_id"], r["type_texte"]): r["texte"] for _, r in t.iterrows()}


def appel_json(a, textes):
    cle = (a["evenement_id"], a["compte_id"])
    fait, question = textes.get(cle + ("fait",)), textes.get(cle + ("question",))
    return {"rang": int(a["rang"]), "compte_id": a["compte_id"], "nom_compte": a["nom_compte"], "statut": a["statut"],
            "score": int(a["score"]), "raison_classement": a["raison_classement"],
            "fait": fait or a["fait"], "question": question or a["question"],
            "origine_textes": "llm_valide" if fait or question else "gabarit",
            "nb_produits_analyses": int(a["nb_produits_analyses"]), "nb_probable": int(a["nb_probable"]),
            "nb_possible": int(a["nb_possible"]), "part_probable": float(a["part_probable"]), "confiance": a["confiance"]}


def date_maj(appels):
    return str(appels["date_calcul"].iloc[0]) if len(appels) else ""


ERREURS_EVT = {404: {"model": Erreur, "description": "Événement inconnu"}, 503: ERREURS[503]}
ERREURS_CPT = {404: {"model": Erreur, "description": "Compte inconnu"}, 503: ERREURS[503]}


@app.get("/evenements", tags=["Liste d'appels"], response_model=ListeEvenements, responses={503: ERREURS[503]})
def evenements():
    """Les événements calculés. Un événement n'apparaît ici qu'après validation par une personne."""
    evts, appels = lire(EVENEMENTS), lire(APPELS)
    return {"date_maj": date_maj(appels), "evenements": [evenement_json(e, appels) for _, e in evts.iterrows()]}


@app.get("/evenements/{evenement_id}/appels", tags=["Liste d'appels"], response_model=ListeAppels, responses=ERREURS_EVT)
def appels_evenement(evenement_id: str):
    """La liste d'appels d'un événement : les clients, puis les prospects, chacun classé avec sa raison."""
    evts, appels = lire(EVENEMENTS), lire(APPELS)
    ligne = evts[evts["evenement_id"] == evenement_id.upper()]
    if ligne.empty:
        raise HTTPException(status_code=404, detail=f"Événement inconnu : {evenement_id}")
    textes = textes_valides()
    a = appels[appels["evenement_id"] == evenement_id.upper()].sort_values("rang")
    groupe = lambda g: [appel_json(r, textes) for _, r in a[a["groupe_appel"] == g].iterrows()]
    return {"date_maj": date_maj(appels), "crm_fictif": True, "evenement": evenement_json(ligne.iloc[0], appels),
            "clients": groupe("clients"), "prospects": groupe("prospects")}


@app.get("/comptes/{compte_id}", tags=["Liste d'appels"], response_model=Compte, responses=ERREURS_CPT)
def compte(compte_id: str):
    """La fiche d'un compte : ses marques, et pour chaque événement qui le touche, les produits concernés."""
    comptes, evts, appels, fiche = lire(COMPTES), lire(EVENEMENTS), lire(APPELS), lire(FICHE)
    ligne = comptes[comptes["compte_id"] == compte_id.upper()]
    if ligne.empty:
        raise HTTPException(status_code=404, detail=f"Compte inconnu : {compte_id}")
    c, textes = ligne.iloc[0], textes_valides()
    titres = evts.set_index("evenement_id")["titre"].to_dict()
    blocs = []
    for _, a in appels[appels["compte_id"] == c["compte_id"]].sort_values("evenement_id").iterrows():
        j = appel_json(a, textes)
        produits = fiche[(fiche["compte_id"] == c["compte_id"]) & (fiche["evenement_id"] == a["evenement_id"])]
        blocs.append({"evenement_id": a["evenement_id"], "titre": titres.get(a["evenement_id"], ""), "rang": j["rang"],
                      "score": j["score"], "fait": j["fait"], "question": j["question"],
                      "produits": [{"code_barre": p["code"], "marque": p["marque"], "nom": p["nom"], "niveau": p["niveau"],
                                    "elements_directs": liste(p["elements_directs"]),
                                    "elements_indices": liste(p["elements_indices"]), "type_rincage": p["type_rincage"],
                                    "date_fiche": str(p["date_fiche"]), "reference_parfum": p["reference_parfum"]}
                                   for _, p in produits.iterrows()]})
    return {"date_maj": date_maj(appels), "crm_fictif": True, "compte_id": c["compte_id"], "nom_compte": c["nom_compte"],
            "statut": c["statut"], "pays": c["pays"], "segment": c["segment"], "commercial": c["commercial"],
            "dernier_contact": c["dernier_contact"], "marques": liste(c["marques"]),
            "nb_produits_analyses": int(c["nb_produits_analyses"]), "classe_ca": c["classe_ca"],
            "nb_parfums": int(c["nb_parfums"]), "quantite_kg_annee": int(c["quantite_kg_annee"]), "evenements": blocs}
