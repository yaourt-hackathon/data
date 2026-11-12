"""GOLD + MART : exposition des produits aux nouveaux allergènes (règles, pas de LLM)."""
import re
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

SILVER_PRODUITS = Path("data/02_silver/produits/slv_msd_produits.csv")
SILVER_REF = Path("data/02_silver/reglementation/slv_ref_allergenes.csv")
GOLD = Path("data/03_gold")
MART = Path("data/04_mart")


def normaliser(texte):
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\s[-–•·]\s|\n|;", ", ", t)
    t = t.replace("*", "")
    return re.sub(r"\s+", " ", t).strip()


def trouver(texte, ref):
    trouves = []
    for _, a in ref.iterrows():
        if a["type"] == "substance":
            motif = r"(?<![a-z])" + re.escape(a["motif_recherche"]) + r"(?![a-z])"
        else:
            motif = a["motif_recherche"]
        if re.search(motif, texte):
            trouves.append(a["nom_usuel"])
    return trouves


def niveau(nouvelles, anciennes, parfum):
    if nouvelles:
        return "probable", "ingrédient de la nouvelle liste lu sur l'étiquette"
    if parfum and anciennes:
        return "possible", "parfum + anciens allergènes : composition du parfum non détaillée"
    if parfum:
        return "indetermine", "parfum sans détail"
    return "non_detecte", "aucun ingrédient de la liste détecté"


def main():
    produits = pd.read_csv(SILVER_PRODUITS, dtype={"code": str})
    ref = pd.read_csv(SILVER_REF)
    ref_nouv, ref_anc = ref[ref["liste"] == "nouvelle"], ref[ref["liste"] == "ancienne"]

    lignes = []
    for _, p in produits.iterrows():
        t = normaliser(p["ingredients"])
        nouv, anc = trouver(t, ref_nouv), trouver(t, ref_anc)
        parfum = bool(re.search(r"(?<![a-z])(parfum|fragrance)(?![a-z])", t))
        niv, motif = niveau(nouv, anc, parfum)
        lignes.append({"code": p["code"], "marque": p["marque"], "nom": p["nom"], "type_rincage": p["type_rincage"],
                       "niveau": niv, "nouvelles_substances": "|".join(nouv), "nb_nouvelles": len(nouv),
                       "anciennes_substances": "|".join(anc), "nb_anciennes": len(anc), "contient_parfum": parfum,
                       "motif": motif, "date_fiche": p["date_fiche"], "source": p["source"]})
    gold = pd.DataFrame(lignes)

    mart = gold.pivot_table(index="marque", columns="niveau", values="code", aggfunc="count", fill_value=0)
    for n in ["probable", "possible", "indetermine", "non_detecte"]:
        if n not in mart.columns:
            mart[n] = 0
    mart = mart[["probable", "possible", "indetermine", "non_detecte"]].add_prefix("nb_").reset_index()
    mart.insert(1, "nb_produits", mart[["nb_probable", "nb_possible", "nb_indetermine", "nb_non_detecte"]].sum(axis=1))
    mart["part_probable"] = (mart["nb_probable"] / mart["nb_produits"]).round(2)
    mart["urgence"] = pd.cut(mart["part_probable"], [-0.01, 0, 0.25, 1], labels=["faible", "moyenne", "haute"])
    mart["date_calcul"] = str(date.today())
    mart = mart.sort_values("nb_probable", ascending=False)

    GOLD.mkdir(parents=True, exist_ok=True)
    MART.mkdir(parents=True, exist_ok=True)
    gold.to_csv(GOLD / "gld_fct_exposition_produit.csv", index=False)
    mart.to_csv(MART / "mrt_notedetete_fct_exposition_marque.csv", index=False)

    print(gold["niveau"].value_counts().to_string())
    print()
    print(mart.to_string(index=False))


if __name__ == "__main__":
    main()