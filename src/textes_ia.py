"""TEXTES DU LLM LOCAL : reformule le fait, la question et les arguments de chaque ligne d'appel.

Le LLM n'invente rien : il reçoit des faits déjà calculés et les met en phrases.
Chaque texte est contrôlé avant d'être gardé, puis relu par une personne avant d'être affiché.

    python src/textes_ia.py                      génère ce qui manque, avec le modèle par défaut
    python src/textes_ia.py --modele qwen2.5:7b  avec un autre modèle
    python src/textes_ia.py --limite 2           seulement les 2 premières lignes (pour essayer)
    python src/textes_ia.py --rejouer            refait aussi les textes déjà générés mais pas encore relus

Les arguments ne sont pas générés par défaut (--arguments pour les demander) : le modèle y glisse des promesses
que la donnée ne porte pas. Le gabarit du code reste affiché à leur place.

Jamais lancé par pipeline.py : le LLM tourne en local, par lot, quand on le décide.
Un texte déjà marqué « valide » ou « rejete » par une personne n'est jamais réécrit.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request

import pandas as pd

from commun import AUJOURDHUI, GOLD, MART, SILVER, ecrire, lire, normaliser

SORTIE = GOLD / "gld_fct_textes_ia.csv"
COLONNES = ["evenement_id", "compte_id", "type_texte", "texte", "origine", "modele",
            "date_generation", "statut_validation", "relu_par"]
TYPES = ["fait", "question", "arguments"]
PAR_DEFAUT = ["fait", "question"]   # les arguments sont une promesse commerciale : au commercial de les écrire
FIGES = ["valide", "rejete"]          # décidés par une personne : on n'y touche plus

OLLAMA = "http://127.0.0.1:11434/api/generate"
MODELE_DEFAUT = "llama3.2:3b"
TEMPERATURE = 0.1                     # on veut la même phrase à chaque fois, pas de la créativité
LONGUEUR_MAX = 400
# Vocabulaire que le modèle ne doit jamais employer : aucune de ces notions n'est dans les faits.
INTERDITS = re.compile(r"non[ -]conform|ill[ée]gal|interdit|sanction|amende|rappel produit|retrait du march", re.I)
OBLIGATIONS = re.compile(r"\b(doit|doive|devez|devra|obligatoire|obligation|exigence|impose|recommand|conseill|nous vous aid)", re.I)
DUREES = re.compile(r"\b\d+\s*(an|ans|mois|semaine|semaines|jour|jours)\b", re.I)
NOMBRES = re.compile(r"\d+(?:[.,]\d+)?")

CONSIGNE = """Tu aides un commercial à préparer un appel. Tu reformules des faits déjà établis.

Règles :
- N'emploie que les chiffres et les ingrédients de la liste de faits. N'en invente aucun.
- Le « fait » doit citer le nombre de produits en exposition probable et le nombre de produits analysés.
- N'écris jamais qu'une entreprise doit faire quelque chose, et n'invente aucun délai.
- Écris « exposition probable », jamais « non conforme », « illégal » ni « interdit ».
- Réponds en français, en JSON, sans rien autour.

Exemple. Faits :
- Compte : Dupont (client, relation fictive pour la démonstration)
- Événement : Nouveaux allergènes de parfum à étiqueter
- Source : texte officiel (exemple)
- Produits analysés : 4. En exposition probable : 3. En exposition possible : 1.
- Ingrédients visés repérés sur les étiquettes : citronnellol, géraniol
- Question à poser au client : Compléter l'étiquette ou revoir le parfum ?

Réponse :
{{"fait": "3 de vos 4 produits analysés listent un ingrédient visé : citronnellol, géraniol. 1 autre est en exposition possible.", "question": "Pour ces produits, préférez-vous compléter l'étiquette ou revoir le parfum ?", "arguments": ["Nous avons déjà la liste des produits concernés et des ingrédients repérés", "Nous pouvons regarder ensemble produit par produit"]}}

À toi. Faits :
{faits}

Réponse :"""


def faits(appel, produits, evenement):
    """Le bloc de faits envoyé au modèle. Rien d'autre ne doit entrer dans le texte."""
    elements = sorted({e for cellule in produits["elements_directs"] for e in cellule.split("|") if e})
    lignes = [
        f"- Compte : {appel['nom_compte']} ({appel['statut']}, relation fictive pour la démonstration)",
        f"- Événement : {evenement['titre']}",
        f"- Source : {evenement['source_nom']}",
        f"- Produits analysés : {appel['nb_produits_analyses']}. "
        f"En exposition probable : {appel['nb_probable']}. En exposition possible : {appel['nb_possible']}.",
        f"- Ingrédients visés repérés sur les étiquettes : {', '.join(elements) if elements else 'aucun'}",
        f"- Question à poser au client : {evenement['question_type']}",
    ]
    if evenement["date_echeance"]:
        lignes.append(f"- Échéance : {evenement['date_echeance']}")
    return "\n".join(lignes)


def nombres_autorises(bloc):
    """Tous les nombres lisibles dans les faits, plus le pourcentage qu'on accepte de voir calculé."""
    autorises = set(NOMBRES.findall(bloc.replace(" ", "")))
    nb = re.search(r"Produits analysés : (\d+)\. En exposition probable : (\d+)", bloc)
    if nb:
        n, p = int(nb.group(1)), int(nb.group(2))
        if n:
            autorises |= {str(round(100 * p / n)), str(round(100 * p / n, 1)).replace(".", ",")}
    return autorises


def vocabulaire_hors_faits(bloc, tous_ingredients):
    """Les ingrédients connus du référentiel qui ne sont PAS sur les étiquettes de ce compte."""
    cites = normaliser(bloc)
    return sorted({i for i in tous_ingredients if i and i not in cites}, key=len, reverse=True)


def controler(texte, autorises, type_texte="fait", obligatoires=(), hors_faits=()):
    """Rend le motif de rejet, ou une chaîne vide si le texte est gardé."""
    if not texte or len(texte) > LONGUEUR_MAX:
        return "texte vide ou trop long"
    if INTERDITS.search(texte):
        return "vocabulaire interdit"
    if OBLIGATIONS.search(texte):
        return "invente une obligation"
    if DUREES.search(texte):
        return "invente un délai"
    inventes = sorted(set(NOMBRES.findall(texte.replace("\u202f", " "))) - set(autorises))
    if inventes:
        return f"chiffre absent des faits : {', '.join(inventes)}"
    propre = normaliser(texte)
    ajoutes = [i for i in hors_faits if re.search(r"(?<![a-z])" + re.escape(i) + r"(?![a-z])", propre)]
    if ajoutes:
        return f"ingrédient absent des étiquettes de ce compte : {ajoutes[0]}"
    if type_texte == "fait":
        manquants = [n for n in obligatoires if n not in NOMBRES.findall(texte)]
        if manquants:
            return f"le fait ne cite pas les nombres de la détection : {', '.join(manquants)}"
    return ""


def interroger(consigne, modele):
    """Un appel au LLM local. Aucune donnée ne sort de la machine."""
    corps = json.dumps({"model": modele, "prompt": consigne, "stream": False, "format": "json",
                        "options": {"temperature": TEMPERATURE, "seed": 7, "num_predict": 400}}).encode()
    requete = urllib.request.Request(OLLAMA, data=corps, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(requete, timeout=180) as reponse:
            brut = json.loads(reponse.read())["response"]
    except urllib.error.URLError as erreur:
        raise SystemExit(f"ERREUR : Ollama ne répond pas sur {OLLAMA} ({erreur}).\n"
                         f"Ouvrir l'application Ollama, puis : ollama pull {modele}")
    try:
        return json.loads(brut)
    except json.JSONDecodeError:
        return {}


def reponse_en_textes(reponse):
    """La réponse du modèle -> un texte par type, en texte simple."""
    textes = {}
    for t in TYPES:
        valeur = reponse.get(t, "")
        if isinstance(valeur, list):
            valeur = " ".join(str(v).strip().rstrip(".") + "." for v in valeur if str(v).strip())
        textes[t] = re.sub(r"\s+", " ", str(valeur)).strip()
    return textes


def existant():
    if not SORTIE.exists():
        return pd.DataFrame(columns=COLONNES)
    return lire(SORTIE)[COLONNES]


def main(argv=None):
    options = argparse.ArgumentParser(description="Textes du LLM local pour la liste d'appels")
    options.add_argument("--modele", default=MODELE_DEFAUT)
    options.add_argument("--limite", type=int, default=0, help="n'traiter que les N premières lignes d'appel")
    options.add_argument("--rejouer", action="store_true", help="refaire aussi les textes « a_relire »")
    options.add_argument("--arguments", action="store_true",
                         help="générer aussi les arguments (par défaut non : le modèle y invente des promesses)")
    args = options.parse_args(argv)

    appels = lire(MART / "mrt_liste_appels.csv")
    impact = lire(GOLD / "gld_fct_impact_produit.csv")
    evenements = lire(GOLD / "gld_dim_evenements.csv").set_index("evenement_id")
    marques = lire(GOLD / "gld_dim_comptes.csv").set_index("compte_id")["marques"].str.split("|")
    regles = lire(SILVER / "evenements/slv_ref_regles_detection.csv")
    tous_ingredients = sorted({normaliser(n) for n in regles["nom_usuel"]})
    if args.limite:
        appels = appels.head(args.limite)

    deja = existant()
    figees = {(r.evenement_id, r.compte_id) for r in deja.itertuples() if r.statut_validation in FIGES}
    a_relire = {(r.evenement_id, r.compte_id) for r in deja.itertuples() if r.statut_validation == "a_relire"}
    garder = deja[deja["statut_validation"].isin(FIGES)] if args.rejouer else deja

    lignes, rejets = [], []
    for appel in appels.to_dict("records"):
        cle = (appel["evenement_id"], appel["compte_id"])
        if cle in figees or (cle in a_relire and not args.rejouer):
            continue
        produits = impact[(impact["evenement_id"] == cle[0]) & impact["marque"].isin(marques.get(cle[1], []))
                          & (impact["niveau"] == "probable")]
        bloc = faits(appel, produits, evenements.loc[cle[0]])
        autorises = nombres_autorises(bloc)
        hors_faits = vocabulaire_hors_faits(bloc, tous_ingredients)
        obligatoires = [str(appel["nb_probable"]), str(appel["nb_produits_analyses"])]
        textes = reponse_en_textes(interroger(CONSIGNE.format(faits=bloc), args.modele))
        for type_texte in (TYPES if args.arguments else PAR_DEFAUT):
            motif = controler(textes[type_texte], autorises, type_texte, obligatoires, hors_faits)
            if motif:
                rejets.append(f"{cle[0]} {cle[1]} {type_texte} : {motif}")
                continue
            lignes.append({"evenement_id": cle[0], "compte_id": cle[1], "type_texte": type_texte,
                           "texte": textes[type_texte], "origine": "llm", "modele": args.modele,
                           "date_generation": AUJOURDHUI, "statut_validation": "a_relire", "relu_par": ""})
        print(f"{cle[0]} {cle[1]} {appel['nom_compte']} : {len([l for l in lignes if (l['evenement_id'], l['compte_id']) == cle])}/{len(TYPES if args.arguments else PAR_DEFAUT)} textes gardés")

    sortie = pd.concat([garder, pd.DataFrame(lignes, columns=COLONNES)], ignore_index=True)
    sortie = sortie.drop_duplicates(subset=["evenement_id", "compte_id", "type_texte"], keep="last")
    ecrire(sortie[COLONNES], SORTIE)

    print(f"\n{len(lignes)} textes générés, {len(rejets)} refusés par les contrôles, "
          f"{len(sortie[sortie['statut_validation'] == 'valide'])} déjà validés par une personne")
    for r in rejets:
        print("  refusé :", r)
    print(f"\nÀ relire : ouvrir {SORTIE.relative_to(SORTIE.parents[2])}, "
          f"mettre « valide » ou « rejete » dans statut_validation et ses initiales dans relu_par.")
    print("L'API n'affiche que les textes « valide » ; pour les autres elle garde le gabarit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
