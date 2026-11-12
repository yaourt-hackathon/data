"""PIPELINE : recalcule toute la chaîne en une commande.

    python pipeline.py              recalcule à partir des sources et du dernier bronze
    python pipeline.py --collecte   refait d'abord la collecte publique (environ 2 minutes, besoin d'internet)

Ordre : (collecte) -> ingestion -> nettoyage -> événements -> détection -> comptes -> appels -> contrôles.
Si une étape ou un contrôle échoue, le script s'arrête avec un code d'erreur : rien ne doit être publié.
"""
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
os.chdir(RACINE)
sys.path.insert(0, str(RACINE / "src"))

import appels, comptes, controles, detection, evenements, ingestion, nettoyage  # noqa: E402
from commun import BRONZE, lire  # noqa: E402


def collecter():
    """Lance la collecte, puis ne garde le nouveau bronze que s'il diffère du précédent."""
    import collecte
    avant = sorted((BRONZE / "produits").glob("brz_msd_produits_obf_*.csv"))
    collecte.main()
    apres = sorted((BRONZE / "produits").glob("brz_msd_produits_obf_*.csv"))
    if not avant or len(apres) == len(avant):
        return
    ancien, nouveau = lire(avant[-1]), lire(apres[-1])
    cle = lambda d: d.drop(columns=["date_extraction"], errors="ignore").sort_values("code").reset_index(drop=True)
    if cle(ancien).equals(cle(nouveau)):
        apres[-1].unlink()
        print(f"Collecte identique à {avant[-1].name} : nouveau fichier non gardé")
    else:
        print(f"Collecte : {len(ancien)} lignes avant, {len(nouveau)} maintenant "
              f"({len(set(nouveau['code']) - set(ancien['code']))} nouveaux codes)")


def main():
    etapes = [("Ingestion", ingestion.main), ("Nettoyage", nettoyage.main), ("Événements", evenements.main),
              ("Détection", detection.main), ("Comptes", comptes.main), ("Appels", appels.main)]
    if "--collecte" in sys.argv:
        etapes.insert(0, ("Collecte", collecter))
    for nom, etape in etapes:
        print(f"\n=== {nom} ===")
        etape()
    print("\n=== Contrôles ===")
    if not controles.main():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
