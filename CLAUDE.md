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
- **LLM:** OpenRouter, Modell-Chain: `gpt-oss-120b:free` → `llama-3.3-70b:free` → `gemini-2.0-flash:free`
- **Deployment:** VPS, Caddy Reverse Proxy, systemd

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

Letzte Migration: `a1b2c3d4e5f6` (Phase 3 — weekly_plans, plan_dishes, shopping_items, learned_preferences, api_calls)

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

## Was Phase 4 braucht (nächster Start)

- **Frontend:** Feedback-Flow nach dem Essen (Daumen ↑/↓, Portion, Freitext) ist im Backend (`PATCH /api/plans/{id}/dishes/{dish_id}/feedback`) bereits implementiert, aber noch nicht als dedizierte UI-Seite vorhanden
- **Frontend:** Plan-Historie-Seite (`GET /api/plans` → Liste vergangener Wochen)
- **Frontend:** Sternchen-Favoriten (bereits im Modell `is_favorite`)
- **Backend:** Feedback → `learned_preferences` Aggregation auslösen (Step 8 der Pipeline)
- **Backend:** Scheduler-Job der wöchentlich `update_from_feedback()` aufruft
