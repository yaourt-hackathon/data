"""Collecte bronze : produits Open Beauty Facts par marque (API v2 publique, licence ODbL)."""
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

URL = "https://world.openbeautyfacts.org/api/v2/search"
MARQUES = ["florame", "cattier", "melvita", "so-bio-etic"]
CHAMPS = ("code,product_name,product_name_fr,brands,brands_tags,ingredients_text,"
          "ingredients_text_fr,countries_tags,categories_tags,last_modified_t")
HEADERS = {"User-Agent": "YaourtHackathon/0.1 (projet etudiant HETIC)"}
PAUSE = 7  # secondes entre deux appels
SORTIE = Path("data/bronze")


def collecter(marque):
    """Toutes les pages de produits d'une marque."""
    produits, page = [], 1
    while True:
        r = requests.get(URL, headers=HEADERS, timeout=30, params={
            "brands_tags": marque, "fields": CHAMPS, "page_size": 100, "page": page})
        r.raise_for_status()
        lot = r.json().get("products", [])
        produits += lot
        if len(lot) < 100:
            return produits
        page += 1
        time.sleep(PAUSE)


def main():
    maintenant = datetime.now()
    lignes = []
    for i, marque in enumerate(MARQUES):
        if i:
            time.sleep(PAUSE)
        produits = collecter(marque)
        print(f"{marque:<15} {len(produits):>4} produits")
        for p in produits:
            p["marque_demandee"] = marque
        lignes += produits

    df = pd.DataFrame(lignes)
    for col in df.columns:  # listes -> texte "a,b,c"
        df[col] = df[col].apply(lambda v: ",".join(v) if isinstance(v, list) else v)
    df["date_extraction"] = maintenant.isoformat(timespec="seconds")
    df["source"] = "Open Beauty Facts API v2 (ODbL)"

    fichier = SORTIE / f"brz_produits_obf_{maintenant:%Y%m%d}.csv"
    df.to_csv(fichier, index=False, encoding="utf-8")
    print(f"\n{len(df)} lignes -> {fichier}")


if __name__ == "__main__":
    main()