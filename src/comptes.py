"""COMPTES ET VENTES (CRM et SAP fictifs) : sources -> bronze -> silver -> gold gld_dim_comptes.

Tout est inventé pour la démonstration et marqué « fictif ». Le statut client ou prospect
ne dit rien de la relation réelle entre ces marques et Givaudan.
"""
import pandas as pd

from commun import AUJOURDHUI, BRONZE, GOLD, SILVER, SOURCES, date_valide, ecrire, lire
from detection import lire_produits

SRC_COMPTES = SOURCES / "crm/comptes_fictifs.csv"
SRC_MARQUES = SOURCES / "crm/marques_comptes_fictif.csv"
SRC_VENTES = SOURCES / "sap/ventes_fictives.csv"
COL_VENTES = ["vente_id", "compte_id", "reference_parfum", "code_produit", "annee", "quantite_kg", "classe_ca", "fictif"]


def main():
    comptes, marques = lire(SRC_COMPTES), lire(SRC_MARQUES)
    ventes = lire(SRC_VENTES) if SRC_VENTES.exists() else pd.DataFrame(columns=COL_VENTES)
    ecrire(comptes.assign(date_chargement=AUJOURDHUI), BRONZE / "clients/brz_msd_comptes_crm.csv")
    ecrire(marques.assign(date_chargement=AUJOURDHUI), BRONZE / "clients/brz_ref_marques_comptes_crm.csv")
    ecrire(ventes.assign(date_chargement=AUJOURDHUI), BRONZE / "ventes/brz_trd_ventes_sap.csv")

    # --- silver : comptes
    c = pd.Series("", index=comptes.index)
    c[comptes["fictif"] != "oui"] = "non_marque_fictif"
    c[~comptes["dernier_contact"].apply(date_valide)] = "date_invalide"
    c[~comptes["commercial"].str.fullmatch(r"KAM-\d{2}")] = "commercial_pas_un_code"
    c[~comptes["statut"].isin(["client", "prospect"])] = "statut_inconnu"
    c[comptes["nom_compte"].str.strip() == ""] = "nom_vide"
    c[comptes.duplicated(subset="compte_id", keep="first")] = "doublon"
    c[~comptes["compte_id"].str.fullmatch(r"CPT-\d{3}")] = "identifiant_invalide"
    comptes_ok = comptes[c == ""]
    ecrire(comptes_ok, SILVER / "clients/slv_msd_comptes.csv")
    ecrire(comptes[c != ""].assign(motif_rejet=c[c != ""]), SILVER / "clients/slv_msd_comptes_rejets.csv")

    # --- silver : marques rattachées
    m = pd.Series("", index=marques.index)
    m[~marques["compte_id"].isin(comptes_ok["compte_id"])] = "compte_inconnu"
    m[marques.duplicated(subset="marque", keep="first")] = "doublon"
    m[marques["marque"].str.strip() == ""] = "marque_vide"
    marques_ok = marques[m == ""]
    ecrire(marques_ok, SILVER / "clients/slv_ref_marques_comptes.csv")
    ecrire(marques[m != ""].assign(motif_rejet=m[m != ""]), SILVER / "clients/slv_ref_marques_comptes_rejets.csv")

    # --- silver : ventes
    produits = lire_produits().merge(marques_ok[["marque", "compte_id"]], on="marque", how="left")
    clients = comptes_ok[comptes_ok["statut"] == "client"]["compte_id"]
    quantite = pd.to_numeric(ventes["quantite_kg"], errors="coerce")
    v = pd.Series("", index=ventes.index)
    v[ventes["fictif"] != "oui"] = "non_marque_fictif"
    v[~ventes["classe_ca"].isin(["A", "B", "C"])] = "classe_inconnue"
    v[~(quantite > 0)] = "quantite_invalide"
    v[~ventes["annee"].str.fullmatch(r"20\d{2}")] = "annee_invalide"
    v[~ventes["reference_parfum"].str.fullmatch(r"PF-\d{4}")] = "reference_parfum_invalide"
    v[~ventes["compte_id"].isin(clients)] = "compte_pas_client"
    v[ventes.duplicated(subset="vente_id", keep="first")] = "doublon"
    paires = set(zip(produits["compte_id"], produits["code"]))
    connu = [("oui" if (cid, code) in paires else "non") if code else "" for cid, code in zip(ventes["compte_id"], ventes["code_produit"])]
    ventes_ok = ventes.assign(code_produit_connu=connu)[v == ""]
    ecrire(ventes_ok, SILVER / "ventes/slv_trd_ventes.csv")
    ecrire(ventes[v != ""].assign(motif_rejet=v[v != ""]), SILVER / "ventes/slv_trd_ventes_rejets.csv")

    # --- gold : une ligne par compte
    gold = comptes_ok.copy()
    par_compte = marques_ok.groupby("compte_id")["marque"]
    gold["marques"] = gold["compte_id"].map(par_compte.apply("|".join)).fillna("")
    gold["nb_marques"] = gold["compte_id"].map(par_compte.size()).fillna(0).astype(int)
    gold["nb_produits_analyses"] = gold["compte_id"].map(produits.groupby("compte_id").size()).fillna(0).astype(int)
    vk = ventes_ok.assign(quantite_kg=pd.to_numeric(ventes_ok["quantite_kg"]))
    annee = vk["annee"].max() if len(vk) else ""
    gold["annee_ventes"] = annee
    gold["quantite_kg_annee"] = gold["compte_id"].map(vk[vk["annee"] == annee].groupby("compte_id")["quantite_kg"].sum()).fillna(0).astype(int)
    gold["nb_parfums"] = gold["compte_id"].map(vk.groupby("compte_id")["reference_parfum"].nunique()).fillna(0).astype(int)
    gold["classe_ca"] = gold["compte_id"].map(vk.groupby("compte_id")["classe_ca"].first()).fillna("")
    ecrire(gold, GOLD / "gld_dim_comptes.csv")

    print(f"Comptes : {len(comptes_ok)} retenus ({comptes_ok['statut'].value_counts().to_dict()}), {int((c != '').sum())} rejetés")
    print(f"Marques rattachées : {len(marques_ok)}, {int((m != '').sum())} rejetées")
    print(f"Ventes fictives : {len(ventes_ok)} retenues, {int((v != '').sum())} rejetées")
    for serie in (c, m, v):
        if (serie != "").any():
            print(serie[serie != ""].value_counts().to_string())
    sans_compte = sorted(produits[produits["compte_id"].isna()]["marque"].unique())
    if sans_compte:
        print(f"  ATTENTION, marques collectées sans compte : {sans_compte}")


if __name__ == "__main__":
    main()
