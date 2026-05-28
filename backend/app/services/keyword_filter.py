"""Heuristic food/non-food classifier for Kaufda offers.

Mirrors the keyword logic described in the original workflow (Idee.md):
positive keywords mark cooking-relevant items, exclusion lists filter them out.
The goal is a robust heuristic — not perfect semantics.
"""

import re

_FOOD_POSITIVE = {
    # Protein
    "hähnchen", "huhn", "hühnchen", "pute", "truthahn", "rind", "rinderhack", "schwein",
    "schweinefilet", "lammfleisch", "lamm", "hackfleisch", "bratwurst", "würstchen", "wurst",
    "aufschnitt", "schinken", "speck", "lachs", "forelle", "thunfisch", "garnelen", "shrimps",
    "fisch", "kabeljau", "seelachs", "scholle", "dorade", "tilapia",
    # Milchprodukte
    "joghurt", "quark", "frischkäse", "käse", "mozzarella", "gouda", "edamer", "parmesan",
    "ricotta", "schmand", "sahne", "schlagsahne", "butter", "margarine", "milch",
    # Gemüse & Obst
    "tomate", "gurke", "paprika", "zucchini", "aubergine", "brokkoli", "blumenkohl",
    "spinat", "salat", "kopfsalat", "eisbergsalat", "rucola", "feldsalat", "mangold",
    "lauch", "zwiebel", "knoblauch", "karotte", "möhre", "sellerie", "petersilie",
    "basilikum", "koriander", "thymian", "rosmarin", "schnittlauch", "kräuter",
    "champignon", "pilze", "erbsen", "bohnen", "linsen", "kichererbsen", "mais",
    "kartoffel", "süßkartoffel", "kürbis", "rote bete", "kohlrabi", "weißkohl",
    "rotkohl", "spitzkohl", "fenchel", "staudensellerie",
    "apfel", "birne", "banane", "erdbeere", "kirsche", "traube", "orange", "mandarine",
    "zitrone", "limette", "mango", "ananas", "kiwi", "avocado", "melone",
    # Pantry
    "reis", "nudeln", "pasta", "spaghetti", "penne", "fusilli", "farfalle", "lasagne",
    "mehl", "zucker", "salz", "pfeffer", "öl", "olivenöl", "rapsöl", "essig",
    "tomatenmark", "dosentomaten", "passata", "ketchup", "senf", "mayonnaise",
    "sojasoße", "worcestersauce", "kokosmilch", "currypaste",
    "linsen", "kichererbsen", "bohnen", "linsensuppe",
    "brot", "brötchen", "toast", "knäckebrot", "croissant",
    "eier", "ei",
    # Fertigprodukte mit Kochbezug
    "tortellini", "gnocchi", "ravioli", "pizza", "tiefkühl", "tk-",
}

_EXCLUSION_KEYWORDS = {
    # Haushalt
    "waschmittel", "spülmittel", "putzmittel", "reiniger", "weichspüler",
    "klopapier", "toilettenpapier", "küchentücher", "taschentücher",
    "wischmopp", "schwamm", "handschuhe", "mülltüten", "frischhaltefolie",
    "alufolie", "backpapier", "gefrierbeutel",
    # Tierfutter
    "hundefutter", "katzenfutter", "tierfutter", "hundesnack", "katzensnack",
    "heimtierbedarf", "aquarium",
    # Körperpflege / Drogerie
    "shampoo", "duschgel", "deo", "deodorant", "zahnbürste", "zahnpasta",
    "rasierer", "lotion", "creme", "sonnencreme", "wundpflaster",
    "windeln", "babypflege", "wattepads",
    # Non-Food-Elektronik / Sonstiges
    "batterie", "glühbirne", "led", "ladekabel", "usb", "kopfhörer",
    "kleidung", "socken", "unterwäsche", "hemd", "hose", "jacke",
    "spielzeug", "buch", "zeitschrift", "blumen", "pflanzen", "blumenerde",
    # Snacks / Süßwaren (meistens nicht kochrelevant)
    "chips", "popcorn", "gummibärchen", "schokolade", "schokoriegel",
    "kekse", "cracker", "salzstangen", "nachos",
    # Getränke (meistens nicht kochrelevant)
    "bier", "wein", "sekt", "prosecco", "spirituosen", "whisky", "vodka",
    "cola", "fanta", "sprite", "softdrink", "energydrink", "limonade",
    "mineralwasser", "saft", "nektar", "kaffee", "tee", "kakao",
}


def _normalize(text: str) -> str:
    return text.lower().replace("-", " ").replace("_", " ")


def is_cooking_relevant(product_name: str, quantity_text: str | None = None) -> bool:
    combined = _normalize(product_name)
    if quantity_text:
        combined += " " + _normalize(quantity_text)

    # Hard exclusion first
    for kw in _EXCLUSION_KEYWORDS:
        if kw in combined:
            return False

    # Positive match
    for kw in _FOOD_POSITIVE:
        # Word-boundary-like check: keyword must appear as a whole word/token
        if re.search(r"(^|\s|[,;:])" + re.escape(kw) + r"($|\s|[,;:])", combined):
            return True
        # Also check as substring for compound words (German: "Rinderhackfleisch")
        if kw in combined:
            return True

    return False
