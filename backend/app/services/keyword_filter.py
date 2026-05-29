"""Heuristic food/non-food classifier for Kaufda offers.

Matching rules:
  Exclusion keywords:
    len <= 4               → word-boundary only  ("bier"→"Bierwurst", "tee"→"Teewurst")
    len >  4               → also substring      ("chips"→"Crunchips", "kaffee"→"Röstkaffee")
    in _EXCL_BOUNDARY_ONLY → word-boundary only regardless of length
                             (e.g. "reise" — protects "Reisessig" from exclusion)

  Positive keywords:
    len <= 4               → word-boundary only  ("reis"→"Reise"/"Kreis", "salz"→"Salzburg")
    len >  4               → also substring      ("schwein"→"Schweinehalssteaks")
    in _POS_COMPOUND_ALLOW → also substring even if len == 4
                             (e.g. "käse"→"Ofenkäse", "mais"→"Zuckermais", "kalb"→"Kalbsbraten")
"""

import re

_EXCL_BOUNDARY_ONLY_MAX = 4   # exclusion kw with len <= this: word-boundary only
_POS_BOUNDARY_ONLY_MAX = 4    # positive kw with len <= this: word-boundary only

# Exclusion keywords forced to word-boundary (regardless of length):
_EXCL_BOUNDARY_ONLY: frozenset[str] = frozenset({"reise"})

# 4-char positive keywords that are safe for compound matching:
#   "käse" → Ofenkäse, Weichkäse, Hartkäse
#   "mais" → Zuckermais, Sonnenmais
#   "brot" → Vollkornbrot, Roggenvollkornbrot
#   "kalb" → Kalbsbraten, Kalbsschnitzel
_POS_COMPOUND_ALLOW: frozenset[str] = frozenset({"käse", "mais", "brot", "kalb"})


_EXCLUSION_KEYWORDS = {
    # Haushalt
    "waschmittel", "spülmittel", "putzmittel", "reiniger", "weichspüler",
    "klopapier", "toilettenpapier", "küchentücher", "taschentücher",
    "wischmopp", "schwamm", "handschuhe", "mülltüten", "frischhaltefolie",
    "alufolie", "backpapier", "gefrierbeutel",
    "schlauch",   # Gartenschlauch — verhindert dass "lauch" in "Schlauch" matcht
    # Tierfutter / Tierpflege / Tierbedarf-Marken
    "hundefutter", "katzenfutter", "tierfutter", "hundesnack", "katzensnack",
    "heimtierbedarf", "aquarium", "hunde", "katzen", "tiernahrung",
    "orlando",    # Lidl Tiernahrungsmarke (Orlando Gourmet/Pure Taste)
    "dekofisch",  # "Dekofische" (Zierfische) — verhindert "fisch" False-Positive
    # Körperpflege / Drogerie / Medizin
    "shampoo", "duschgel", "deo", "deodorant", "zahnbürste", "zahnpasta",
    "zahnfleisch", "rasierer", "lotion", "sonnencreme", "wundpflaster",
    "windeln", "babypflege", "wattepads",
    "slipeinlag", "damenbind", "inkontinenz",
    # Non-Food-Elektronik / Sonstiges
    "batterie", "glühbirne", "ladekabel", "usb", "kopfhörer",
    "kleidung", "socken", "unterwäsche", "hemd", "hose", "jacke",
    "spielzeug", "buch", "zeitschrift", "blumenerde",
    "induktion",  # Küchengeräte: "für alle Herdarten, inkl. Induktion"
    # Reisen / Veranstaltungen
    "reise",      # in _EXCL_BOUNDARY_ONLY → nur bilateral Word-Boundary
                  # Fängt "5-tägige Reise," aber NICHT "Reisessig" (Reisweinessig)
    "kreuzfahrt", "halbpension", "vollpension", "reisebüro", "nächte",
    # Produktdesign / Farb-Hinweise in Beschreibungen
    "design",     # "Weitere Designs: Kirschen, Blumen, Beige"
    "farben",     # "Weitere Farben: Orange, Türkis"
    # "blumen" + "pflanzen" NICHT hier: würden "Sonnenblumenöl", "Pflanzenmargarine" treffen.
    # Snacks / Süßwaren (nicht kochrelevant)
    "chips", "popcorn", "gummibärchen", "schokolade", "schokoriegel",
    "kekse", "cracker", "salzstangen", "nachos",
    # Getränke
    "bier", "wein", "sekt", "prosecco", "secco", "radler",
    "spirituosen", "whisky", "vodka", "direktsaft", "milchshake",
    "cola", "fanta", "sprite", "softdrink", "energydrink", "energy",
    "limonade", "mineralwasser", "saft", "nektar",
    "kaffee", "tee", "kakao",
}

_FOOD_POSITIVE = {
    # Protein / Fleisch
    "hähnchen", "huhn", "hühnchen", "pute", "truthahn",
    "rind", "rinderhack", "schwein", "schweinefilet",
    "lammfleisch", "lamm", "hackfleisch",
    "bratwurst", "würstchen", "wurst",
    "aufschnitt", "schinken", "speck",
    "lachs", "forelle", "thunfisch", "garnelen", "shrimps",
    "fisch", "kabeljau", "seelachs", "scholle", "dorade", "tilapia",
    "gulasch", "steak", "schnitzel", "kalb", "braten",
    "fleisch", "filet", "bacon", "mortadella", "salami",
    "ragout", "keule", "lende", "spareribs", "ribs",
    # Milchprodukte
    "joghurt", "quark", "frischkäse", "käse", "mozzarella",
    "gouda", "edamer", "parmesan", "parmigiano", "ricotta", "schmand",
    "halloumi",
    "sahne", "schlagsahne", "butter", "margarine", "milch",
    "skyr", "fraîche", "fraiche", "creme",
    # Gemüse & Obst
    "tomate", "gurke", "paprika", "zucchini", "aubergine",
    "brokkoli", "blumenkohl", "spinat", "salat", "kopfsalat",
    "eisbergsalat", "rucola", "feldsalat", "mangold",
    "lauch", "zwiebel", "knoblauch", "karotte", "möhre",
    "sellerie", "petersilie", "basilikum", "koriander", "ingwer",
    "thymian", "rosmarin", "schnittlauch", "kräuter",
    "champignon", "pilze", "erbsen", "bohnen", "linsen",
    "kichererbsen", "mais", "kartoffel", "süßkartoffel",
    "kürbis", "rote bete", "kohlrabi", "weißkohl", "rotkohl",
    "spitzkohl", "fenchel", "staudensellerie", "spargel", "radieschen",
    "apfel", "birne", "banane", "erdbeer", "kirsche",
    "traube", "orange", "mandarine", "zitrone", "limette",
    "mango", "ananas", "kiwi", "avocado", "melone", "aprikose",
    # Pantry
    "reis", "nudeln", "pasta", "spaghetti", "penne",
    "fusilli", "farfalle", "lasagne", "teigwaren",
    "mehl", "zucker", "salz", "pfeffer", "olivenöl", "rapsöl", "sonnenblumenöl", "essig",
    "tomatenmark", "dosentomaten", "passata", "ketchup",
    "senf", "mayonnaise", "sojasoße", "worcestersauce",
    "kokosmilch", "currypaste", "brühe", "fond",
    "brot", "brötchen", "toast", "knäckebrot", "croissant",
    "eier", "ei",  # word-boundary only (len=2 <= threshold)
    "öl",          # word-boundary only (len=2 <= threshold)
    # Fertigprodukte mit Kochbezug
    "tortellini", "gnocchi", "ravioli", "pizza", "tiefkühl", "tk-",
}


def _normalize(text: str) -> str:
    return text.lower().replace("-", " ").replace("_", " ")


def _word_boundary_match(kw: str, text: str) -> bool:
    return bool(re.search(r"(^|\s|[,;:(])" + re.escape(kw) + r"($|\s|[,;:)])", text))


def is_cooking_relevant(product_name: str, quantity_text: str | None = None) -> bool:
    combined = _normalize(product_name)
    if quantity_text:
        combined += " " + _normalize(quantity_text)

    # Hard exclusion checked first.
    for kw in _EXCLUSION_KEYWORDS:
        if _word_boundary_match(kw, combined):
            return False
        # Substring matching for long keywords — unless in the bilateral-only override set.
        if len(kw) > _EXCL_BOUNDARY_ONLY_MAX and kw not in _EXCL_BOUNDARY_ONLY and kw in combined:
            return False

    # Positive match.
    for kw in _FOOD_POSITIVE:
        if _word_boundary_match(kw, combined):
            return True
        # Substring for keywords longer than threshold, or in the explicit allow list.
        do_substring = (
            kw in _POS_COMPOUND_ALLOW
            or len(kw) > _POS_BOUNDARY_ONLY_MAX
        )
        if do_substring and kw in combined:
            return True

    return False
