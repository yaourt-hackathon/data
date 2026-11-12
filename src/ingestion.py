"""INGESTION : charge les fichiers reçus (scrap, exports) à partir d'une règle écrite dans regles/<source>.json.

    python src/ingestion.py sites_marques     une source
    python src/ingestion.py                   toutes les règles du dossier regles/

La source n'est jamais modifiée. Bronze = tous les fichiers de la source, tels quels, avec leur nom.
Pour le domaine « produits », le silver suit les mêmes contrôles que la collecte publique.
"""
import hashlib
import json
import sys

import pandas as pd

from commun import AUJOURDHUI, RACINE, REGLES, SILVER, ecrire, slug
from nettoyage import SEPARATEURS, type_rincage

CLES = ["source", "domaine", "fichiers", "table_bronze", "colonnes_obligatoires"]


def charger(regle):
    fichiers = sorted(RACINE.glob(regle["fichiers"]))
    lots = []
    for f in fichiers:
        lot = pd.read_csv(f, dtype=str, keep_default_na=False, sep=regle.get("separateur", ","),
                          encoding=regle.get("encodage", "utf-8"))
        manque = [c for c in regle["colonnes_obligatoires"] if c not in lot.columns]
        if manque:
            raise SystemExit(f"ERREUR {f.name} : colonnes obligatoires absentes {manque}. Fichier non chargé.")
        lots.append(lot.assign(fichier_source=f.name, date_chargement=AUJOURDHUI))
        print(f"  {f.name} : {len(lot)} lignes")
    return pd.concat(lots, ignore_index=True) if lots else None


def silver_produits(bronze, regle):
    """Même forme et mêmes rejets que slv_msd_produits (voir nettoyage.py)."""
    m = regle["mapping_silver"]
    col = lambda nom: bronze[m[nom]].str.strip() if m.get(nom) in bronze.columns else pd.Series("", index=bronze.index)
    df = pd.DataFrame({"code": col("code"), "marque": col("marque").apply(slug), "nom": col("nom"),
                       "ingredients": col("ingredients"), "langue_ingredients": "inconnue"})
    url = col("url")
    sans_code = df["code"] == ""
    df.loc[sans_code, "code"] = ["URL-" + hashlib.md5((u or n).encode()).hexdigest()[:12]
                                 for u, n in zip(url[sans_code], df["nom"][sans_code])]
    df["nb_ingredients"] = df["ingredients"].apply(lambda t: len([x for x in SEPARATEURS.split(t) if x.strip()]))
    df["type_rincage"] = (df["nom"] + " " + col("categories")).apply(type_rincage)
    df["date_fiche"] = pd.to_datetime(col("date_fiche"), errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    df["date_extraction"] = bronze["date_chargement"]
    df["source"] = "Site de la marque (" + bronze["fichier_source"] + ")"
    df["url"] = url

    motif = pd.Series("", index=df.index)
    motif[df["nb_ingredients"] < 4] = "moins_de_4_ingredients"
    motif[df["ingredients"].str.len() < 40] = "texte_trop_court"
    motif[df["ingredients"] == ""] = "sans_ingredients"
    motif[df["marque"] == ""] = "sans_marque"
    motif[df.duplicated(subset="code", keep="last")] = "doublon_version_plus_recente_gardee"
    nom = f"slv_msd_produits_{slug(regle['source']).replace('-', '_')}"
    ecrire(df[motif == ""], SILVER / f"produits/{nom}.csv")
    ecrire(df[motif != ""][["code", "marque", "nom"]].assign(motif=motif[motif != ""]), SILVER / f"produits/{nom}_rejets.csv")
    print(f"  silver : {int((motif == '').sum())} retenus, {int((motif != '').sum())} rejetés")
    if (motif != "").any():
        print(motif[motif != ""].value_counts().to_string())


def ingerer(nom):
    chemin = REGLES / f"{nom}.json"
    if not chemin.exists():
        raise SystemExit(f"ERREUR : pas de règle {chemin.relative_to(RACINE)}")
    regle = json.loads(chemin.read_text(encoding="utf-8"))
    manque = [c for c in CLES if c not in regle]
    if manque:
        raise SystemExit(f"ERREUR {chemin.name} : clés manquantes {manque}")
    print(f"Ingestion « {nom} »")
    bronze = charger(regle)
    if bronze is None:
        print("  aucun fichier pour l'instant : rien à faire")
        return
    ecrire(bronze, RACINE / regle["table_bronze"])
    print(f"  bronze : {len(bronze)} lignes -> {regle['table_bronze']}")
    if regle["domaine"] == "produits" and "mapping_silver" in regle:
        silver_produits(bronze, regle)
    else:
        print("  domaine sans silver automatique pour l'instant : le bronze est prêt")


def main(noms=None):
    noms = noms or [f.stem for f in sorted(REGLES.glob("*.json"))]
    if not noms:
        print("Ingestion : aucune règle dans regles/")
    for nom in noms:
        ingerer(nom)


if __name__ == "__main__":
    main(sys.argv[1:])
