"""German prompt templates for the AI pipeline."""


def build_suggestions_prompt(
    *,
    offers_text: str,
    profile_text: str,
    learn_text: str,
    count: int = 10,
    week_start: str,
    exclude_names: list[str] | None = None,
    wish_text: str | None = None,
) -> list[dict]:
    exclude_hint = ""
    if exclude_names:
        names = ", ".join(f'"{n}"' for n in exclude_names)
        exclude_hint = (
            f"\nDiese Gerichte wurden kürzlich vorgeschlagen oder gekocht — "
            f"schlage sie NICHT erneut vor (auch keine nahezu identischen Varianten): {names}.\n"
        )

    wish_block = ""
    if wish_text:
        wish_block = f"""

=== WÜNSCHE DES HAUSHALTS FÜR DIESE WOCHE ===
{wish_text}
Berücksichtige diese Wünsche prioritär: nimm explizit gewünschte Gerichte in die Vorschläge auf
und plane genannte vorhandene Vorräte/Zutaten mit ein, wenn welche erwähnt werden."""

    system = (
        "Du bist ein Kochassistent für deutsche Familien. "
        "Du antwortest immer auf Deutsch und gibst deine Antwort ausschließlich als gültiges JSON zurück. "
        "Nutze nur die angegebenen Angebote und das Haushaltsprofil, um passende Gerichte vorzuschlagen."
    )

    user = f"""Wochenbeginn: {week_start}

=== HAUSHALTSPROFIL ===
{profile_text}
{wish_block}

=== LERNKONTEXT (bisherige Vorlieben) ===
{learn_text or "Noch keine Vorlieben gespeichert."}

=== AKTUELLE ANGEBOTE (kochrelevant) ===
{offers_text or "Keine Angebote verfügbar."}
{exclude_hint}
Schlage {count} verschiedene Gerichte für diese Woche vor.
Nutze dabei möglichst viele der genannten Angebote als Hauptzutaten.
Beachte das Haushaltsprofil (Diät, Allergien, Kochzeit, Geschmack).
Achte auf echte Abwechslung: unterschiedliche Küchen (z.B. deutsch, italienisch,
asiatisch, orientalisch), unterschiedliche Hauptzutaten und Zubereitungsarten —
nicht mehrmals dasselbe Grundgericht in Varianten. Mische bekannte
Familienklassiker mit 2-3 kreativeren Ideen.

Gib exakt dieses JSON zurück:
{{
  "vorschlaege": [
    {{
      "name": "Gerichtname",
      "beschreibung": "Kurzbeschreibung (1-2 Sätze)",
      "hauptzutaten": ["Zutat1", "Zutat2"],
      "angebots_zutaten": [{{"name": "EXAKTER Produktname aus Angebotsliste", "laden": "Rewe"}}],
      "kochzeit_min": 30,
      "kategorie": "vegetarisch|vegan|Fisch|Fleisch|gemischt",
      "schwierigkeit": "leicht|mittel|aufwändig"
    }}
  ]
}}"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_recipe_prompt(
    *,
    dish_name: str,
    dish_description: str,
    profile_text: str,
    offers_text: str,
) -> list[dict]:
    system = (
        "Du bist ein Kochassistent. Antworte immer auf Deutsch und ausschließlich als gültiges JSON. "
        "Erstelle detaillierte, praxisnahe Rezepte für deutsche Familien."
    )

    user = f"""Erstelle ein vollständiges Rezept für: **{dish_name}**
Beschreibung: {dish_description}

=== HAUSHALTSPROFIL ===
{profile_text}

=== VERFÜGBARE ANGEBOTE (gerne verwenden) ===
{offers_text or "Keine spezifischen Angebote."}

Gib exakt dieses JSON zurück:
{{
  "zutaten": [
    {{"name": "Zutatname", "menge": 200, "einheit": "g", "ist_angebot": false, "laden": null}},
    {{"name": "EXAKTER Produktname aus Angebotsliste", "menge": 400, "einheit": "g", "ist_angebot": true, "laden": "Lidl"}}
  ],
  "schritte": [
    "Schritt 1: ...",
    "Schritt 2: ..."
  ],
  "geschaetzte_zeit_min": 30,
  "tipps": ["Tipp für Familien", "Variante"]
}}

Mengen für das angegebene Haushaltsprofil (Erwachsene + Kinder) anpassen.
WICHTIG für Angebots-Zutaten:
- "ist_angebot": true NUR wenn die Zutat aus der Angebotsliste stammt
- "name": verwende den EXAKTEN Produktnamen wie er in der Angebotsliste steht (z.B. "Gut Ponholz Hähnchen-Schenkel", nicht nur "Hähnchen")
- "laden": der Ladenname in eckigen Klammern aus der Angebotsliste (z.B. "Lidl", "Rewe", "Aldi")
Für normale Zutaten: "ist_angebot": false, "laden": null"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_recipes_batch_prompt(
    *,
    dishes: list[tuple[str, str]],  # (name, beschreibung)
    profile_text: str,
    offers_text: str,
) -> list[dict]:
    """One call, several full recipes — fewer requests than one call per dish."""
    system = (
        "Du bist ein Kochassistent. Antworte immer auf Deutsch und ausschließlich als gültiges JSON. "
        "Erstelle detaillierte, praxisnahe Rezepte für deutsche Familien."
    )

    dish_lines = "\n".join(
        f"{i + 1}. **{name}** — {desc or 'keine Beschreibung'}"
        for i, (name, desc) in enumerate(dishes)
    )

    user = f"""Erstelle vollständige Rezepte für diese {len(dishes)} Gerichte:

{dish_lines}

=== HAUSHALTSPROFIL ===
{profile_text}

=== VERFÜGBARE ANGEBOTE (gerne verwenden) ===
{offers_text or "Keine spezifischen Angebote."}

Gib exakt dieses JSON zurück (ein Eintrag pro Gericht, "gericht" EXAKT wie oben angegeben):
{{
  "rezepte": [
    {{
      "gericht": "Gerichtname exakt wie oben",
      "zutaten": [
        {{"name": "Zutatname", "menge": 200, "einheit": "g", "ist_angebot": false, "laden": null}},
        {{"name": "EXAKTER Produktname aus Angebotsliste", "menge": 400, "einheit": "g", "ist_angebot": true, "laden": "Lidl"}}
      ],
      "schritte": ["Schritt 1: ...", "Schritt 2: ..."],
      "geschaetzte_zeit_min": 30,
      "tipps": ["Tipp für Familien"]
    }}
  ]
}}

Mengen für das angegebene Haushaltsprofil (Erwachsene + Kinder) anpassen.
WICHTIG für Angebots-Zutaten:
- "ist_angebot": true NUR wenn die Zutat aus der Angebotsliste stammt
- "name": verwende den EXAKTEN Produktnamen aus der Angebotsliste
- "laden": der Ladenname in eckigen Klammern aus der Angebotsliste
Für normale Zutaten: "ist_angebot": false, "laden": null"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_feedback_summary_prompt(feedback_entries: list[dict]) -> list[dict]:
    entries_text = "\n".join(
        f"- {e['name']}: {'👍' if e.get('thumbs') == 1 else '👎' if e.get('thumbs') == -1 else '?'} "
        f"{e.get('portion_note', '')} {e.get('free_text', '')}"
        for e in feedback_entries
    )

    system = (
        "Du bist ein Kochassistent. Analysiere das Nutzerfeedback zu Gerichten "
        "und extrahiere Muster und Empfehlungen für zukünftige Vorschläge. "
        "Antworte auf Deutsch und ausschließlich als gültiges JSON."
    )

    user = f"""Analysiere dieses Nutzerfeedback zur letzten Woche:

{entries_text}

Gib exakt dieses JSON zurück:
{{
  "muster": ["Muster 1", "Muster 2"],
  "empfehlungen": ["Empfehlung 1", "Empfehlung 2"]
}}

Muster: Was hat funktioniert / nicht funktioniert?
Empfehlungen: Was sollte zukünftig mehr/weniger vorgeschlagen werden?"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_recipe_import_ingredients_prompt(*, raw_ingredients: list[str]) -> list[dict]:
    """Structure raw ingredient lines (e.g. from JSON-LD recipeIngredient) into
    the app's zutaten schema — used by POST /api/recipes/import."""
    system = (
        "Du bist ein Kochassistent. Antworte immer auf Deutsch und ausschließlich als gültiges JSON."
    )
    lines = "\n".join(f"- {r}" for r in raw_ingredients)
    user = f"""Wandle diese Zutatenzeilen aus einem Rezept in strukturierte Daten um:

{lines}

Gib exakt dieses JSON zurück:
{{
  "zutaten": [
    {{"name": "Zutatname ohne Menge", "menge": 200, "einheit": "g"}}
  ]
}}

- "menge": Zahl (z.B. 0.5, 200) oder null, wenn keine Menge angegeben ist
- "einheit": kurze Einheit (g, kg, ml, l, EL, TL, Stück, Prise, ...) oder null
- Behalte Reihenfolge und Anzahl der Zeilen exakt bei (eine Ausgabe pro Eingabezeile)."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_recipe_import_from_text_prompt(*, page_text: str, url: str) -> list[dict]:
    """Extract a full recipe from unstructured page text (no JSON-LD present —
    Instagram/Pinterest/blog posts) — used by POST /api/recipes/import."""
    system = (
        "Du bist ein Kochassistent, der Rezepte aus unstrukturiertem Webseitentext extrahiert. "
        "Antworte immer auf Deutsch und ausschließlich als gültiges JSON."
    )
    user = f"""Der folgende Text stammt von der Webseite {url}. Prüfe, ob er ein Kochrezept enthält
(z.B. ein Instagram-Post, Pinterest-Pin oder Blogartikel mit Zutaten und Zubereitung).

=== SEITENTEXT ===
{page_text}

Wenn KEIN Rezept erkennbar ist (z.B. weil es nur Werbung, ein Profil oder unzusammenhängender Text ist),
gib zurück: {{"erkannt": false}}

Wenn ein Rezept erkennbar ist, gib exakt dieses JSON zurück:
{{
  "erkannt": true,
  "name": "Gerichtname",
  "kategorie": "vegetarisch|vegan|Fisch|Fleisch|gemischt",
  "zutaten": [
    {{"name": "Zutatname", "menge": 200, "einheit": "g"}}
  ],
  "schritte": ["Schritt 1: ...", "Schritt 2: ..."],
  "geschaetzte_zeit_min": 30,
  "tipps": ["Tipp"]
}}

Extrahiere nur, was im Text tatsächlich steht — erfinde keine Zutaten oder Schritte."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_recipe_photo_prompt(*, image_data_urls: list[str]) -> list[dict]:
    """Extract a full recipe from one or more photos (cookbook page, social-media
    screenshot series, handwritten note) — used by POST /api/recipes/import-photo.
    Mirrors build_recipe_import_from_text_prompt's erkannt/nicht-erkannt contract
    (same ImportedRecipeResponse schema) so the router can reuse that parsing path."""
    system = (
        "Du bist ein Kochassistent, der Rezepte von Fotos abliest — Kochbuchseiten, "
        "Screenshots von Social-Media-Posts oder handschriftliche Notizzettel. "
        "Antworte immer auf Deutsch und ausschließlich als gültiges JSON."
    )
    n = len(image_data_urls)
    photo_note = (
        "Das folgende Foto zeigt" if n == 1
        else f"Die folgenden {n} Fotos zeigen (zusammengehörig, z.B. Zutatenliste + Zubereitung getrennt)"
    )
    user_text = f"""{photo_note} vermutlich ein Kochrezept. Lies den Text (auch handschriftliche
Notizen) sorgfältig, auch wenn die Bildqualität nicht perfekt ist.

Wenn KEIN Rezept erkennbar ist (z.B. Urlaubsfoto, Produktfoto ohne Zutaten/Zubereitung,
unleserlicher Text), gib zurück: {{"erkannt": false}}

Wenn ein Rezept erkennbar ist, gib exakt dieses JSON zurück:
{{
  "erkannt": true,
  "name": "Gerichtname",
  "kategorie": "vegetarisch|vegan|Fisch|Fleisch|gemischt",
  "zutaten": [
    {{"name": "Zutatname", "menge": 200, "einheit": "g"}}
  ],
  "schritte": ["Schritt 1: ...", "Schritt 2: ..."],
  "geschaetzte_zeit_min": 30,
  "tipps": ["Tipp"]
}}

Extrahiere nur, was auf den Fotos tatsächlich zu erkennen ist — erfinde keine Zutaten oder Schritte.
Wenn mehrere Fotos gegeben sind, führe die Informationen zu einem einzigen Rezept zusammen
(z.B. Zutatenliste von Foto 1 + Zubereitungsschritte von Foto 2)."""

    content: list[dict] = [{"type": "text", "text": user_text}]
    for url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]


def format_profile(profile, portion_override: int | None = None) -> str:
    """Format a Profile ORM object as a readable string for prompts.

    portion_override: when set (a household's "Gäste-Modus" for this one
    week), the normal household headcount line is replaced with an explicit
    instruction to cook for that many people this week instead.
    """
    import json
    allergies = json.loads(profile.allergies_json or "[]")
    no_gos = json.loads(profile.no_gos_json or "[]")
    cuisines = json.loads(profile.preferred_cuisines_json or "[]")
    meats = json.loads(profile.allowed_meats_json or "[]")

    if portion_override:
        household_line = (
            f"Haushalt: DIESE WOCHE für {portion_override} Personen kochen "
            f"(Gäste/abweichende Personenzahl)!"
        )
    else:
        household_line = f"Haushalt: {profile.adults} Erwachsene, {profile.kids} Kinder"

    parts = [
        household_line,
        f"Diät: {profile.diet}",
        f"Erlaubte Fleischsorten: {', '.join(meats) if meats else 'keine'}",
        f"Max. Kochzeit: {profile.max_cook_time_min} Minuten",
    ]
    if allergies:
        parts.append(f"Allergien: {', '.join(allergies)}")
    if no_gos:
        parts.append(f"No-Gos: {', '.join(no_gos)}")
    if cuisines:
        parts.append(f"Bevorzugte Küchen: {', '.join(cuisines)}")
    return "\n".join(parts)


def format_offers(offers: list) -> str:
    """Format a list of Offer ORM objects as a readable string for prompts."""
    if not offers:
        return "Keine Angebote."
    lines = []
    # Deliberately uncapped: every cooking-relevant offer of every selected
    # store goes into the prompt (~290 offers ≈ 4-5k tokens — fine for the
    # whole model chain, and offer coverage is the core promise of the app).
    for o in offers:
        price = f" — {o.price_text}" if o.price_text else ""
        date_hint = f" (ab {o.live_from_date})" if o.live_from_date else ""
        store = o.store.capitalize() if o.store else ""
        lines.append(f"• {o.product_name}{price}{date_hint} [{store}]")
    return "\n".join(lines)
