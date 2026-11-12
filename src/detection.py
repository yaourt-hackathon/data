"""GOLD : impact de chaque événement sur chaque produit. Des règles lisibles, pas de LLM.

Une ligne = un produit x un événement. Niveaux :
  probable     au moins un élément « direct » de la règle est lu sur l'étiquette
  possible     aucun direct, mais un « indice » (et, si l'événement le prévoit, un parfum non détaillé)
  indetermine  un parfum non détaillé, rien d'autre (seulement si parfum_masque = oui)
  non_detecte  rien
"""
import re

import pandas as pd

from commun import AUJOURDHUI, GOLD, MART, SILVER, ecrire, lire, normaliser, slug

PRODUITS = SILVER / "produits"
NIVEAUX = ["probable", "possible", "indetermine", "non_detecte"]
PARFUM = re.compile(r"(?<![a-z])(parfum|fragrance)(?![a-z])")
COLONNES = ["evenement_id", "code", "marque", "nom", "type_rincage", "niveau", "elements_directs", "nb_directs",
            "elements_indices", "nb_indices", "contient_parfum", "motif", "date_fiche", "confiance", "source"]


def garder_la_plus_recente(produits):
    """Un même code-barres vu plusieurs fois : on garde la capture la plus récente.

    Une source rafraîchie dans le temps (trois mois de scraping) contient le même produit
    à plusieurs dates. Sans ça, on afficherait une étiquette périmée alors qu'on en a une à jour.
    """
    ordre = produits.assign(
        _extraction=pd.to_datetime(produits.get("date_extraction", ""), errors="coerce"),
        _fiche=pd.to_datetime(produits.get("date_fiche", ""), errors="coerce"),
    ).sort_values(["_extraction", "_fiche"], ascending=False, na_position="last", kind="stable")
    return produits.loc[ordre.drop_duplicates(subset="code", keep="first").index]


def cle_produit(ligne):
    """Clé de rapprochement ENTRE SOURCES : la marque et le nom, sans accent ni ponctuation.

    Toutes les sources n'ont pas de code-barres (Cosmébio n'en publie pas). Sans ça, le même
    produit vu par deux sources compterait deux fois et fausserait le classement des comptes.
    """
    return slug(ligne["marque"]) + "::" + slug(ligne["nom"])


def lire_produits(bavard=False):
    """Tous les silver produits (collecte publique + fichiers de sites), sans les rejets ni les doublons.

    Deux niveaux de dédoublonnage, et un seul s'applique à l'intérieur d'une source :
      - même code : toujours un doublon, on garde la première ligne ;
      - même marque et même nom, mais SOURCES DIFFÉRENTES : c'est le même produit vu deux fois,
        on garde la ligne qui a un vrai code-barres.
    Dans une même source, deux codes-barres pour un même nom sont deux références réelles
    (deux contenances, deux emballages) : on les garde toutes les deux.
    """
    fichiers = [f for f in sorted(PRODUITS.glob("slv_msd_produits*.csv")) if not f.stem.endswith("_rejets")]
    produits = pd.concat([lire(f) for f in fichiers], ignore_index=True)
    avant = len(produits)
    produits = garder_la_plus_recente(produits)

    produits["_cle"] = produits.apply(cle_produit, axis=1)
    produits["_sans_ean"] = produits["code"].str.startswith("URL-")
    nb_sources = produits.groupby("_cle")["source"].transform("nunique")
    entre_sources = (nb_sources > 1) & (produits["_cle"] != "::")
    gardes = (produits[entre_sources].sort_values("_sans_ean", kind="stable")
              .drop_duplicates(subset="_cle", keep="first"))
    produits = pd.concat([produits[~entre_sources], gardes])
    retires = avant - len(produits)
    if retires and bavard:
        print(f"  {retires} doublons retirés : même code, ou même produit vu par deux sources")
    return produits.drop(columns=["_cle", "_sans_ean"]).sort_values("code").reset_index(drop=True)


def compiler(regles):
    """Une substance se cherche comme un mot entier ; un extrait naturel a son propre motif."""
    compilees = []
    for r in regles.itertuples():
        motif = r.motif_recherche
        if r.type == "substance":
            motif = r"(?<![a-z])" + re.escape(motif) + r"(?![a-z])"
        compilees.append((r.nom_usuel, r.role, re.compile(motif)))
    return compilees


def chercher(texte, compilees, role):
    return [nom for nom, r, motif in compilees if r == role and motif.search(texte)]


def niveau(directs, indices, parfum, parfum_masque):
    if directs:
        return "probable", "ingrédient visé lu sur l'étiquette"
    if parfum_masque:
        if parfum and indices:
            return "possible", "parfum non détaillé et ingrédients proches : composition du parfum inconnue"
        if parfum:
            return "indetermine", "parfum non détaillé"
    elif indices:
        return "possible", "ingrédient proche lu sur l'étiquette"
    return "non_detecte", "aucun ingrédient visé détecté"


def confiance(date_fiche):
    """Une fiche ancienne peut décrire une formule qui a changé."""
    age = (pd.Timestamp(AUJOURDHUI) - pd.to_datetime(date_fiche, errors="coerce")).days
    if pd.isna(age):
        return "faible"
    return "bonne" if age < 730 else "moyenne" if age < 1825 else "faible"


def detecter(produits, evenements, regles):
    lignes = []
    textes = produits["ingredients"].apply(normaliser)
    for evt in evenements.itertuples():
        compilees = compiler(regles[regles["evenement_id"] == evt.evenement_id])
        masque = evt.parfum_masque == "oui"
        for p, texte in zip(produits.itertuples(), textes):
            directs, indices = chercher(texte, compilees, "direct"), chercher(texte, compilees, "indice")
            parfum = bool(PARFUM.search(texte))
            niv, motif = niveau(directs, indices, parfum, masque)
            lignes.append({"evenement_id": evt.evenement_id, "code": p.code, "marque": p.marque, "nom": p.nom,
                           "type_rincage": p.type_rincage, "niveau": niv,
                           "elements_directs": "|".join(directs), "nb_directs": len(directs),
                           "elements_indices": "|".join(indices), "nb_indices": len(indices),
                           "contient_parfum": parfum, "motif": motif, "date_fiche": p.date_fiche,
                           "confiance": confiance(p.date_fiche), "source": p.source})
    return pd.DataFrame(lignes, columns=COLONNES)


def anciens_fichiers(impact):
    """Les deux fichiers lus par /marques et /exposition (API v0.3) : même forme qu'avant, tirés de EVT-001."""
    g = impact[impact["evenement_id"] == "EVT-001"]
    if g.empty:
        return
    gold = g.rename(columns={"elements_directs": "nouvelles_substances", "nb_directs": "nb_nouvelles",
                             "elements_indices": "anciennes_substances", "nb_indices": "nb_anciennes"})
    gold = gold[["code", "marque", "nom", "type_rincage", "niveau", "nouvelles_substances", "nb_nouvelles",
                 "anciennes_substances", "nb_anciennes", "contient_parfum", "motif", "date_fiche", "source"]]
    mart = gold.pivot_table(index="marque", columns="niveau", values="code", aggfunc="count", fill_value=0)
    for n in NIVEAUX:
        if n not in mart.columns:
            mart[n] = 0
    mart = mart[NIVEAUX].add_prefix("nb_").reset_index()
    mart.insert(1, "nb_produits", mart[["nb_" + n for n in NIVEAUX]].sum(axis=1))
    mart["part_probable"] = (mart["nb_probable"] / mart["nb_produits"]).round(2)
    mart["urgence"] = pd.cut(mart["part_probable"], [-0.01, 0, 0.25, 1], labels=["faible", "moyenne", "haute"])
    mart["date_calcul"] = AUJOURDHUI
    ecrire(gold, GOLD / "gld_fct_exposition_produit.csv")
    ecrire(mart.sort_values(["nb_probable", "marque"], ascending=[False, True]),
           MART / "mrt_notedetete_fct_exposition_marque.csv")


def main():
    produits = lire_produits(bavard=True)
    evenements = lire(GOLD / "gld_dim_evenements.csv")
    regles = lire(SILVER / "evenements/slv_ref_regles_detection.csv")
    impact = detecter(produits, evenements, regles)
    ecrire(impact, GOLD / "gld_fct_impact_produit.csv")
    anciens_fichiers(impact)

    print(f"Détection : {len(produits)} produits x {len(evenements)} événements = {len(impact)} lignes")
    if len(impact):
        resume = impact.pivot_table(index="evenement_id", columns="niveau", values="code", aggfunc="count", fill_value=0)
        print(resume.reindex(columns=NIVEAUX, fill_value=0).to_string())


if __name__ == "__main__":
    main()
