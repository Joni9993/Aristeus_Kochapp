"""
Bereinigt Rezept-Namen und generiert einheitliche Descriptions.

Kein LLM-Aufruf — rein deterministisch aus Struktur-Daten.

Einheitliches System:
  name        – sauberer Gerichtsname ohne User-Attribut, Marketing-Slogan
                oder Meal-Type-Label
  description – 1–2 Sätze: Hauptzutaten + Diät/Küche-Hinweis wenn relevant

Aufruf:
    cd backend
    .venv/Scripts/python fix_recipe_metadata.py [--dry-run]
"""

import argparse
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "aristeus.db"

# ---------------------------------------------------------------------------
# Name-Bereinigung
# ---------------------------------------------------------------------------

# Marketing-Schlagwörter nach " - " oder " – " → Suffix entfernen
_MARKETING_WORDS = re.compile(
    r"(schnell|einfach|lecker|köstlich|unwiderstehlich|sagenhaft|partyknüller|"
    r"vorzüglich|mega|super|raffiniert|beliebt|ausgezeichnet|lob|einfach gemacht|"
    r"mmhh|mmh|mhh|yummy|saftig|fluffig|knusprig und|cremig und|würzig und|"
    r"selber\s+machen|zum\s+nachkochen|zum\s+genießen|jetzt\s+entdecken|"
    r"ergibt\s+ca\.|ergibt\s+\d|für\s+\d+\s+brötchen|"
    r"hausmannskost|günstiges\s+mittagessen|perfekter\s+lunch|"
    r"kleines\s+mittagessen|blitzschnell)",
    re.IGNORECASE,
)

# Meal-Type-Wörter — wenn der Suffix nach " - " eines davon enthält, wird er entfernt
_MEAL_WORD = re.compile(
    r"\b(mittagessen|abendessen|frühstück|abendbrot|lunch|snack|"
    r"single-abendessen|abendbrot)\b",
    re.IGNORECASE,
)

# Renommierung "Single-Abendessen Nr. X - Eigentlicher Name"
_SINGLE_PREFIX = re.compile(
    r"^single-abendessen\s+nr\.\s*\d+\s*[-–]?\s*",
    re.IGNORECASE,
)

# User-Name am Anfang: "Dirks ", "Mamas ", "Peters ", "Smokeys "
# Adjektiv-Endungen auf "-es" werden NICHT gematchet: lookbehind prüft, dass der Char VOR "s"
# nicht "e" ist — so treffen wir keine Adjektive (Schwarzes, Buntes, Knuspriges …)
_POSSESSIVE_PREFIX = re.compile(r"^[A-ZÄÖÜ][a-zäöüß]{1,14}(?<![eE])s\s+(?=[A-ZÄÖÜ])")

# "K's ", "R's " — Initiale mit Apostroph
_INITIAL_POSSESSIVE = re.compile(r"^[A-ZÄÖÜ]'s\s+")

# "von Elli K.", "von LavaCHilli", "von eisbobby" am Ende
_VON_SUFFIX = re.compile(r"\s+von\s+[\w\s.]+$", re.IGNORECASE)

# Klammern mit Nutzerhinweisen wie "(von Elli K.)" oder "(Variante nach...)"
_USER_PAREN = re.compile(r"\s*\(von\s+[\w\s.]+\)", re.IGNORECASE)

# Redundanter "dafür ernte ich immer Lob!" und ähnliches in Klammern
_PRAISE_PAREN = re.compile(r"\s*[-–]\s*dafür ernte ich immer lob[!.]?", re.IGNORECASE)


def _clean_name(raw: str) -> str:
    name = raw.strip()

    # "Single-Abendessen Nr. X - Echter Name" → "Echter Name"
    if _SINGLE_PREFIX.match(name):
        name = _SINGLE_PREFIX.sub("", name).strip()

    # "von [Name]" am Ende
    name = _VON_SUFFIX.sub("", name).strip()

    # "(von Elli K.)" in Klammern
    name = _USER_PAREN.sub("", name).strip()

    # Lob-Klammern
    name = _PRAISE_PAREN.sub("", name).strip()

    # Suffix nach " - " oder " – " entfernen wenn Marketing-Slogan oder Meal-Type-Label
    for sep in [" – ", " - "]:
        if sep in name:
            parts = name.split(sep, 1)
            suffix = parts[1].strip()
            if _MARKETING_WORDS.search(suffix) or _MEAL_WORD.search(suffix):
                name = parts[0].strip()
            break

    # User-Name-Prefix (Genitiv): "Dirks Apfelkuchen" → "Apfelkuchen"
    name = _POSSESSIVE_PREFIX.sub("", name)

    # Initiale mit Apostroph: "K's Waffeln" → "Waffeln"
    name = _INITIAL_POSSESSIVE.sub("", name)

    # Überflüssige Punkte/Leerzeichen am Ende
    name = name.rstrip(".,!? ").strip()

    # Verwaiste/unpassende Klammern entfernen (z.B. aus fehlerhafte Runs generierte Namen)
    if name.count("(") != name.count(")"):
        name = name.replace("(", "").replace(")", "")
    name = name.strip()

    return name or raw.strip()


# ---------------------------------------------------------------------------
# Description-Generierung
# ---------------------------------------------------------------------------

# Mappe Kategorien auf sprechende Gerichts-Typen
_CAT_MAP = {
    "dessert": "Dessert",
    "cremes": "Cremiges Dessert",
    "frucht": "Frucht-Dessert",
    "backen": "Gebackenes",
    "kuchen": "Kuchen",
    "brot und brötchen": "Brot",
    "pasta & nudel": "Nudelgericht",
    "suppen": "Suppe",
    "eintöpfe": "Eintopf",
    "salate": "Salat",
    "gemüse": "Gemüsegericht",
    "hülsenfrüchte": "Hülsenfrücht-Gericht",
    "kartoffeln": "Kartoffelgericht",
    "reis": "Reisgericht",
    "geflügel": "Geflügelgericht",
    "rind": "Rindfleischgericht",
    "schwein": "Schweinefleischgericht",
    "lamm": "Lammgericht",
    "fisch": "Fischgericht",
    "meeresfrüchte": "Meeresfrüchte-Gericht",
    "eier": "Eiergericht",
    "aufläufe": "Auflauf",
    "auflauf": "Auflauf",
    "überbacken": "Überbackenes Gericht",
    "schmoren": "Geschmortes",
    "braten": "Gebratenes",
    "dünsten": "Gedünstetes",
    "grillen": "Gegrilltes",
    "pfannengerichte": "Pfannengericht",
    "vegetarisch": "Vegetarisches Gericht",
    "vegan": "Veganes Gericht",
    "kalorienarm": "Leichtes Gericht",
    "fettarm": "Fettarmes Gericht",
    "trennkost": "Leichtes Gericht",
    "snacks": "Snack",
    "fingerfood": "Fingerfood",
    "sandwiches": "Sandwich",
    "grundrezept": "Grundrezept",
    "saucen": "Sauce",
    "dips": "Dip",
    "marinaden": "Marinade",
}

# Mappe Küche auf Adjektiv
_CUISINE_MAP = {
    "italien": "Italienisch",
    "frankreich": "Französisch",
    "spanien": "Spanisch",
    "griechenland": "Griechisch",
    "türkei": "Türkisch",
    "asien": "Asiatisch",
    "china": "Chinesisch",
    "japan": "Japanisch",
    "thailand": "Thailändisch",
    "indien": "Indisch",
    "usa & kanada": "Amerikanisch",
    "usa": "Amerikanisch",
    "mexiko": "Mexikanisch",
    "österreich": "Österreichisch",
    "schweiz": "Schweizerisch",
    "skandinavien": "Skandinavisch",
    "russland": "Russisch",
    "mittelmeer": "Mediterran",
}


def _dish_type(category: str, meal_type: str, is_vegetarian: bool, is_vegan: bool) -> str:
    cat_key = (category or "").lower().strip()
    mapped = _CAT_MAP.get(cat_key)
    if mapped:
        return mapped
    # Fallback über meal_type
    mt = (meal_type or "").lower()
    if mt == "dessert":
        return "Dessert"
    if mt == "grundrezept":
        return "Grundrezept"
    if is_vegan:
        return "Veganes Gericht"
    if is_vegetarian:
        return "Vegetarisches Gericht"
    return "Gericht"


def _cuisine_label(cuisine: str) -> str | None:
    if not cuisine:
        return None
    key = cuisine.lower().strip()
    for part, label in _CUISINE_MAP.items():
        if part in key:
            return label
    if key in ("deutsch", "deutschland", ""):
        return None  # Deutsch ist der Standard, muss nicht erwähnt werden
    return cuisine.strip()  # Unbekannte Küche direkt übernehmen


# Ingredient-Namen die nur Einheiten oder Generika sind → rausfiltern
_UNIT_ONLY = re.compile(
    r"^(g|kg|ml|l|el|tl|pck\.?|stk\.?|stück|tasse|portion|scheibe|dose|flasche|glas|"
    r"bund|handvoll|prise|zehe|zweig|becher|etwas|nach\s+bedarf|n\.\s*b\.|salz\s+und\s+pfeffer|"
    r"wasser|salz|pfeffer|öl\s+zum\s+braten|butter\s+zum\s+braten)$",
    re.IGNORECASE,
)

# Adjektive + Größenangaben am Anfang einer Zutat entfernen
_LEADING_ADJ = re.compile(
    r"^(große?[rms]?|kleine?[rms]?|mittlere?[rms]?|m\.-?große?[rms]?|frische?[rms]?|"
    r"reife?[rms]?|sehr\s+reife?[rms]?|tiefgekühlte?[rms]?|getrocknete?[rms]?|"
    r"gehackte?[rms]?|gewürfelte?[rms]?|fein\s+gehackte?[rms]?|"
    r"dünne?[rms]?|dicke?[rms]?|zarte?[rms]?|weiche?[rms]?|süße?[rms]?)\s+",
    re.IGNORECASE,
)


def _clean_ingredient(raw: str) -> str:
    """Entfernt Mengen-Präfixe und geklammerte Hinweise aus rohem Zutaten-Namen."""
    # Mengenangaben am Anfang: "500 g Mehl" → "Mehl", "2 Pck. Vanillezucker" → "Vanillezucker"
    raw = re.sub(
        r"^\d[\d,./]*\s*(g|kg|ml|cl|dl|l|liter|el|tl|pck\.?|stk\.?|stück|tasse[n]?|"
        r"portion[en]?|scheibe[n]?|zehe[n]?|prise[n]?|prisen?|bund|handvoll|"
        r"dose[n]?|flasche[n]?|glas|gläser|becher|port\.|m\.?-?große?[rms]?|"
        r"große?[rms]?|kleine?[rms]?|mittlere?[rms]?|tropfen|zweig[e]?|blatt|"
        r"blätter|stange[n]?|kopf|köpfe|riegel|tafel|knolle[n]?)\.?\s+",
        "", raw, flags=re.IGNORECASE
    )
    # Schrägstrich-Plural vor Klammern: "Tomate(n)" → "Tomaten"
    raw = re.sub(r"\(n\)", "n", raw)
    raw = re.sub(r"\(r\)", "r", raw)
    raw = re.sub(r"\(s\)", "s", raw)
    raw = re.sub(r"\(e\)", "e", raw)
    # Geklammerte Ergänzungen entfernen — iterativ für verschachtelte Klammern
    for _ in range(3):
        raw = re.sub(r"\s*\([^()]{0,80}\)", "", raw)
    # Übrig gebliebene verwaiste Klammern entfernen
    raw = raw.replace("(", "").replace(")", "")
    # Komma-Hinweise abschneiden: "Joghurt, griechisch" → "Joghurt"
    raw = raw.split(",")[0].strip()
    # "/ " Alternativen: "Mandeln/Walnüsse" → "Mandeln"
    raw = raw.split("/")[0].strip()
    # Adjektiv am Anfang entfernen: "große Äpfel" → "Äpfel"
    raw = _LEADING_ADJ.sub("", raw).strip()
    # "Pck. Vanillezucker" ohne Zahl am Anfang: Einheiten-Präfix entfernen
    raw = re.sub(
        r"^(pck\.?|stk\.?|tl\.?|el\.?|dose[n]?\.?|flasche[n]?\.?|becher\.?|glas\.?|"
        r"bund\.?|portion[en]?\.?|port\.?|scheibe[n]?\.?|zehe[n]?\.?|prise[n]?\.?|"
        r"prisen?\.?|beutel\.?|tafel\.?|riegel\.?|liter\.?|tropfen\.?|spritzer\.?)\s+",
        "", raw, flags=re.IGNORECASE,
    )
    return raw.strip()


def _build_description(
    dish_type: str,
    ingredients: list[str],
    cuisine_label: str | None,
    is_vegetarian: bool,
    is_vegan: bool,
    is_fish: bool,
    is_meat: bool,
) -> str:
    # Zutaten bereinigen und deduplizieren
    clean_ingr = []
    seen = set()
    for raw in ingredients:
        c = _clean_ingredient(raw)
        # Reine Einheiten, zu kurze oder generische Strings rausfiltern
        if not c or len(c) <= 2 or _UNIT_ONLY.match(c):
            continue
        # Reine Zahlen oder Abkürzungen rausfiltern
        if re.match(r"^[\d.,]+$", c) or re.match(r"^[A-Z]{1,3}\.?$", c):
            continue
        if c.lower() not in seen:
            seen.add(c.lower())
            clean_ingr.append(c)

    # Satz 1: Gericht-Typ + Zutaten
    if len(clean_ingr) == 0:
        satz1 = f"{dish_type}."
    elif len(clean_ingr) == 1:
        satz1 = f"{dish_type} mit {clean_ingr[0]}."
    elif len(clean_ingr) == 2:
        satz1 = f"{dish_type} mit {clean_ingr[0]} und {clean_ingr[1]}."
    elif len(clean_ingr) == 3:
        satz1 = f"{dish_type} mit {clean_ingr[0]}, {clean_ingr[1]} und {clean_ingr[2]}."
    else:
        hauptzutaten = ", ".join(clean_ingr[:3])
        weitere = " und ".join(clean_ingr[3:5]) if len(clean_ingr) > 4 else clean_ingr[3]
        satz1 = f"{dish_type} mit {hauptzutaten}, verfeinert mit {weitere}."

    # Satz 2: Küche + Diät
    tags = []
    if cuisine_label:
        tags.append(cuisine_label)
    if is_vegan:
        tags.append("vegan")
    elif is_vegetarian:
        tags.append("vegetarisch")
    elif is_fish and not is_meat:
        tags.append("Fisch")

    satz2 = (", ".join(tags).capitalize() + ".") if tags else ""

    return (satz1 + " " + satz2).strip() if satz2 else satz1


# ---------------------------------------------------------------------------
# Haupt-Routine
# ---------------------------------------------------------------------------

def process(conn: sqlite3.Connection, dry_run: bool):
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT r.id, r.name, r.source_url, r.category, r.cuisine, r.meal_type,
               r.is_vegetarian, r.is_vegan, r.is_meat, r.is_fish,
               GROUP_CONCAT(ri.raw_name, '||') AS main_ingr
        FROM recipes r
        LEFT JOIN recipe_ingredients ri ON ri.recipe_id = r.id AND ri.is_main = 1
        GROUP BY r.id
        ORDER BY r.id
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"Rezepte: {total}")

    updates = []
    for r in rows:
        new_name = _clean_name(r["name"])
        ingr_raw = (r["main_ingr"] or "").split("||") if r["main_ingr"] else []
        dish_type = _dish_type(
            r["category"], r["meal_type"],
            bool(r["is_vegetarian"]), bool(r["is_vegan"])
        )
        cuisine_lbl = _cuisine_label(r["cuisine"])
        new_desc = _build_description(
            dish_type,
            ingr_raw,
            cuisine_lbl,
            bool(r["is_vegetarian"]),
            bool(r["is_vegan"]),
            bool(r["is_fish"]),
            bool(r["is_meat"]),
        )

        # Wenn der Name aus einer vorherigen fehlerhaften Run mit einem Einheiten-Präfix
        # beginnt (z.B. "Port. Putenbrustfilets ..."), diesen entfernen
        new_name = re.sub(
            r"^(Port\.|Pck\.|Stk\.|Prise[n]?\.|EL\.|TL\.)\s+",
            "", new_name, flags=re.IGNORECASE,
        ).strip()

        # Fallback: nur wenn der Name eindeutig kaputt ist (z.B. "Single" aus erster,
        # fehlerhafter Run) — nicht für kurze aber valide Namen wie "Baklava", "Tiramisu"
        _BAD_NAMES = {"single", "die", "der", "das", "ein", "eine", "und"}
        if new_name.lower() in _BAD_NAMES and ingr_raw:
            clean_ingr = []
            seen: set[str] = set()
            for raw_i in ingr_raw:
                c = _clean_ingredient(raw_i)
                if c and len(c) > 2 and not _UNIT_ONLY.match(c) and c.lower() not in seen:
                    seen.add(c.lower())
                    clean_ingr.append(c)
            if len(clean_ingr) >= 2:
                new_name = f"{clean_ingr[0]} mit {clean_ingr[1]}"
                if len(clean_ingr) >= 3:
                    new_name += f" und {clean_ingr[2]}"
            elif len(clean_ingr) == 1:
                new_name = f"{dish_type} mit {clean_ingr[0]}"

        updates.append((r["id"], r["name"], new_name, new_desc))

    if dry_run:
        for rid, old_name, new_name, new_desc in updates[:20]:
            print(f"\nID {rid}")
            print(f"  ALT : {old_name}")
            print(f"  NEU : {new_name}")
            print(f"  DESC: {new_desc}")
        print(f"\n... (zeige 20 von {total})")
    else:
        for rid, _, new_name, new_desc in updates:
            cur.execute(
                "UPDATE recipes SET name = ?, description = ? WHERE id = ?",
                (new_name, new_desc, rid),
            )

        # Manuelle Korrekturen: Rezepte deren Original-Name durch frühere fehlerhafte
        # Runs überschrieben wurde und nicht mehr aus den Zutaten rekonstruierbar ist.
        # Format: (id, korrekter_name) — description bleibt die generierte.
        _MANUAL_NAME_FIXES = [
            (153, "Baklava"),
        ]
        for rid, correct_name in _MANUAL_NAME_FIXES:
            cur.execute("UPDATE recipes SET name = ? WHERE id = ?", (correct_name, rid))

        conn.commit()
        print(f"Fertig: {total} Rezepte aktualisiert + {len(_MANUAL_NAME_FIXES)} manuelle Korrekturen.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    try:
        process(conn, args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
