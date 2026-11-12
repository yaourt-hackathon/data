# Contrat d'API — version 0.4.0

Équipe 7 Yaourt · dépôt `data` · étiquette `v0.4.0` sur `develop`.

**Règle de livraison** : on ajoute des routes et des champs, on ne renomme ni ne retire rien.
L'application génère son client à partir de `/openapi.json` : une route renommée casse sa compilation.
Tout changement qui romprait cette règle passe par une version majeure annoncée à l'avance.

Documentation vivante : `http://127.0.0.1:8000/docs`

## Les routes

| Route | Ce qu'elle renvoie | Depuis |
|---|---|---|
| `GET /health` | L'API répond, les données sont présentes | v0.1 |
| `GET /marques` | Les marques et leur urgence (EVT-001) | v0.2 |
| `GET /exposition?marque=` | Le détail d'une marque (EVT-001) | v0.2 |
| `GET /evenements` | La liste des événements calculés | **v0.4** |
| `GET /evenements/{evenement_id}/appels` | La liste d'appels classée : clients, puis prospects | **v0.4** |
| `GET /comptes/{compte_id}` | Un compte, ses marques, les événements qui le touchent, les produits concernés | **v0.4** |

Erreurs : `404` si l'événement ou le compte n'existe pas, `503` si les données ne sont pas calculées.

## GET /evenements/{evenement_id}/appels

Exemple de réponse. Les valeurs montrent la forme, ce ne sont pas des résultats.

```json
{
  "date_maj": "2026-11-12",
  "crm_fictif": true,
  "evenement": {
    "evenement_id": "EVT-001",
    "type": "reglementation",
    "titre": "Nouveaux allergènes de parfum à étiqueter",
    "resume": "…",
    "source_nom": "Règlement (UE) 2023/1545",
    "source_url": "https://eur-lex.europa.eu/eli/reg/2023/1545/oj",
    "date_publication": "2023-07-27",
    "date_echeance": "2028-07-31",
    "statut_validation": "valide",
    "nb_comptes_a_appeler": 4
  },
  "clients": [
    {
      "rang": 1,
      "compte_id": "CPT-001",
      "nom_compte": "Florame",
      "statut": "client",
      "score": 50,
      "raison_classement": "5 produits sur 6 en exposition probable (83 %).",
      "fait": "5 de vos 6 produits analysés sont en exposition probable…",
      "question": "Pour ces produits, préférez-vous compléter l'étiquette ou revoir le parfum ?",
      "arguments": "",
      "origine_textes": "llm_valide",
      "nb_produits_analyses": 6,
      "nb_probable": 5,
      "nb_possible": 0,
      "part_probable": 0.83,
      "confiance": "faible"
    }
  ],
  "prospects": []
}
```

### Champs à connaître côté application

| Champ | À quoi il sert à l'écran |
|---|---|
| `groupe clients` / `prospects` | Deux listes séparées, chacune classée de 1 à N. Ne pas les fusionner |
| `rang` | L'ordre d'appel dans son groupe |
| `score` | `5 × probable (10 max) + 2 × possible (10 max) + 30 × part de probable`. Calculé par du code lisible, pas par un modèle |
| `fait`, `question` | À afficher tels quels. Ne rien reformuler côté application |
| `origine_textes` | `gabarit` : phrase écrite par le code. `llm_valide` : écrite par le LLM local et relue par une personne. Concerne le champ `fait` |
| `arguments` | Vide tant qu'aucun argument n'est validé. Prévoir que le bloc puisse ne pas s'afficher |
| `confiance` | `faible` sous 10 produits analysés, `bonne` à partir de 20. À montrer : le classement est fragile sur peu de produits |
| `crm_fictif` | Toujours vrai. L'écran doit porter une mention « données de démonstration » |

## GET /comptes/{compte_id}

Renvoie le compte, ses marques, ses chiffres de ventes fictifs (`classe_ca`, `nb_parfums`,
`quantite_kg_annee`) et, pour chaque événement qui le touche, la liste des produits concernés
avec leurs ingrédients repérés.

## GET /evenements

La liste des événements calculés, avec pour chacun le nombre de comptes à appeler.
Un événement n'apparaît que s'il est marqué `valide` ou `test` par une personne, et s'il a au moins une règle.

`EVT-002` est un événement d'essai inventé par l'équipe : `statut_validation` vaut `test`.
L'écran peut s'en servir pour afficher un bandeau.

## Vocabulaire

On écrit **exposition probable**, jamais « non conforme ». Le règlement impose un étiquetage
au-delà d'un seuil, et nous ne connaissons pas les concentrations. Un contrôle du pipeline
refuse tout texte contenant « non conforme », « illégal » ou « interdit ».

Les comptes, leur statut client ou prospect, les commerciaux (`KAM-01`…) et les ventes sont
**fictifs** et marqués comme tels. Aucun nom de personne.

Ils s'inspirent de **Pegasus**, le CRM des commerciaux de Givaudan, et de l'ERP pour les ventes.
**Atlas**, le suivi des projets techniques relié à Pegasus, est la source naturelle d'une version
ultérieure : il porte l'avancement des projets côté technique.

## Récupérer le client

```bash
npm run api:pull     # côté hackathon-app, après chaque étiquette annoncée
```

Les livraisons sont annoncées dans le canal de l'équipe avec le numéro d'étiquette.
