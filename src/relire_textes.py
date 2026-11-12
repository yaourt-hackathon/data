"""RELECTURE des textes du LLM : un texte à l'écran, une touche, on passe au suivant.

    python src/relire_textes.py            relire ce qui est « a_relire »
    python src/relire_textes.py --tout     revoir aussi ce qui est déjà décidé

Touches : o = valide, n = rejete, Entrée = laisser pour plus tard, q = enregistrer et sortir.
Rien n'est enregistré tant qu'on n'a pas quitté avec « q » ou fini la liste.
C'est la seule étape où une personne décide : l'API n'affiche que les textes « valide ».
"""
import argparse
import sys

from commun import GOLD, ecrire, lire
from textes_ia import COLONNES, SORTIE

ATTENDU = {"fait": "Dit un fait vrai, avec les bons nombres, sans promesse ni obligation.",
           "question": "Une question ouverte, que le commercial peut poser telle quelle.",
           "arguments": "Des arguments que la donnée porte vraiment."}


def contexte(cle, appels):
    ligne = appels[(appels["evenement_id"] == cle[0]) & (appels["compte_id"] == cle[1])]
    if ligne.empty:
        return ""
    a = ligne.iloc[0]
    return (f"{a['nom_compte']} ({a['statut']}) · {a['nb_probable']} produits sur {a['nb_produits_analyses']} "
            f"en exposition probable, {a['nb_possible']} en possible")


def main(argv=None):
    options = argparse.ArgumentParser(description="Relire les textes du LLM")
    options.add_argument("--tout", action="store_true", help="revoir aussi les textes déjà validés ou rejetés")
    args = options.parse_args(argv)

    if not SORTIE.exists():
        raise SystemExit(f"Rien à relire : {SORTIE.name} n'existe pas. Lancer d'abord python src/textes_ia.py")
    textes = lire(SORTIE)
    appels = lire(GOLD.parent / "04_mart/mrt_liste_appels.csv")
    a_voir = textes.index if args.tout else textes.index[textes["statut_validation"] == "a_relire"]
    if not len(a_voir):
        print("Tout est déjà relu. --tout pour revoir quand même.")
        return 0

    initiales = input("Tes initiales : ").strip() or "?"
    print(f"\n{len(a_voir)} textes à relire. o = valide, n = rejete, Entrée = plus tard, q = quitter.\n")
    decides = 0
    for numero, i in enumerate(a_voir, start=1):
        r = textes.loc[i]
        print("─" * 78)
        print(f"{numero}/{len(a_voir)}  {r['evenement_id']} · {contexte((r['evenement_id'], r['compte_id']), appels)}")
        print(f"type : {r['type_texte']} — {ATTENDU.get(r['type_texte'], '')}")
        if r["statut_validation"] != "a_relire":
            print(f"déjà : {r['statut_validation']} par {r['relu_par']}")
        print(f"\n  {r['texte']}\n")
        reponse = input("o / n / Entrée / q > ").strip().lower()
        if reponse == "q":
            break
        if reponse in ("o", "n"):
            textes.loc[i, "statut_validation"] = "valide" if reponse == "o" else "rejete"
            textes.loc[i, "relu_par"] = initiales
            decides += 1

    ecrire(textes[COLONNES], SORTIE)
    valides = int((textes["statut_validation"] == "valide").sum())
    restants = int((textes["statut_validation"] == "a_relire").sum())
    print(f"\n{decides} décidés maintenant. En tout : {valides} valides, "
          f"{int((textes['statut_validation'] == 'rejete').sum())} rejetés, {restants} encore à relire.")
    print("L'API affiche les textes « valide » et garde le gabarit pour les autres.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(SORTIE.parents[2] / "src"))
    sys.exit(main())
