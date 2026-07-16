# Aristeus Kochapp — Projekt-Kontext für Claude Code

Browser-basierte PWA-Familien-Kochapp. Liest Kaufda-Angebote, schlägt Gerichte vor, generiert Rezepte + Einkaufsliste, lernt aus Feedback. Vollständiger Implementierungsplan in [PLAN.md](PLAN.md).

## Phasenstand

| Phase | Status | Inhalt |
|---|---|---|
| 0 | ✅ fertig | Repo-Struktur, Hello-World, Alembic, Caddy/systemd-Templates |
| 1 | ✅ fertig | Auth (bcrypt, HTTP-only Sessions), Passwort-Reset, Onboarding, Profil, Admin |
| 2 | ✅ fertig | Kaufda-Scraper, nightly Refresh, Freshness-Endpoint, Store-Discovery |
| 3 | ✅ fertig | AI-Harness: OpenRouter-Client, Prompts (DE), Pipeline, Plan-Endpoints, Frontend-Flow |
| 4 | ✅ fertig | Wochenplan-Flow (Feedback pro Gericht, Historie, Sternchen-Favoriten) |
| 5 | ✅ fertig | Wochenfeedback + Lern-Aggregation (`learned_preferences`) |
| 6 | ✅ fertig | PWA-Politur (Manifest, Service Worker, Offline-Liste, Teilen-Button) |
| 7 | ✅ fertig | Admin-Übersicht + DSGVO (Export, Löschen) |

## Stack

- **Backend:** FastAPI 0.136, SQLAlchemy 2.0, SQLite WAL, APScheduler, Alembic
- **Frontend:** React 18, Vite 5, TypeScript, Tailwind CSS, React Router v6
- **LLM:** OpenRouter, Modell-Chain (Stand 2026-07-14): `qwen3-next-80b-a3b-instruct:free` → `gemma-4-31b-it:free` → `llama-3.3-70b-instruct:free` → `nemotron-3-super-120b-a12b:free`. Fast-Failover: bei 429/Parse-Fehler sofort nächstes Modell; erst nach kompletter erfolgloser Runde 35s warten + zweite Runde. Free-Slugs sterben regelmäßig (gpt-oss-120b:free und gemini-2.0-flash-exp:free gaben 404) → bei 404-Fehlern zuerst `curl https://openrouter.ai/api/v1/models` gegen die Chain prüfen
- **Rezeptquelle:** AI-Vorschläge sind der Primärpfad. Der Chefkoch-Katalog (`recipe_matcher.py`, `chefkoch_scraper.py`) ist **deaktiviert** (`USE_RECIPE_CATALOG=false`, Default) — Code bleibt hinter dem Flag erhalten
- **AI-Ablauf (seit 2026-07-14):** Rezepte werden gebündelt generiert (4 Gerichte pro LLM-Call, `recipe_batch`); Confirm läuft asynchron (Status `confirming`, Frontend pollt) und ist idempotent. Scheduler: Kaufda-Refresh Sa+So 03:00, **Vorgenerierung So 04:00** (pro Haushalt: Plan für kommende Woche + 30 Vorschläge à 3×10 Calls + alle Rezepte in `dish.recipe_json`) → Plan-Erstellung und Confirm brauchen dann 0 LLM-Calls. Feedback-Aggregation Mo 04:00, **Healthcheck Mo 07:00** (prüft, ob jeder Haushalt einen Plan für die Woche hat). `POST /api/plans` gibt einen existierenden pending/suggestions_ready-Plan derselben Woche zurück statt einen neuen anzulegen. `max_tokens` großzügig setzen — Reasoning-Modelle (Nemotron) verbrauchen 1000+ Tokens vor dem JSON, zu knappe Limits truncaten das JSON
- **Monitoring:** Fehler bei Plan-/Rezept-Generierung + Healthcheck-Befunde gehen als Vorfall an das Status-Dashboard (`STATUS_WEBHOOK_URL`, Kuma-Webhook-Format, s. `backend/app/services/status_webhook.py`; Produktion: `http://192.168.50.62:8080/api/kuma-webhook`) → Eintrag in „Letzte Vorfälle" auf status.tr4jon.com + Web-Push
- **Optionale Env-Vars:** `OPENROUTER_PAID_MODELS` (bezahlte Modelle ans Ende der Free-Chain), `PEXELS_API_KEY` (Gerichtsfotos, ohne Key Emoji-Platzhalter), `STATUS_WEBHOOK_URL` — alle leer = Feature aus, kein Fehler
- **Deployment:** Homeserver docker-vm (192.168.50.61), Stack `/opt/stacks/aristeus`, Auto-Deploy GitHub Actions → GHCR → Watchtower (≤5 min). Migrationen laufen automatisch beim Container-Start (`alembic upgrade head` im Dockerfile-CMD). Env-Änderungen: `aristeus.env` auf dem Server + `docker compose up -d`
- **Versionierung (PFLICHT seit v2.0.0):** Jedes Update (Feature wie Bugfix) bumpt die Version — Semver in `frontend/src/version.ts` (`APP_VERSION`, wird auf Login + Home angezeigt) **und** `frontend/package.json` synchron halten, Version in die Commit-Message, Releases als Git-Tag (`vX.Y.Z`)

## Lokal starten

```bash
# Backend
cd backend
.venv\Scripts\uvicorn app.main:app --reload --port 8000

# Frontend (neues Terminal)
cd frontend
npm run dev
```

Erfordert `backend/.env` mit `OPENROUTER_API_KEY` (siehe `backend/.env.example`).

## Wichtige Dateien

| Datei | Zweck |
|---|---|
| `backend/app/models.py` | Alle SQLAlchemy-Modelle (Household, Profile, Brochure, Offer, WeeklyPlan, PlanDish, ShoppingItem, ...) |
| `backend/app/ai/pipeline.py` | 8-Stufen-Harness: Angebots-Filter → Lernkontext → LLM-Vorschläge → Validierung → Rezepte → Einkaufsliste |
| `backend/app/ai/client.py` | OpenRouter-Client mit Retry + Modell-Fallback-Chain |
| `backend/app/services/kaufda.py` | Kaufda-Scraper (shelf-page + location-cookie + Bonial content-API) |
| `backend/app/routers/plans.py` | Plan-Lifecycle: erstellen, Vorschläge, bestätigen, Feedback, Einkaufsliste |
| `frontend/src/pages/Plan.tsx` | Haupt-Plan-Seite (status-gesteuert: pending → suggestions → confirmed/Rezepte+Einkauf) |

## Kaufda-API (kritisches Wissen)

Die offizielle `api.kaufda.de` gibt 404 — wir nutzen einen anderen Ansatz:

1. PLZ-Koordinaten: `api.zippopotam.us/DE/{plz}`
2. Shelf-Page: `GET https://seopages.kaufda.de/shelf?postalCode={plz}` mit Cookie `location={JSON_url_encoded}`
3. `__NEXT_DATA__` parsen → Pfad: `props.pageProps.pageInformation.shelfContents.contents[]`
4. Content-API: `GET https://content-viewer-be.kaufda.de/v1/brochures/{contentId}/pages?lat=&lng=` + Header `Bonial-Api-Consumer: web-content-viewer-fe`

Details in `backend/app/services/kaufda.py` und Memory-Datei `project_kaufda_api.md`.

## DB-Migrationen

```bash
cd backend
.venv\Scripts\alembic upgrade head
```

Letzte Migration: `c4d5e6f7a8b9` (saved_recipes.origin + Backfill gekochter Rezepte; davor `b3c4d5e6f7a8` saved_recipes, `a2b3c4d5e6f7` image_url/portion_override, `f6a7b8c9d0e1` wish_text). Migrationen laufen im Deployment automatisch beim Container-Start.

## Keyword-Filter (`backend/app/services/keyword_filter.py`)

### Architektur

`is_cooking_relevant(product_name, quantity_text)` klassifiziert Angebote beim Scrapen.
Das Flag `Offer.is_cooking_relevant` wird einmalig beim Scrapen gesetzt und in der DB gespeichert.
Nach Filter-Änderungen muss die DB manuell reklassifiziert werden:

```bash
cd backend
.venv\Scripts\python reclassify_offers.py  # Skript bei Bedarf neu anlegen (s.u.)
```

### Matching-Logik (Stand 2026-05-29)

| Kategorie | Regel |
|---|---|
| Exclusion, len ≤ 4 | nur Word-Boundary (`bier`→`Bierwurst`, `tee`→`Teewurst`) |
| Exclusion, len > 4 | auch Substring (`chips`→`Crunchips`, `kaffee`→`Röstkaffee`) |
| `_EXCL_BOUNDARY_ONLY` | bilateral Word-Boundary erzwungen, egal wie lang (`"reise"` schützt `"Reisessig"`) |
| Positiv, len ≤ 4 | nur Word-Boundary (`reis`→`Reise/Kreis`, `salz`→`Salzburg`) |
| Positiv, len > 4 | auch Substring (`schwein`→`Schweinehalssteaks`) |
| `_POS_COMPOUND_ALLOW` | Substring auch für len=4: `käse`, `mais`, `brot`, `kalb` |

### Bekannte Restprobleme (nicht perfekt)

**Akzeptierte False Positives** (LLM ignoriert sie im Kontext):
- Getränke mit echten Zutaten im Namen: `Active O2 Apfel Kiwi`, `Almdudler` (wegen `kräuter`)
- Dekoriative Blumen-/Pflanzenprodukte wenn Name echte Zutat enthält: `Bunter Maistauß`
- `Nivea Creme` (wegen `creme`-Keyword) — `zahnpasta`/`zahncreme` greift für explizite Zahncreme

**Akzeptierte False Negatives:**
- Branded Käse ohne `käse` im Namen und ohne Beschreibung: `Parmigiano Reggiano DOP` → `parmigiano` Keyword ergänzt, aber weitere exotische Käsemarken möglich
- `VITASIA Reisteigplatten` (Reisesnudeln) — `reis` ist word-boundary only, kein anderes Keyword greift
- Produkte mit deutschen Namen ohne die hinterlegten Keywords (z.B. `Riesenfrikadelle`)

### Typische Debugging-Muster

Wenn ein Produkt falsch klassifiziert wird, prüfen:

```python
# In backend/ ausführen:
import sys; sys.path.insert(0, ".")
from app.services.keyword_filter import (
    _EXCLUSION_KEYWORDS, _FOOD_POSITIVE, _EXCL_BOUNDARY_ONLY_MAX,
    _POS_BOUNDARY_ONLY_MAX, _POS_COMPOUND_ALLOW, _EXCL_BOUNDARY_ONLY,
    _normalize, _word_boundary_match,
)

combined = _normalize("Produktname") + " " + _normalize("Quantity Text")
# Dann manuell prüfen welche Keywords matchen
```

Reklassifizierungs-Script (bei Bedarf neu anlegen als `backend/reclassify_offers.py`):

```python
import sqlite3, sys
sys.path.insert(0, ".")
from app.services.keyword_filter import is_cooking_relevant

conn = sqlite3.connect("data/aristeus.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT id, product_name, quantity_text, is_cooking_relevant FROM offers")
added, removed = [], []
for row in cur.fetchall():
    new_val = is_cooking_relevant(row["product_name"], row["quantity_text"])
    if new_val != bool(row["is_cooking_relevant"]):
        cur.execute("UPDATE offers SET is_cooking_relevant = ? WHERE id = ?",
                    (1 if new_val else 0, row["id"]))
        (added if new_val else removed).append(row["product_name"])
conn.commit()
print(f"+{len(added)} kochrelevant, -{len(removed)} entfernt")
```

### Nächste Verbesserungsideen

- **Kategorie-basierter Pre-Filter:** Der Scraper schreibt `Offer.category` aus der Kaufda-API (z.B. "Tiernahrung", "Molkerei"). `is_cooking_relevant` könnte diese Kategorie als dritten Parameter entgegennehmen und vor dem Keyword-Check auswerten — deutlich zuverlässiger als Keywords.
- **LLM-basierte Nachklassifizierung:** Zweideutige Produkte (weder klar food noch klar non-food) könnten per Batch-Aufruf vom LLM nachbewertet werden.
- **Umlaut-Normalisierung:** `_normalize()` konvertiert keine Akzente (é, è, î etc.). Französische Produktnamen wie `Crème fraîche` matchen deshalb nur über das explizit ergänzte `"fraîche"`-Keyword.

## Feature-Welle 2026-07-16 (nach Phase 7)

Alle Phasen fertig; darauf aufbauend kam eine große Alltags-/Robustheits-Welle:

- **Plan-Lifecycle:** Pläne vergangener Wochen werden beim Lesen automatisch `complete`; `GET /api/plans/feedback-pending` liefert den jüngsten complete-Plan mit unbewertetem Gericht (treibt die Feedback-Karte auf Home → Seite `/plan/:id/feedback`)
- **Plan-Steuerung:** `wish_text` (Freitext-Wünsche/Vorräte, fließt in den Suggestions-Prompt) und `portion_override` (2–20 Personen, Gäste-Modus) bei `POST /api/plans`; `POST .../dishes/{id}/swap` tauscht ein bestätigtes Gericht (Status kurz `confirming`, Einkaufsliste wird unter Erhalt von Häkchen + eigenen Items neu gebaut)
- **Einkaufsliste:** eigene Items (`POST/DELETE .../shopping`), 10s-Polling-Sync zwischen Geräten, einheitengerechte Mengen-Rundung (`_round_quantity`), `savings`-Block im Plan (`offers_used`, `offer_total`)
- **UI:** „Heute"-Karte + Wochenkalender, Kochmodus (Wake-Lock, Schritt-für-Schritt), Kochbuch-Seite `/cookbook` (`GET /api/recipes`, dedupe per Name, Suche + Favoriten), Gerichtsbilder via Pexels (`dish_images.py`) mit Emoji-Platzhalter (`DishImage.tsx`); geteilte Frontend-Typen in `frontend/src/types.ts`
- **Robustheit:** `more-suggestions` asynchron (Frontend pollt Dish-Anzahl), echte LLM-Kosten in `api_calls.cost_estimate` (OpenRouter `usage.include`), Incident-Reporting ans Status-Dashboard, pytest-Suite in `backend/tests/`

Bewusst offen gelassen: Web-Push-Benachrichtigungen („Morgen: X — Fleisch auftauen"), Kategorie-basierter Offer-Pre-Filter, LLM-Nachklassifizierung zweideutiger Angebote (s. Keyword-Filter-Abschnitt).

## v2.1/v2.2 (2026-07-16, nach Live-Test)

- **Angebote im Prompt uncapped:** `format_offers` schneidet nicht mehr bei 80 ab — ALLE kochrelevanten Angebote aller gewählten Läden gehen ins LLM; `_get_active_offers` verzahnt die Läden Round-Robin (sonst verdrängt Rewe mit 145 Angeboten Lidl/Aldi aus dem Aufmerksamkeits-Anfang)
- **Kochbuch = `saved_recipes` (dauerhaft):** einzige Quelle für `GET /api/recipes` (`origin` "gekocht"|"eigene"). `archive_recipes_to_cookbook(plan, db)` upsertet bestätigte Rezepte (dedupe per Haushalt+lowercase-Name) — aufgerufen nach Confirm/Swap/Regenerate/Einplanen. Plan-Löschen berührt das Kochbuch nicht; jeder Eintrag einzeln löschbar. Eigene Rezepte: `POST /api/recipes/import` (URL: JSON-LD → LLM-Fallback, SSRF-Guard) + `POST /api/recipes/manual`; Einplanen via `POST /api/recipes/plan-into-week` (current|next, baut Einkaufsliste unter Erhalt von Häkchen/Custom-Items neu, `build_shopping_list` matcht ALLE Zutaten gegen aktive Angebote)
- **Rezept-Nachgenerierung:** `POST .../dishes/{id}/regenerate-recipe` für bestätigte Gerichte ohne recipe_json (Free-Tier-429-Reparatur, Button „Rezept jetzt generieren"); Teilausfälle beim Confirm melden sich als Vorfall
- **Ersparnis:** `savings.estimated_savings` schätzt echte Ersparnis aus „statt X"/UVP/Prozent in Offer.hint/price_text (`estimate_item_savings` in plans.py) — nie erfinden, Fallback auf „N Zutaten im Angebot"
- **UI:** Einkaufs-Tab `/shopping` (Wochen-Auswahl, geteilte `components/ShoppingView.tsx`), Heute-Karte deep-linkt `/plan/{id}?dish={dishId}`, „Gericht tauschen" aus der UI entfernt (Backend-Endpoint bleibt), Kochmodus-Button im `zutatenAction`-Slot von RecipeDetails
- **Design „Honig & Olive":** CSS-Variablen-Tokens in `frontend/src/index.css` (surface/card/ink/muted/line/olive/honey als RGB-Triplets), Dark Mode via `prefers-color-scheme` (`darkMode: 'media'`, kein Klassen-Toggle mehr), Fraunces (`@fontsource-variable/fraunces`, lokal) als `font-display` für Titel/Gerichtsnamen, `components/Laurel.tsx`. REGEL: Honig-Gold exklusiv für Angebote/Ersparnis/Favoriten-Sterne, Olivgrün für Primäraktionen, keine `stone-`/`emerald-`-Klassen mehr in src/
