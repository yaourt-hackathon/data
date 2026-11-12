# data · équipe 7 Yaourt

D'un événement (une règle qui change, un prix qui monte) à une liste d'appels de clients et de prospects,
avec pour chacun un fait sourcé et une question à poser.

Le code croise et classe. Le LLM local rédige. Le commercial valide.
On écrit « exposition probable », jamais « non conforme ».

## Lancer

```bash
python -m venv .venv
source .venv/bin/activate            # Windows : .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt

python pipeline.py                   # recalcule tout, finit par « Contrôles : OK »
python pipeline.py --collecte        # refait d'abord la collecte publique (2 minutes, internet)
python -m pytest -q                  # les tests
uvicorn src.api:app --reload         # l'API, documentation sur http://127.0.0.1:8000/docs
```

L'API en conteneur, comme la lance le `compose.yaml` de l'application :

```bash
docker build -t data-api .
docker run --rm -p 8000:8000 data-api   # lit data/03_gold et data/04_mart tels que versionnés
```

## La chaîne

```
data/00_sources   ce qu'on reçoit ou qu'on écrit à la main. Jamais modifié par le code.
data/01_bronze    la copie brute, datée
data/02_silver    nettoyé et contrôlé. Ce qui est écarté part dans un fichier _rejets, avec la raison.
data/03_gold      ce que les règles calculent
data/04_mart      ce que l'API lit
```

| Étape | Script | Lit | Écrit |
|---|---|---|---|
| Collecte publique | `src/collecte.py` | Open Beauty Facts | `01_bronze/produits/brz_msd_produits_obf_AAAAMMJJ.csv` |
| Ingestion des fichiers reçus | `src/ingestion.py` + `regles/*.json` | `00_sources/<source>/` | bronze, et silver pour les produits |
| Nettoyage | `src/nettoyage.py` | dernier bronze produits | `02_silver/produits/slv_msd_produits.csv` et rejets |
| Événements et règles | `src/evenements.py` | `00_sources/evenements/`, `00_sources/regles_detection/` | `03_gold/gld_dim_evenements.csv` |
| Détection | `src/detection.py` | produits x règles | `03_gold/gld_fct_impact_produit.csv` |
| Comptes et ventes (fictifs) | `src/comptes.py` | `00_sources/crm/`, `00_sources/sap/` | `03_gold/gld_dim_comptes.csv` |
| Liste d'appels | `src/appels.py` | impact x comptes | `04_mart/mrt_liste_appels.csv`, `04_mart/mrt_fiche_compte.csv` |
| Contrôles | `src/controles.py` | tout | arrête le pipeline à la première erreur |

`pipeline.py` enchaîne tout dans cet ordre.

## Ce qu'on modifie à la main

| Pour | Fichier |
|---|---|
| ajouter un événement | `data/00_sources/evenements/evenements.csv` (statut `a_valider`, puis `valide` ou `test`) |
| écrire sa règle | `data/00_sources/regles_detection/EVT-00N.csv` (`role` : `direct` ou `indice`) |
| ajouter un compte ou une marque | `data/00_sources/crm/` |
| brancher une nouvelle source de scrap | `regles/<source>.json` |

Un événement n'est calculé que s'il est marqué `valide` (ou `test` pour un essai).
`EVT-002` est un événement d'essai inventé par l'équipe : il sert à vérifier que la chaîne accepte plusieurs événements.

## Données fictives

Les comptes, leur statut client ou prospect, les commerciaux (`KAM-01`…) et les ventes sont inventés
pour la démonstration et marqués `fictif`. Ils ne disent rien de la relation réelle entre ces marques et Givaudan.
Aucun nom de personne, nulle part.

## Documentation

`docs/contrat_api_v0.4.md` : les routes, les champs et ce qu'ils veulent dire côté application.
`docs/benchmark_llm.pdf` : la comparaison des modèles locaux (la version qui fait foi est à la racine du fork `example-rag`).

## API (v0.4.0)

`/health`, `/marques`, `/exposition?marque=` (inchangées), `/evenements`, `/evenements/{evenement_id}/appels`,
`/comptes/{compte_id}`. On ajoute, on ne renomme ni ne retire rien : l'application génère son client à partir de `/openapi.json`.

L'API affiche les textes du LLM marqués `valide` dans `data/03_gold/gld_fct_textes_ia.csv`,
et garde le gabarit écrit par le code pour les autres (champ `origine_textes`).

## Textes du LLM local

```bash
ollama pull llama3.2:3b                 # une seule fois
python src/textes_ia.py --limite 2      # essayer sur deux comptes
python src/textes_ia.py                 # tout ce qui manque
```

Le LLM reçoit des faits déjà calculés et les met en phrases. Chaque texte passe trois contrôles :
aucun chiffre absent des faits, pas de « non conforme », « illégal » ni « interdit », moins de 400 caractères.
Un texte refusé n'est pas enregistré : le gabarit reste.

Ce script n'est pas dans `pipeline.py` : le LLM tourne en local, par lot, quand on le décide.
Après génération, chaque ligne est à `a_relire`. Une personne met `valide` ou `rejete` et ses initiales
dans `relu_par`. Une ligne déjà décidée n'est jamais réécrite.

## Automatisation

`.github/workflows/pipeline.yml` relance `pipeline.py` et les tests quand une source, une règle ou un script
arrive sur `develop`, et chaque nuit avec une nouvelle collecte. Si tout passe, les données recalculées sont
enregistrées sur `develop`. Sinon rien n'est publié.

## Règles d'équipe

Une tâche, une issue, une branche qui part de `develop`, une demande de fusion. Jamais `git add .`.
Seule Judicha modifie `src/`. Les autres annulent les fichiers recalculés avant d'enregistrer :
`git restore data/01_bronze data/02_silver data/03_gold data/04_mart`.

`src/exposition.py` et `src/ref_allergenes.py` sont les scripts de la première version. `detection.py` et
`regles_detection/EVT-001.csv` les remplacent ; ils restent là le temps de vérifier, puis seront retirés.
