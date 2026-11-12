"""ÉVÉNEMENTS ET RÈGLES : sources -> bronze -> silver (contrôlé, rejets expliqués) -> gold.

Un événement n'est calculé que si une personne l'a marqué « valide » (ou « test » pour un essai).
"""
import re

import pandas as pd

from commun import AUJOURDHUI, BRONZE, GOLD, SILVER, SOURCES, date_valide, ecrire, lire

SRC_EVENEMENTS = SOURCES / "evenements/evenements.csv"
SRC_REGLES = SOURCES / "regles_detection"

COL_EVENEMENTS = ["evenement_id", "type", "titre", "resume", "perimetre", "source_nom", "source_url",
                  "date_publication", "date_echeance", "parfum_masque", "question_type",
                  "statut_validation", "saisi_par"]
COL_REGLES = ["evenement_id", "regle_id", "nom_usuel", "role", "type", "motif_recherche", "source",
              "reference", "statut_verification", "verifie_par"]
STATUTS = ["valide", "test", "a_valider", "rejete"]
CALCULES = ["valide", "test"]


def colonnes_manquantes(df, attendues, nom):
    manque = [c for c in attendues if c not in df.columns]
    if manque:
        raise SystemExit(f"ERREUR {nom} : colonnes manquantes {manque}")


def motif_valide(motif):
    try:
        re.compile(motif)
        return motif != ""
    except re.error:
        return False


def main():
    # --- bronze : copie brute
    evt = lire(SRC_EVENEMENTS)
    colonnes_manquantes(evt, COL_EVENEMENTS, SRC_EVENEMENTS.name)
    fichiers = sorted(SRC_REGLES.glob("EVT-*.csv"))
    lots = []
    for f in fichiers:
        lot = lire(f)
        colonnes_manquantes(lot, COL_REGLES, f.name)
        lots.append(lot.assign(fichier_source=f.name))
    regles = pd.concat(lots, ignore_index=True) if lots else pd.DataFrame(columns=COL_REGLES + ["fichier_source"])
    ecrire(evt.assign(date_chargement=AUJOURDHUI), BRONZE / "evenements/brz_ref_evenements.csv")
    ecrire(regles.assign(date_chargement=AUJOURDHUI), BRONZE / "evenements/brz_ref_regles_detection.csv")

    # --- silver : règles
    for c in COL_REGLES:
        regles[c] = regles[c].str.strip()
    r = pd.Series("", index=regles.index)
    r[~regles["motif_recherche"].apply(motif_valide)] = "motif_illisible"
    r[~regles["type"].isin(["substance", "extrait_naturel"])] = "type_inconnu"
    r[~regles["role"].isin(["direct", "indice"])] = "role_inconnu"
    r[regles["nom_usuel"] == ""] = "nom_vide"
    r[regles["evenement_id"] + ".csv" != regles["fichier_source"]] = "evenement_different_du_fichier"
    r[~regles["evenement_id"].isin(evt["evenement_id"])] = "evenement_inconnu"
    r[regles.duplicated(subset=["evenement_id", "regle_id"], keep="first")] = "doublon"
    regles_ok = regles[r == ""][COL_REGLES]
    ecrire(regles_ok, SILVER / "evenements/slv_ref_regles_detection.csv")
    ecrire(regles[r != ""].assign(motif_rejet=r[r != ""]), SILVER / "evenements/slv_ref_regles_detection_rejets.csv")

    # --- silver : événements
    for c in COL_EVENEMENTS:
        evt[c] = evt[c].str.strip()
    e = pd.Series("", index=evt.index)
    e[~evt["parfum_masque"].isin(["oui", "non"])] = "parfum_masque_ni_oui_ni_non"
    e[~evt["date_echeance"].apply(date_valide)] = "date_echeance_invalide"
    e[~evt["date_publication"].apply(date_valide)] = "date_publication_invalide"
    e[~evt["statut_validation"].isin(STATUTS)] = "statut_inconnu"
    e[(evt["titre"] == "") | (evt["question_type"] == "") | (evt["source_nom"] == "")] = "champ_obligatoire_vide"
    e[evt.duplicated(subset="evenement_id", keep="first")] = "doublon"
    e[~evt["evenement_id"].str.fullmatch(r"EVT-\d{3}")] = "identifiant_invalide"
    evt_ok = evt[e == ""][COL_EVENEMENTS]
    ecrire(evt_ok, SILVER / "evenements/slv_ref_evenements.csv")
    ecrire(evt[e != ""].assign(motif_rejet=e[e != ""]), SILVER / "evenements/slv_ref_evenements_rejets.csv")

    # --- gold : les événements à calculer
    nb = regles_ok.groupby(["evenement_id", "role"]).size().unstack(fill_value=0)
    gold = evt_ok[evt_ok["statut_validation"].isin(CALCULES)].copy()
    gold["nb_regles_directes"] = gold["evenement_id"].map(nb.get("direct", pd.Series(dtype=int))).fillna(0).astype(int)
    gold["nb_regles_indices"] = gold["evenement_id"].map(nb.get("indice", pd.Series(dtype=int))).fillna(0).astype(int)
    sans_regle = gold[gold["nb_regles_directes"] == 0]["evenement_id"].tolist()
    gold = gold[gold["nb_regles_directes"] > 0]
    ecrire(gold, GOLD / "gld_dim_evenements.csv")

    print(f"Événements : {len(evt)} lus, {len(evt_ok)} retenus, {len(gold)} à calculer "
          f"({', '.join(gold['evenement_id']) or 'aucun'})")
    en_attente = evt_ok[~evt_ok["statut_validation"].isin(CALCULES)]["evenement_id"].tolist()
    if en_attente:
        print(f"  en attente de validation ou rejetés par une personne : {en_attente}")
    if sans_regle:
        print(f"  sans règle directe, donc non calculés : {sans_regle}")
    print(f"Règles : {len(regles)} lues, {len(regles_ok)} retenues, {int((r != '').sum())} rejetées")
    if (r != "").any():
        print(r[r != ""].value_counts().to_string())
    if (e != "").any():
        print(e[e != ""].value_counts().to_string())


if __name__ == "__main__":
    main()
