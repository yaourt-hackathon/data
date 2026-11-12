"""Outils partagés par les scripts du pipeline : chemins, lecture, écriture, normalisation."""
import re
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
SOURCES = RACINE / "data/00_sources"
BRONZE = RACINE / "data/01_bronze"
SILVER = RACINE / "data/02_silver"
GOLD = RACINE / "data/03_gold"
MART = RACINE / "data/04_mart"
REGLES = RACINE / "regles"

AUJOURDHUI = str(date.today())


def lire(chemin):
    """Lit un CSV en texte, sans valeur manquante : une case vide reste une chaîne vide."""
    return pd.read_csv(chemin, dtype=str, keep_default_na=False, encoding="utf-8")


def ecrire(df, chemin):
    """Écrit un CSV en UTF-8, fins de ligne Unix, et crée le dossier si besoin."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(chemin, index=False, encoding="utf-8", lineterminator="\n")
    return chemin


def normaliser(texte):
    """Texte d'étiquette -> minuscules sans accent, séparateurs ramenés à la virgule."""
    t = re.sub(r"\s[-–•·]\s|\n|;", ", ", str(texte))  # avant de retirer les accents : « – » et « • » ne sont pas de l'ASCII
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    t = t.replace("*", "")
    return re.sub(r"\s+", " ", t).strip()


def slug(texte):
    """« So'Bio étic » -> « so-bio-etic » : l'identifiant d'une marque."""
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def date_valide(texte, vide_accepte=True):
    if texte == "":
        return vide_accepte
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", texte)) and not pd.isna(pd.to_datetime(texte, errors="coerce"))


def pluriel(n, singulier, pluriel_=None):
    return f"{n} {singulier if n < 2 else (pluriel_ or singulier + 's')}"
