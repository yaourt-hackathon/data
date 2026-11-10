"""Silver PRODUITS : lit le dernier bronze OBF, nettoie, sépare retenus / rejets."""
import re
from pathlib import Path

import pandas as pd

BRONZE = Path("data/01_bronze/produits")
SILVER = Path("data/02_silver/produits")

RINCE = re.compile(r"shampo|douche|savon|nettoyant|d[ée]maquill|masque|bain|gommage|rasage|dentifrice|dentargile", re.I)
NON_RINCE = re.compile(r"cr[èe]me|lait|huile|baume|s[ée]rum|eau de (toilette|parfum)|parfum|d[ée]odorant|lotion|soin", re.I)
SEPARATEURS = re.compile(r",|;|\s[-–•·]\s|\n|\.\s")


def type_rincage(texte):
    if RINCE.search(texte):
        return "rince"
    if NON_RINCE.search(texte):
        return "non_rince"
    return "indetermine"


def main():
    fichier = sorted(BRONZE.glob("brz_msd_produits_obf_*.csv"))[-1]
    df = pd.read_csv(fichier, dtype={"code": str})
    print(f"Bronze lu : {fichier.name} ({len(df)} lignes)")

    df = df.drop_duplicates(subset="code")
    fr = df["ingredients_text_fr"].fillna("").str.strip()
    autre = df["ingredients_text"].fillna("").str.strip()
    df["ingredients"] = fr.where(fr != "", autre)
    df["langue_ingredients"] = (fr != "").map({True: "fr", False: "autre"})
    df["nb_ingredients"] = df["ingredients"].apply(lambda t: len([x for x in SEPARATEURS.split(t) if x.strip()]))
    df["nom"] = df["product_name_fr"].fillna(df["product_name"]).fillna("")
    df["vendu_france"] = df["countries_tags"].fillna("").str.contains("en:france")
    df["type_rincage"] = (df["nom"] + " " + df["categories_tags"].fillna("")).apply(type_rincage)
    df["date_fiche"] = pd.to_datetime(df["last_modified_t"], unit="s").dt.date
    df["marque"] = df["marque_demandee"]

    motif = pd.Series("", index=df.index)
    motif[df["nb_ingredients"] < 4] = "moins_de_4_ingredients"
    motif[df["ingredients"].str.len() < 40] = "texte_trop_court"
    motif[df["ingredients"] == ""] = "sans_ingredients"
    motif[~df["vendu_france"]] = "hors_france"

    colonnes = ["code", "marque", "nom", "ingredients", "langue_ingredients", "nb_ingredients",
                "type_rincage", "date_fiche", "date_extraction", "source"]
    retenus = df[motif == ""][colonnes]
    rejets = df[motif != ""][["code", "marque", "nom"]].assign(motif=motif[motif != ""])

    SILVER.mkdir(parents=True, exist_ok=True)
    retenus.to_csv(SILVER / "slv_msd_produits.csv", index=False)
    rejets.to_csv(SILVER / "slv_msd_produits_rejets.csv", index=False)

    print(f"Retenus : {len(retenus)} | Rejets : {len(rejets)}")
    print(rejets["motif"].value_counts().to_string())
    print(retenus.groupby("marque").size().to_string())
    print(retenus["type_rincage"].value_counts().to_string())


if __name__ == "__main__":
    main()