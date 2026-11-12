"""REF REGLEMENTATION : liste des allergènes (extrait de travail, à vérifier sur EUR-Lex)."""
from pathlib import Path
import pandas as pd

BRONZE = Path("data/01_bronze/reglementation")
SILVER = Path("data/02_silver/reglementation")

ANCIENNE = ["limonene", "linalool", "geraniol", "citronellol", "citral", "eugenol", "isoeugenol", "coumarin",
            "farnesol", "benzyl alcohol", "benzyl salicylate", "benzyl benzoate", "benzyl cinnamate", "cinnamal",
            "cinnamyl alcohol", "amyl cinnamal", "amylcinnamyl alcohol", "hexyl cinnamal", "hydroxycitronellal",
            "anise alcohol", "alpha-isomethyl ionone", "methyl 2-octynoate", "evernia prunastri", "evernia furfuracea"]
NOUVELLES = ["menthol", "camphor", "vanillin", "linalyl acetate", "terpineol", "pinene", "caryophyllene", "carvone",
             "geranyl acetate", "benzaldehyde", "anethole", "methyl salicylate", "amyl salicylate", "terpinolene",
             "santalol", "sclareol"]
EXTRAITS = {
    "lavande": r"lavandula (angustifolia|hybrida|intermedia|spica|latifolia)[^,;]{0,45}(oil|extract)",
    "rose": r"rosa (damascena|centifolia|alba|gallica|moschata|rubiginosa|canina)[^,;]{0,12}flower[^,;]{0,12}(oil|extract)",
    "ylang-ylang": r"cananga odorata[^,;]{0,30}(oil|extract)",
    "bergamote": r"citrus (aurantium )?bergamia[^,;]{0,40}oil",
    "citron": r"citrus (medica )?limon(um)?[^,;]{0,25}(peel|fruit)?[^,;]{0,12}oil",
    "orange": r"citrus (aurantium dulcis|sinensis|aurantium amara)[^,;]{0,40}(peel|flower|leaf)[^,;]{0,12}oil",
    "menthe": r"mentha (piperita|viridis|spicata|arvensis)[^,;]{0,30}oil",
    "eucalyptus": r"eucalyptus globulus[^,;]{0,25}oil",
    "girofle": r"eugenia caryophyllus[^,;]{0,30}oil",
    "geranium": r"pelargonium graveolens[^,;]{0,30}oil",
    "patchouli": r"pogostemon cablin[^,;]{0,25}oil",
    "jasmin": r"jasminum (officinale|grandiflorum|sambac)[^,;]{0,30}(oil|extract)",
    "santal": r"santalum album[^,;]{0,25}oil",
    "cannelle": r"cinnamomum (cassia|zeylanicum)[^,;]{0,30}oil",
    "citronnelle": r"cymbopogon (citratus|schoenanthus|flexuosus|nardus|winterianus)[^,;]{0,30}oil",
    "cedre": r"(cedrus atlantica|juniperus virginiana)[^,;]{0,30}oil",
    "laurier": r"laurus nobilis[^,;]{0,30}oil",
    "badiane": r"illicium verum[^,;]{0,30}oil",
}


def main():
    lignes = []
    for nom in ANCIENNE:
        lignes.append([nom, "ancienne", "substance", nom, "Règlement (CE) 1223/2009, annexe III"])
    for nom in NOUVELLES:
        lignes.append([nom, "nouvelle", "substance", nom, "Règlement (UE) 2023/1545"])
    for nom, motif in EXTRAITS.items():
        lignes.append([nom, "nouvelle", "extrait_naturel", motif, "Règlement (UE) 2023/1545"])

    df = pd.DataFrame(lignes, columns=["nom_usuel", "liste", "type", "motif_recherche", "source"])
    df.insert(0, "allergene_id", [f"A{i:03d}" for i in range(1, len(df) + 1)])
    df["statut_verification"] = "a_verifier_eurlex"

    BRONZE.mkdir(parents=True, exist_ok=True)
    SILVER.mkdir(parents=True, exist_ok=True)
    df.to_csv(BRONZE / "brz_ref_allergenes_eurlex.csv", index=False)
    df.to_csv(SILVER / "slv_ref_allergenes.csv", index=False)
    print(df.groupby(["liste", "type"]).size().to_string())
    print(f"Total : {len(df)} allergènes (statut : a_verifier_eurlex)")


if __name__ == "__main__":
    main()