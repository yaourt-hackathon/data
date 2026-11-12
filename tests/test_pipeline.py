"""Tests : à lancer avec « python -m pytest » depuis la racine, après « python pipeline.py »."""
import sys
from pathlib import Path

import pandas as pd
import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

import appels  # noqa: E402
import controles  # noqa: E402
import detection  # noqa: E402
from commun import normaliser, slug  # noqa: E402


def produits(*ingredients):
    return pd.DataFrame({"code": [str(i) for i in range(len(ingredients))], "marque": "essai", "nom": "produit",
                         "ingredients": list(ingredients), "type_rincage": "rince", "date_fiche": "2026-01-01",
                         "source": "test"})


def regles():
    return pd.DataFrame([
        {"evenement_id": "EVT-900", "nom_usuel": "menthol", "role": "direct", "type": "substance", "motif_recherche": "menthol"},
        {"evenement_id": "EVT-900", "nom_usuel": "lavande", "role": "direct", "type": "extrait_naturel",
         "motif_recherche": r"lavandula angustifolia[^,;]{0,45}oil"},
        {"evenement_id": "EVT-900", "nom_usuel": "linalool", "role": "indice", "type": "substance", "motif_recherche": "linalool"}])


def evenement(parfum_masque):
    return pd.DataFrame([{"evenement_id": "EVT-900", "parfum_masque": parfum_masque}])


def niveaux(textes, parfum_masque="oui"):
    return detection.detecter(produits(*textes), evenement(parfum_masque), regles())["niveau"].tolist()


def test_un_ingredient_direct_donne_probable():
    assert niveaux(["Aqua, Glycerin, Menthol, Parfum"]) == ["probable"]
    assert niveaux(["Aqua, Lavandula Angustifolia (Lavender) Oil*, Glycerin"]) == ["probable"]


def test_parfum_et_indice_donnent_possible_puis_indetermine_puis_rien():
    assert niveaux(["Aqua, Parfum, Linalool", "Aqua, Parfum (Fragrance)", "Aqua, Glycerin"]) == ["possible", "indetermine", "non_detecte"]


def test_sans_parfum_masque_un_parfum_seul_ne_compte_pas():
    assert niveaux(["Aqua, Parfum", "Aqua, Linalool"], parfum_masque="non") == ["non_detecte", "possible"]


def test_une_substance_se_cherche_comme_un_mot_entier():
    assert niveaux(["Aqua, Mentholatum, Glycerin"]) == ["non_detecte"]


def test_normaliser_et_slug():
    assert normaliser("Huile – Lavandé*;  Eau") == "huile, lavande, eau"
    assert slug("So'Bio étic") == "so-bio-etic"


def test_score_et_confiance():
    assert appels.score(5, 0, 6) == 50
    assert appels.score(0, 0, 0) == 0
    assert appels.score(30, 30, 30) == 100
    assert [appels.confiance(n) for n in (6, 10, 20)] == ["faible", "moyenne", "bonne"]


def test_les_controles_passent_sur_les_donnees_du_depot():
    assert controles.controler() == []


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app)


def test_api_anciennes_routes_inchangees(client):
    assert client.get("/health").json()["status"] == "ok"
    marques = client.get("/marques").json()["marques"]
    assert {"id", "marque", "nb_produits", "nb_probable", "urgence"} <= set(marques[0])
    expo = client.get("/exposition", params={"marque": marques[0]["id"]}).json()
    assert {"produits", "nb_probable", "source", "urgence"} <= set(expo)
    assert client.get("/exposition", params={"marque": "inconnue"}).status_code == 404


def test_api_liste_d_appels(client):
    evts = client.get("/evenements").json()["evenements"]
    assert "EVT-001" in [e["evenement_id"] for e in evts]
    r = client.get("/evenements/EVT-001/appels").json()
    assert r["crm_fictif"] is True
    for groupe in ("clients", "prospects"):
        assert [a["rang"] for a in r[groupe]] == list(range(1, len(r[groupe]) + 1))
        assert [a["score"] for a in r[groupe]] == sorted([a["score"] for a in r[groupe]], reverse=True)
    assert client.get("/evenements/EVT-999/appels").status_code == 404


def test_api_fiche_compte(client):
    premier = client.get("/evenements/EVT-001/appels").json()["clients"][0]
    c = client.get(f"/comptes/{premier['compte_id']}").json()
    assert c["crm_fictif"] is True and c["commercial"].startswith("KAM-")
    assert sum(p["niveau"] == "probable" for p in c["evenements"][0]["produits"]) == premier["nb_probable"]
    assert client.get("/comptes/CPT-999").status_code == 404


def test_api_fiche_compte_porte_de_quoi_preparer_un_rendez_vous(client):
    """L'écran « avant le rendez-vous » doit se construire sans rappeler /evenements."""
    premier = client.get("/evenements/EVT-001/appels").json()["clients"][0]
    bloc = client.get(f"/comptes/{premier['compte_id']}").json()["evenements"][0]
    assert bloc["source_nom"] and bloc["source_url"].startswith("http")   # ouvrir la source depuis la fiche
    assert bloc["nb_probable"] == premier["nb_probable"]                  # mêmes chiffres que la liste d'appels
    assert bloc["nb_possible"] == premier["nb_possible"]
    assert bloc["confiance"] == premier["confiance"]
    assert bloc["origine_textes"] in ("gabarit", "llm_valide")
