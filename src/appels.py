"""MART : la liste d'appels par événement, et la fiche de chaque compte.

Le classement est un calcul lisible, pas un modèle :
  score = 5 x produits « probable » (10 au plus) + 2 x produits « possible » (10 au plus) + 30 x part de « probable »
Les clients et les prospects sont classés séparément. Les textes sont des gabarits écrits par le code ;
ceux du LLM, une fois relus, les remplacent dans l'API (fichier gld_fct_textes_ia.csv).
"""
import pandas as pd

from commun import AUJOURDHUI, GOLD, MART, SILVER, ecrire, lire, pluriel
from detection import lire_produits

COLONNES = ["evenement_id", "compte_id", "nom_compte", "statut", "groupe_appel", "rang", "score", "raison_classement",
            "fait", "question", "nb_produits_analyses", "nb_probable", "nb_possible", "part_probable",
            "confiance", "date_calcul", "crm_fictif"]
COL_FICHE = ["compte_id", "evenement_id", "code", "marque", "nom", "niveau", "elements_directs", "elements_indices",
             "type_rincage", "date_fiche", "confiance", "reference_parfum", "ingredients"]


def score(nb_probable, nb_possible, nb_analyses):
    part = nb_probable / nb_analyses if nb_analyses else 0
    return round(5 * min(nb_probable, 10) + 2 * min(nb_possible, 10) + 30 * part)


def confiance(nb_analyses):
    """Peu de produits analysés : le classement est fragile."""
    return "bonne" if nb_analyses >= 20 else "moyenne" if nb_analyses >= 10 else "faible"


def elements_frequents(series, maximum=4):
    compte = pd.Series([e for cellule in series for e in cellule.split("|") if e]).value_counts()
    return ", ".join(compte.index[:maximum])


def raison(p, q, n):
    part = f" ({round(100 * p / n)} %)" if p else ""
    texte = f"{pluriel(p, 'produit')} sur {n} en exposition probable{part}"
    return texte + (f", {q} en exposition possible." if q else ".")


def fait(p, q, n, elements, source):
    if p:
        verbe = "liste" if p == 1 else "listent"
        return (f"{pluriel(p, 'produit')} sur {pluriel(n, 'analysé')} {verbe} au moins un ingrédient visé "
                f"({elements}). Source : {source}.")
    verbe = "contient" if q == 1 else "contiennent"
    return (f"{pluriel(q, 'produit')} sur {pluriel(n, 'analysé')} {verbe} un ingrédient proche ou un parfum "
            f"dont la composition n'est pas détaillée. Source : {source}.")


def main():
    impact = lire(GOLD / "gld_fct_impact_produit.csv")
    evenements = lire(GOLD / "gld_dim_evenements.csv").set_index("evenement_id")
    comptes = lire(GOLD / "gld_dim_comptes.csv").set_index("compte_id")
    marques = lire(SILVER / "clients/slv_ref_marques_comptes.csv")
    ventes = lire(SILVER / "ventes/slv_trd_ventes.csv")

    impact = impact.merge(marques[["marque", "compte_id"]], on="marque", how="inner")
    lignes = []
    for (evt_id, cid), g in impact.groupby(["evenement_id", "compte_id"]):
        n, p, q = len(g), int((g["niveau"] == "probable").sum()), int((g["niveau"] == "possible").sum())
        if p + q == 0 or cid not in comptes.index:
            continue
        evt, c = evenements.loc[evt_id], comptes.loc[cid]
        lignes.append({"evenement_id": evt_id, "compte_id": cid, "nom_compte": c["nom_compte"], "statut": c["statut"],
                       "groupe_appel": c["statut"] + "s", "rang": 0, "score": score(p, q, n),
                       "raison_classement": raison(p, q, n),
                       "fait": fait(p, q, n, elements_frequents(g["elements_directs"]), evt["source_nom"]),
                       "question": evt["question_type"], "nb_produits_analyses": n, "nb_probable": p,
                       "nb_possible": q, "part_probable": round(p / n, 2), "confiance": confiance(n),
                       "date_calcul": AUJOURDHUI, "crm_fictif": "oui"})
    appels = pd.DataFrame(lignes, columns=COLONNES)
    if len(appels):
        appels = appels.sort_values(["evenement_id", "groupe_appel", "score", "nb_probable", "compte_id"],
                                    ascending=[True, True, False, False, True])
        appels["rang"] = appels.groupby(["evenement_id", "groupe_appel"]).cumcount() + 1
    ecrire(appels, MART / "mrt_liste_appels.csv")

    # --- fiche compte : les produits touchés, événement par événement
    parfums = ventes[ventes["code_produit"] != ""].drop_duplicates("code_produit").set_index("code_produit")["reference_parfum"]
    fiche = impact[impact["niveau"].isin(["probable", "possible"])].copy()
    fiche["reference_parfum"] = fiche["code"].map(parfums).fillna("")
    # L'étiquette telle quelle : l'application y surligne les ingrédients repérés.
    fiche["ingredients"] = fiche["code"].map(lire_produits().set_index("code")["ingredients"]).fillna("")
    fiche = fiche.sort_values(["compte_id", "evenement_id", "niveau", "nb_directs", "code"],
                              ascending=[True, True, False, False, True])[COL_FICHE]
    ecrire(fiche, MART / "mrt_fiche_compte.csv")

    print(f"Liste d'appels : {len(appels)} lignes, fiche compte : {len(fiche)} produits touchés")
    if len(appels):
        print(appels[["evenement_id", "groupe_appel", "rang", "nom_compte", "score", "raison_classement"]].to_string(index=False))


if __name__ == "__main__":
    main()
