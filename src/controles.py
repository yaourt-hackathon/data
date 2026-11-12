"""CONTRÔLES : ce qui doit toujours être vrai après un recalcul. Une seule erreur arrête le pipeline."""
import re

import pandas as pd

from commun import BRONZE, GOLD, MART, SILVER, lire, slug
from detection import lire_produits

INTERDITS = re.compile(r"non[ -]conform|ill[ée]gal|interdit", re.I)


def controler():
    erreurs = []

    def verifier(condition, message):
        if not condition:
            erreurs.append(message)

    attendus = [SILVER / "produits/slv_msd_produits.csv", SILVER / "evenements/slv_ref_evenements.csv",
                SILVER / "evenements/slv_ref_regles_detection.csv", SILVER / "clients/slv_msd_comptes.csv",
                SILVER / "clients/slv_ref_marques_comptes.csv", GOLD / "gld_dim_evenements.csv",
                GOLD / "gld_fct_impact_produit.csv", GOLD / "gld_dim_comptes.csv", MART / "mrt_liste_appels.csv",
                MART / "mrt_fiche_compte.csv", MART / "mrt_notedetete_fct_exposition_marque.csv"]
    absents = [f.name for f in attendus if not f.exists()]
    if absents:
        return [f"fichiers absents : {absents}"]

    produits, impact = lire_produits(), lire(GOLD / "gld_fct_impact_produit.csv")
    evenements, comptes = lire(GOLD / "gld_dim_evenements.csv"), lire(GOLD / "gld_dim_comptes.csv")
    marques, appels = lire(SILVER / "clients/slv_ref_marques_comptes.csv"), lire(MART / "mrt_liste_appels.csv")

    # produits : rien ne se perd entre le bronze et le silver
    bronze = sorted((BRONZE / "produits").glob("brz_msd_produits_obf_*.csv"))[-1]
    nb_bronze = lire(bronze)["code"].nunique()
    nb_silver = len(lire(SILVER / "produits/slv_msd_produits.csv")) + len(lire(SILVER / "produits/slv_msd_produits_rejets.csv"))
    verifier(nb_bronze == nb_silver, f"produits : {nb_bronze} en bronze mais {nb_silver} retenus + rejetés en silver")
    verifier(len(produits) > 0, "aucun produit analysable")
    verifier(not (produits["code"] == "").any(), "produit sans code")
    verifier(produits["code"].is_unique, "code produit en double")
    # Deux références d'une même source (deux contenances) sont normales ; le même produit
    # vu par deux sources ne l'est pas : lire_produits() doit l'avoir rapproché.
    cles = produits.assign(cle=produits.apply(lambda l: slug(l["marque"]) + "::" + slug(l["nom"]), axis=1))
    cles = cles[cles["cle"] != "::"]
    vues = cles.groupby("cle")["source"].nunique()
    doublons = sorted(vues[vues > 1].index)
    verifier(not doublons, f"même produit vu par deux sources et non rapproché : {doublons[:3]}")

    # chaque marque collectée est rattachée à un compte
    sans_compte = sorted(set(produits["marque"]) - set(marques["marque"]))
    verifier(not sans_compte, f"marques sans compte dans marques_comptes_fictif.csv : {sans_compte}")
    verifier(set(marques["compte_id"]) <= set(comptes["compte_id"]), "marque rattachée à un compte inconnu")
    verifier((comptes["fictif"] == "oui").all(), "compte non marqué fictif")

    # détection : un produit x un événement, une seule fois, avec un niveau connu
    verifier(len(impact) == len(produits) * len(evenements),
             f"impact : {len(impact)} lignes au lieu de {len(produits)} x {len(evenements)}")
    verifier(not impact.duplicated(subset=["evenement_id", "code"]).any(), "impact : produit en double pour un événement")
    verifier(impact["niveau"].isin(["probable", "possible", "indetermine", "non_detecte"]).all(), "impact : niveau inconnu")
    probables = impact[impact["niveau"] == "probable"]
    verifier((probables["elements_directs"] != "").all(), "produit « probable » sans ingrédient cité")

    # liste d'appels : cohérente avec la détection, rangs sans trou, vocabulaire tenu
    if len(appels):
        nb = appels[["nb_produits_analyses", "nb_probable", "nb_possible", "rang"]].apply(pd.to_numeric)
        verifier((nb["nb_probable"] + nb["nb_possible"] <= nb["nb_produits_analyses"]).all(), "appels : plus de produits touchés que de produits analysés")
        for (evt, groupe), g in appels.groupby(["evenement_id", "groupe_appel"]):
            rangs = sorted(pd.to_numeric(g["rang"]))
            verifier(rangs == list(range(1, len(g) + 1)), f"appels : rangs incorrects pour {evt} / {groupe}")
        touches = impact[impact["niveau"] == "probable"].merge(marques, on="marque")
        attendu = touches.groupby(["evenement_id", "compte_id"]).size()
        obtenu = appels.set_index(["evenement_id", "compte_id"])["nb_probable"].astype(int)
        verifier(attendu.to_dict() == obtenu[obtenu > 0].to_dict(), "appels : le nombre de « probable » ne correspond pas à la détection")
        textes = " ".join(appels["fait"] + " " + appels["question"] + " " + appels["raison_classement"])
        verifier(not INTERDITS.search(textes), "appels : un texte contient « non conforme », « illégal » ou « interdit »")
        verifier((appels["fait"] != "").all() and (appels["question"] != "").all(), "appels : fait ou question vide")
        verifier(set(appels["groupe_appel"]) <= {"clients", "prospects"}, "appels : groupe inconnu")
    verifier(len(evenements) == 0 or len(appels) > 0, "des événements sont calculés mais la liste d'appels est vide")
    return erreurs


def main():
    erreurs = controler()
    for e in erreurs:
        print("ERREUR :", e)
    print("Contrôles : OK" if not erreurs else f"Contrôles : {len(erreurs)} erreur(s)")
    return not erreurs


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
