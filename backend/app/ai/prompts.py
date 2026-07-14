"""German prompt templates for the AI pipeline."""


def build_suggestions_prompt(
    *,
    offers_text: str,
    profile_text: str,
    learn_text: str,
    count: int = 10,
    week_start: str,
    exclude_names: list[str] | None = None,
) -> list[dict]:
    exclude_hint = ""
    if exclude_names:
        names = ", ".join(f'"{n}"' for n in exclude_names)
        exclude_hint = (
            f"\nDiese Gerichte wurden kürzlich vorgeschlagen oder gekocht — "
            f"schlage sie NICHT erneut vor (auch keine nahezu identischen Varianten): {names}.\n"
        )

    system = (
        "Du bist ein Kochassistent für deutsche Familien. "
        "Du antwortest immer auf Deutsch und gibst deine Antwort ausschließlich als gültiges JSON zurück. "
        "Nutze nur die angegebenen Angebote und das Haushaltsprofil, um passende Gerichte vorzuschlagen."
    )

    user = f"""Wochenbeginn: {week_start}

=== HAUSHALTSPROFIL ===
{profile_text}

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


def format_profile(profile) -> str:
    """Format a Profile ORM object as a readable string for prompts."""
    import json
    allergies = json.loads(profile.allergies_json or "[]")
    no_gos = json.loads(profile.no_gos_json or "[]")
    cuisines = json.loads(profile.preferred_cuisines_json or "[]")
    meats = json.loads(profile.allowed_meats_json or "[]")

    parts = [
        f"Haushalt: {profile.adults} Erwachsene, {profile.kids} Kinder",
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
    for o in offers[:80]:  # cap at 80 to stay within context
        price = f" — {o.price_text}" if o.price_text else ""
        date_hint = f" (ab {o.live_from_date})" if o.live_from_date else ""
        store = o.store.capitalize() if o.store else ""
        lines.append(f"• {o.product_name}{price}{date_hint} [{store}]")
    return "\n".join(lines)
