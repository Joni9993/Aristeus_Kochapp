# Aristeus Kochapp — Implementierungsplan

Browser-basierte (PWA) Familien-Kochapp: liest regionale Kaufda-Angebote, schlägt kontextbewusste Gerichte vor, generiert Rezepte und Einkaufsliste, lernt aus Nutzer-Feedback.

Nachfolger des cron-basierten Telegram/OneNote-Workflows aus [Idee.md](Idee.md), umgebaut für Mehrnutzer-Zugriff durch Familie und Freunde.

---

## 1. Produktentscheidungen (abgestimmt)

| Bereich | Entscheidung |
|---|---|
| Nutzer | Eigene Accounts pro Haushalt (Username + Passwort, bcrypt) |
| Registrierung | Nur per Einladungs-Token (Admin generiert) |
| Haushaltsprofil | Erwachsene, Kinder, Diät, Allergien, erlaubte Fleischsorten, max. Kochzeit, bevorzugte Küchen, No-Gos, Budget-Sensitivität |
| Adresse / Stores | PLZ einmalig, dann Auswahl aus vorgegebener Laden-Liste (Aldi, Rewe, Lidl, Edeka, Penny, Netto, Kaufland), spätere Änderung möglich |
| Angebots-Quelle | Kaufda-API (`/v1/brochures/<id>/pages`), wie im alten Skript |
| Angebots-Aktualität | Nightly Refresh pro PLZ, Freshness-Badges pro Store, manueller Refresh möglich |
| Onboarding-Frage | „Nur Mo.-gültige Angebote oder alle?" — beeinflusst Filterlogik |
| Trigger | Rein on-demand: Nutzer drückt „Neue Woche planen" |
| Gerichtsvorschläge | Initial 10 Karten, „5 weitere zeigen" bis max. 30 |
| Auswahl | Frei (kein fester Wochengericht-Count), Nutzer weist Tage manuell zu |
| Rezept-Output | Alles auf einen Schlag nach Auswahl: Rezepte + Einkaufsliste + Wochenübersicht |
| Einkaufsliste | Mobile-optimiert, abhakbar, „hab ich zuhause"-Häkchen, sortiert nach Gültigkeitstag → Laden → Warengruppe, Teilen-Button (Web Share API) |
| Historie | Alte Pläne dauerhaft speichern; Rezepte mit Sternchen markierbar → sanfter Re-Vorschlag-Boost (alle 3–4 Wochen, nicht ständig) |
| Feedback-Loop | Wochenende: pro Gericht Daumen ↑/↓, Portion zu viel/wenig, Freitext → persistent gespeichert und in zukünftige Vorschläge eingearbeitet |
| Haushaltsteilung | Ein Account pro Familie (geteilt); abgehakte Items synchronisiert über Geräte |
| LLM | OpenRouter Free Tier, modellunabhängig (Default: `google/gemini-2.0-flash-exp:free`, Fallback `meta-llama/llama-3.3-70b-instruct:free`) |
| Harness | Mehrstufige Pipeline mit JSON-Schema-Validierung, deterministische Schritte ohne LLM wo möglich |
| Admin | Übersicht aller Nutzer + gesetzte Präferenzen + API-Token-Verbrauch |
| DSGVO | Datenschutzhinweis bei Registrierung, Datenexport (JSON), Account-Löschen, bcrypt-Passwörter, HTTPS |
| Sprache (MVP) | Deutsch |

---

## 2. Architektur

```
Browser (PWA)
  React + Vite + Tailwind + React Router
  installierbar auf Smartphone-Homescreen
        │
        │ HTTPS (Cookie-Session)
        ▼
Caddy (Reverse Proxy, Auto-HTTPS via Let's Encrypt)
        │
        ▼
FastAPI Backend (Python 3.11, Uvicorn)
  ├─ Auth / Profil / Pläne / Feedback Router
  ├─ Kaufda-Scraper (Port des alten Skripts)
  ├─ AI-Harness (Pipeline 1–8) → OpenRouter
  ├─ APScheduler (nightly Refresh)
  └─ E-Mail-Versand (SMTP)
        │
        ▼
SQLite (WAL-Mode)
```

Komponenten alle auf einem VPS. Inferenz extern via OpenRouter.

---

## 3. Datenmodell (SQLite)

```sql
-- Haushalte / Accounts
households(id, username UNIQUE, email UNIQUE, password_hash,
           created_at, last_login_at, is_admin)

-- Profil pro Haushalt (1:1)
profiles(household_id PK, adults, kids, diet, allergies_json,
         allowed_meats_json, max_cook_time_min, preferred_cuisines_json,
         no_gos_json, budget_sensitivity, postal_code,
         selected_stores_json, monday_only_offers, updated_at)

-- Prospekte / Angebote (geteilt nach PLZ)
brochures(id, store, postal_code, brochure_id_kaufda,
          valid_from, valid_to, fetched_at, status)
offers(id, brochure_id FK, product_name, price_text, quantity_text,
       base_price, hint, store, live_from_date,
       category, is_cooking_relevant, page_no)

-- Wochenpläne
weekly_plans(id, household_id, week_start_date, created_at, status)
plan_dishes(id, plan_id FK, name, description, cuisine, cook_time_min,
            cook_day, recipe_json, used_offer_ids_json,
            is_favorite, feedback_thumbs,
            feedback_portion_note, feedback_free_text)
shopping_items(id, plan_id FK, ingredient, quantity, unit, store,
               live_from_date, offer_id FK NULL,
               is_checked, is_already_have)

-- Lernhinweise (aggregiert aus Feedback)
learned_preferences(household_id PK, loved_dishes_json,
                    disliked_dishes_json, portion_adjustments_json,
                    recurring_notes, updated_at)

-- Auth
sessions(id, household_id, expires_at, created_at, user_agent)
password_resets(token, household_id, expires_at, used)
invite_tokens(token, created_by, used_by, used_at, created_at)

-- Beobachtung
api_calls(id, household_id, model, input_tokens, output_tokens,
          cost_estimate, created_at)
```

---

## 4. Backend-Module (FastAPI)

```
backend/
  app/
    main.py                   # FastAPI-App, Router-Registrierung, CORS
    config.py                 # pydantic-settings (.env)
    db.py                     # SQLAlchemy-Engine + Session
    models.py                 # SQLAlchemy 2.0-Modelle
    schemas.py                # Pydantic I/O-Schemas
    security.py               # bcrypt, Cookie-Sessions, get_current_household
    routers/
      auth.py                 # register / login / logout / password-reset
      profile.py              # GET/PUT /me + /profile, /onboarding
      plans.py                # neue Woche, History, Detail
      suggestions.py          # +5 weitere Vorschläge
      feedback.py             # Daumen / Portion / Freitext
      shopping.py             # abhaken, Export-Text
      stores.py               # Läden + Freshness für PLZ
      admin.py                # Nutzer-Übersicht
      gdpr.py                 # Export + Account-Löschen
    services/
      kaufda.py               # Kaufda-Scraper, PLZ → Prospekt-Discovery
      keyword_filter.py       # kochrelevant / Non-Food-Klassifizierung
      scheduler.py            # APScheduler-Jobs (nightly Refresh)
      email.py                # SMTP-Versand
    ai/
      client.py               # OpenRouter-Client (httpx + Retry + Fallback)
      schemas.py              # Pydantic-Schemas für LLM-Output
      prompts.py              # Prompt-Templates (deutsch)
      pipeline.py             # 8-stufiger Harness
      validators.py           # deterministische Pre-/Post-Checks
      learned_prefs.py        # Feedback → Prompt-Kontext
  alembic/                    # Migrationen
  pyproject.toml
  .env.example
```

---

## 5. AI-Harness (Pipeline)

Strukturiert, weil Free-Tier-Modelle weniger zuverlässig sind als Top-Modelle.

| Schritt | Was | LLM? |
|---|---|---|
| 1 | Angebote vorbereiten: Filter `is_cooking_relevant`, ggf. `monday_only` | nein |
| 2 | Lernkontext bauen: top-3 geliebt, top-3 abgelehnt, Notizen, Sternchen-Cooldown | nein |
| 3 | Gerichtsvorschläge generieren (initial 10, +5 weitere bis 30) | **ja** — JSON-Schema, max. 2 Retries |
| 4 | Validator: Diät/Allergie/Kochzeit/Starttag-Logik, Dubletten | nein |
| 5 | Nutzer wählt aus + weist Tage zu | UI |
| 6 | Rezepte generieren (parallel, ein Call pro Gericht) | **ja** — JSON-Schema |
| 7 | Einkaufsliste aggregieren: Mengen summieren, gegen Angebote matchen, sortieren | nein |
| 8 | Wochenfeedback aggregieren (Mini-LLM-Call extrahiert Muster aus Freitexten) | **ja** — wöchentlich |

JSON-Schemas:

```json
// Schritt 3 — Vorschläge
{
  "vorschlaege": [{
    "name": "Linsen-Bolognese mit Spinat",
    "beschreibung": "Vegetarische Bolognese aus roten Linsen, mit Spinat und Tomate.",
    "hauptzutaten": ["Linsen","Spinat","Tomate","Pasta"],
    "angebots_zutaten": [{"name":"Spinat","laden":"Rewe","ab_tag":"Mi. 28.5."}],
    "kochzeit_min": 30,
    "kategorie": "vegetarisch",
    "schwierigkeit": "leicht"
  }]
}

// Schritt 6 — Rezept
{
  "zutaten": [{"name":"Rote Linsen","menge":250,"einheit":"g","ist_angebot":false}],
  "schritte": ["Linsen abspülen.","Zwiebel anschwitzen.","..."],
  "geschätzte_zeit_min": 30,
  "tipps": ["Kinder mögen es milder — Chili weglassen."]
}
```

---

## 6. Frontend (React PWA)

```
frontend/src/
  pages/
    Login / Register / Onboarding (6 Schritte)
    Home              # "Diese Woche" oder "Neue Woche planen"
    Plan/
      NewPlan         # Freshness + Start-Button
      Suggestions     # 10er-Raster, "5 weitere"
      AssignDays      # Tag-Zuweisung
      Recipes         # Akkordeon
      Shopping        # Mobile, Checkboxen
    History / Recipe / Feedback / Profile / Settings
    Admin/Overview
  components/         # DishCard, OfferBadge, FreshnessBadge, ShoppingItem, ...
  pwa/                # manifest.json, service-worker.ts
```

Mobile-First, PWA installierbar, Service Worker cached Wochenseite + Einkaufsliste offline.

---

## 7. Externe Integrationen

- **Kaufda** — bestehender Scraper portiert; nightly Refresh via APScheduler; konservatives Rate-Limit (1 req/s); PLZ-basierte Prospekt-Discovery pro Store
- **OpenRouter** — `https://openrouter.ai/api/v1/chat/completions`, JSON-Mode, Retry mit Backoff, Fallback-Modell, Token-Logging
- **E-Mail** — SMTP via Gmail App-Passwort oder Mailgun Free Tier; nur Passwort-Reset (DSGVO-light)

---

## 8. Sicherheit & DSGVO

| Punkt | Umsetzung |
|---|---|
| Passwörter | bcrypt cost=12 |
| Sessions | HTTP-only, Secure, SameSite=Lax, 30 Tage |
| CSRF | Double-Submit-Token für state-changing Endpoints |
| Rate-Limit | 5 Login-Versuche / 10 min / IP |
| HTTPS | Caddy + Let's Encrypt |
| Datenexport | `/me/export` → JSON aller eigenen Daten |
| Löschen | `/me/delete` → harter Delete |
| Privacy-Seite | `/privacy` |
| Backups | nightly SQLite-Dump, 14 Tage Retention |

---

## 9. Deployment (VPS)

```
/opt/aristeus/
  app/           # Backend (git pull)
  frontend/      # vite build Output
  data/
    aristeus.db
    backups/
  .env

systemd:  aristeus-api.service (Uvicorn)
Caddy:    /etc/caddy/Caddyfile  → 443 → Frontend statisch + /api → Uvicorn:8000
```

`deploy.sh`: `git pull && pip install -r ... && npm run build && systemctl restart aristeus-api`.

---

## 10. Phasen (Roadmap)

| Phase | Dauer | Inhalt |
|---|---|---|
| 0 | ½ Wo | Repo + Projektstruktur + Caddy/systemd-Templates + SQLite/Alembic + Hello-World End-to-End |
| 1 | 1 Wo | Auth + Passwort-Reset + Onboarding + Profil-Edit + Admin-Flag |
| 2 | 1 Wo | Kaufda-Integration + nightly Refresh + Store-Discovery + Freshness-Endpoint |
| 3 | 1.5 Wo | AI-Harness (OpenRouter-Client, Prompts, Validatoren, JSON-Schemas) |
| 4 | 1 Wo | Wochenplan-Flow (Suggestions, AssignDays, parallel Rezept-Gen, Shopping) |
| 5 | ½ Wo | Wochenfeedback + Lern-Aggregation in `learned_preferences` |
| 6 | ½ Wo | PWA-Politur (Manifest, Service Worker, Offline-Liste, Teilen-Button) |
| 7 | ½ Wo | Admin-Übersicht + DSGVO (Export, Löschen) + Beta-Test |

---

## 11. Risiken

| Risiko | Mitigation |
|---|---|
| Kaufda blockt / API ändert sich | konservatives Rate-Limit, korrekter User-Agent, OCR-Fallback aus altem Code als Plan B |
| OpenRouter Free Tier Limits | mehrere Modelle als Fallback, Token-Logging zur Beobachtung |
| Free-Modelle halten JSON-Schema nicht | strikter Validator, bis zu 2 Retries, Fallback-Modell |
| VPS-RAM knapp (2 GB) | leichter Stack, Scheduler-Job darf nicht parallel zu LLM-Calls laufen (einfacher In-Process-Lock) |
| Spam-Registrierungen | Registrierung nur per Einladungs-Token |
