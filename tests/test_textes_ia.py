"""Les contrôles qui empêchent un texte inventé d'arriver jusqu'au commercial.

Le LLM n'est pas appelé ici : on teste la préparation des faits et le filtre des réponses.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import textes_ia  # noqa: E402

APPEL = {"nom_compte": "Florame", "statut": "client", "nb_produits_analyses": 6, "nb_probable": 5, "nb_possible": 0}
PRODUITS = pd.DataFrame({"elements_directs": ["lavande|citron", "orange"]})
EVENEMENT = {"titre": "Nouveaux allergènes de parfum à étiqueter", "source_nom": "Règlement (UE) 2023/1545",
             "question_type": "Compléter l'étiquette ou revoir le parfum ?", "date_echeance": "2028-07-31"}


@pytest.fixture
def bloc():
    return textes_ia.faits(APPEL, PRODUITS, EVENEMENT)


def test_les_faits_ne_contiennent_que_du_calcule(bloc):
    assert "5" in bloc and "6" in bloc
    assert "citron, lavande, orange" in bloc          # dédoublonnés et triés
    assert "fictive" in bloc                          # la relation est signalée comme inventée


def test_un_texte_fidele_est_garde(bloc):
    autorises = textes_ia.nombres_autorises(bloc)
    assert textes_ia.controler("5 produits sur 6 listent un ingrédient visé (83 %).", autorises) == ""


def test_un_chiffre_invente_est_refuse(bloc):
    autorises = textes_ia.nombres_autorises(bloc)
    assert "12" in textes_ia.controler("12 produits sont concernés.", autorises)


def test_le_vocabulaire_interdit_est_refuse(bloc):
    autorises = textes_ia.nombres_autorises(bloc)
    for texte in ["Vos produits sont non conformes.", "C'est illégal depuis 2023.", "Ce produit est interdit."]:
        assert textes_ia.controler(texte, autorises) == "vocabulaire interdit"


def test_un_texte_vide_ou_trop_long_est_refuse(bloc):
    autorises = textes_ia.nombres_autorises(bloc)
    assert textes_ia.controler("", autorises) == "texte vide ou trop long"
    assert textes_ia.controler("a" * 401, autorises) == "texte vide ou trop long"


def test_une_liste_d_arguments_devient_du_texte():
    textes = textes_ia.reponse_en_textes({"fait": " un  fait ", "question": "et vous ?",
                                          "arguments": ["premier", "second"]})
    assert textes == {"fait": "un fait", "question": "et vous ?", "arguments": "premier. second."}


def test_une_reponse_illisible_ne_fait_pas_tomber_le_script():
    assert textes_ia.reponse_en_textes({}) == {"fait": "", "question": "", "arguments": ""}


def test_une_obligation_inventee_est_refusee(bloc):
    autorises = textes_ia.nombres_autorises(bloc)
    assert textes_ia.controler("L'industrie doit réviser ses étiquettes.", autorises) == "invente une obligation"


def test_un_delai_invente_est_refuse(bloc):
    autorises = textes_ia.nombres_autorises(bloc)
    # « 5 » vient du nombre de produits : le chiffre est autorisé, la phrase est fausse.
    assert textes_ia.controler("Une nouvelle règle s'applique dans les 5 ans.", autorises) == "invente un délai"


def test_un_ingredient_absent_des_etiquettes_est_refuse(bloc):
    autorises = textes_ia.nombres_autorises(bloc)
    hors = textes_ia.vocabulaire_hors_faits(bloc, ["citron", "lavande", "orange", "geraniol"])
    assert hors == ["geraniol"]
    motif = textes_ia.controler("5 produits sur 6 contiennent du géraniol.", autorises, "fait", ["5", "6"], hors)
    assert motif == "ingrédient absent des étiquettes de ce compte : geraniol"


def test_un_fait_sans_les_nombres_de_la_detection_est_refuse(bloc):
    autorises = textes_ia.nombres_autorises(bloc)
    assert "5, 6" in textes_ia.controler("Vos produits sont concernés.", autorises, "fait", ["5", "6"])
    # la question, elle, n'a pas à citer de nombre
    assert textes_ia.controler("Compléter l'étiquette ou revoir le parfum ?", autorises, "question", ["5", "6"]) == ""
