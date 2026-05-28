Weekly-Rezepte-, Einkaufslisten- und Angebots-Workflow

Zweck und Grundidee

Dieser Ablauf verbindet drei Dinge zu einem gemeinsamen Wochenprozess:

1. Angebote der kommenden Woche einsammeln und konsolidieren
2. daraus einen sinnvollen Familien-Wochenplan mit genau 4 Abendessen ableiten
3. eine echte, nutzbare Einkaufsliste erzeugen, die nur die tatsächlich verwendeten Zutaten enthält

Die Grundidee ist nicht einfach „Rezepte erzeugen“, sondern familientaugliche Essensplanung mit Angebotslogik:

• gekocht wird für 2 Erwachsene und 2 kleine Kinder
• die Gerichte sollen lecker, gesund, alltagstauglich und in 20–50 Minuten machbar sein
• die Woche soll hauptsächlich vegetarisch sein
• 1–2 Gerichte mit Huhn oder Pute sind erlaubt bzw. gewünscht
• Zutaten sollen über mehrere Gerichte hinweg klug wiederverwendet werden
• die Einkaufsliste soll realistisch und nicht künstlich aufgebläht sein
• Angebote sollen gezielt genutzt werden, aber nicht um jeden Preis: ergänzende reguläre Zutaten sind ausdrücklich erlaubt

Das System trennt deshalb bewusst zwischen:

• vollständiger Angebotsbasis (latest.md)
• kochrelevanter Arbeitsauswahl (cooking-shortlist.md)
• eigentlich daraus abgeleitetem Wochenplan (inkl. OneNote-Eintrag)

───

Die zentrale Logik in einem Satz

Erst werden Angebote verlässlich gesammelt, dann zu einer kochrelevanten Datengrundlage verdichtet, und erst danach wird daraus der Wochenplan samt Einkaufsliste gebaut.

So bleibt die Rezeptplanung stabil, nachvollziehbar und unabhängig von flüchtigem Chatkontext.

───

Warum der Ablauf so gebaut ist

1. Telegram ist nur Eingangskanal, nicht Datenspeicher

John kann Angebotslinks, Screenshots, Fotos, PDFs oder Text per Telegram schicken. Diese Informationen dürfen aber nicht nur im Chat „liegen bleiben“, weil Cronjobs später nicht zuverlässig auf alten Gesprächskontext bauen sollen.

Darum werden relevante Eingangsdaten in feste lokale Dateien geschrieben:

• state/weekly-offers/inbox/current-lidl.md
• state/weekly-offers/inbox/current-rewe.md
• optional state/weekly-offers/inbox/current-aldi.md

2. Kaufda ist die gemeinsame Primärquelle

Statt Lidl, Rewe und Aldi einzeln über unterschiedliche Händlerseiten abzugrasen, wird Kaufda bevorzugt, weil es robuster und einheitlicher ist.

Vorzugsquelle:

• https://www.kaufda.de/shelf

Zusätzlicher Override:

• state/weekly-offers/direct-links.md

3. Der Wochenplan soll nicht live im Web suchen

Die eigentliche Wochenplanung soll nicht während der Planerstellung wieder Händlerseiten lesen. Deshalb arbeitet sie auf einer vorher erzeugten, lokalen Konsolidierung.

Das macht den Ablauf:

• stabiler
• reproduzierbarer
• leichter prüfbar
• weniger fehleranfällig

───

Gesamtstruktur des Workflows

Der aktuelle Angebots- und Planungsablauf ist in drei operative Bausteine getrennt:

• A — Angebotsanfrage / Eingang öffnen
• B — Angebots-Konsolidierung
• C — Wochenplan aus Angeboten erzeugen

Zusätzlich laufen zwei flankierende Routinen:

• Samstag 16:00: Feedback zur laufenden Woche einholen
• Sonntag 16:00: klassischer Wochenplan ohne Angebotsbasis bleibt vorerst als Parallel-/Fallback-Lauf aktiv

───

Zeitlicher Ablauf Woche für Woche

Samstag, 16:00 — Feedback zur laufenden Woche

Ziel:

• kurzes Feedback von John einholen
• künftige Pläne anpassen

Inhaltlich wird nach Rückmeldung pro Gericht gefragt, damit Vorlieben, Abneigungen und praktische Probleme in kommende Wochen einfließen.

Samstag, 18:00 — Baustein A: Angebotsanfrage

Ziel:

• John kurz um aktuelle Lidl-, Rewe- und bei Bedarf Aldi-Angebote oder direkte Kaufda-Links bitten

Akzeptierte Formen:

• Kaufda-Direktlinks
• Screenshots
• Fotos
• PDF-Seiten
• kopierter Text

Wichtige Regel:
• Sobald John Daten schickt, wird nicht bis Sonntag 08:00 gewartet.
• Stattdessen folgt Baustein B sofort im selben Arbeitsgang.

Sofort nach Eingang neuer Daten — manuelle Eingangsverarbeitung

Wenn John Angebotsdaten liefert, passiert Folgendes:

1. Inhalt der Nachricht wird ausgewertet2. Bilder/Screenshots werden bei Bedarf visuell gelesen
2. direkte Kaufda-Links werden zusätzlich in state/weekly-offers/direct-links.md gepflegt
3. erkannte Inhalte werden in die festen Inbox-Dateien geschrieben
4. anschließend wird direkt Baustein B ausgeführt

Sonntag, 08:00 — Baustein B: Fallback-/Refresh-Konsolidierung

Ziel:

• falls vorher nichts oder nicht genug einging, die kommende Woche trotzdem konsolidieren
• aktuelle Kaufda-Daten erneut verarbeiten

Dieser Lauf ist Fallback/Refresh, nicht mehr der primäre Auslöser.

Sonntag, 08:30 — Baustein C: Wochenplan aus Angeboten

Ziel:

• aus cooking-shortlist.md und bei Bedarf ergänzend aus latest.md den echten Wochenplan bauen
• den Plan nach OneNote schreiben
• denselben Plan zusätzlich im Chat ausgeben

Sonntag, 16:00 — klassischer Wochenplan parallel

Der ältere Sonntags-16:00-Lauf bleibt aktuell noch aktiv, bis der neue angebotsbasierte 08:30-Ablauf langfristig vollständig verifiziert ist.

───

Die drei Bausteine im Detail

A — Angebotsanfrage / Eingangsöffnung

Ziel

John rechtzeitig um verwertbare Angebotsdaten für die kommende Woche bitten.

Warum dieser Schritt wichtig ist

Dieser Schritt sorgt dafür, dass:

• direkte Kaufda-Links genutzt werden können, wenn sie schon vorliegen
• Screenshots/PDFs als Override dienen können
• der Sonntagslauf nicht blind oder mit veralteten Daten arbeitet

Ergebnis von A

A selbst erzeugt noch keinen Wochenplan. Es öffnet nur den Eingang und sorgt dafür, dass Daten hereinkommen.

───

B — Angebots-Konsolidierung

Ziel

Aus Kaufda und ggf. lokalen Overrides eine saubere, lesbare und lokale Angebotsbasis erzeugen.

Eingaben von B

B arbeitet mit diesen Quellen:

1. bevorzugt direkte Links aus
• state/weekly-offers/direct-links.md
2. sonst Kaufda Shelf
• https://www.kaufda.de/shelf
3. ergänzend manuelle Inbox-Dateien
• state/weekly-offers/inbox/current-lidl.md
• state/weekly-offers/inbox/current-rewe.md
• state/weekly-offers/inbox/current-aldi.md

Ausgaben von B

B schreibt immer vier Dateien:

• state/weekly-offers/latest.md
• state/weekly-offers/cooking-shortlist.md
• state/weekly-offers/archive/YYYY-MM-DD.md
• state/weekly-offers/archive/YYYY-MM-DD-shortlist.md

Fachliche Regel von B

B trennt absichtlich zwei Ebenen:

latest.md

Die möglichst vollständige Angebotsbasis.

Sie enthält:

• alle erkannten Angebote aus den gelesenen Prospekten, nicht nur die interessanten Kochartikel
• nutzerseitig lesbar formulierte Zeilen
• keine Technikdiagnosen

Pflichtformat jeder Angebotszeile:

Produkt — Preis — Menge — Grundpreis — Ersparnis/Hinweis — Laden

cooking-shortlist.md

Die gefilterte Arbeitsdatei für Küche, Familienplanung und Ladenpriorisierung.

Sie enthält:

• kochrelevante Lebensmittel
• familiennützliche Angebotsbausteine
• Ladenpriorisierung
• Kochideen

Nicht hineingehören sollen möglichst:

• Haushaltszeug
• Tierfutter
• die meisten Snacks
• Getränke
• irrelevante Non-Food-Artikel

Wichtige konservative Regeln in B

• Preise werden nie geraten
• fehlende Felder werden als unbekannt oder unsicher markiert
• ein Prospekt gilt nicht als gelesen, wenn nur Seite 1 geprüft wurde
• latest.md bleibt bewusst nicht-technisch

───

C — Wochenplan aus der Konsolidierung

Ziel

Aus den konsolidierten Angebotsdateien einen tatsächlich kochbaren Familienplan machen.

Primäre Arbeitsgrundlage

• zuerst state/weekly-offers/cooking-shortlist.md
• ergänzend bei Bedarf state/weekly-offers/latest.md
[14.05.2026 18:23] Aristaeus: Was C inhaltlich leisten muss

C erstellt:

1. genau 4 Abendgerichte für die kommende Woche
2. pro Gericht eine klare Zubereitungsbeschreibung
3. eine echte Einkaufsliste, die nur die verwendeten Zutaten enthält
[14.05.2026 18:23] Aristaeus: 4. einen OneNote-Eintrag im Notizbuch Family Glow Up, Bereich Aristaeus

Inhaltliche Leitplanken für die Rezepte

• 2 Erwachsene + 2 kleine Kinder
• lecker, gesund, alltagstauglich
• 20–50 Minuten
• überwiegend vegetarisch
• 1–2 Geflügelgerichte pro Woche
• gute Nährstoffbalance: Ballaststoffe, Protein, Vitamine• deutliche Abwechslung zu Vorwochen
• Zutatenmengen müssen konkret genannt werden

Sehr wichtige Planungsregel: Angebotsstarttage beachten

Wenn ein Produkt in den Angebotsdateien z. B. mit

• live ab Mo. ...
• live ab Mi. ...
• live ab Fr. ...
markiert ist, dann darf es erst ab diesem Tag für Gerichte und Einkaufsliste verwendet werden.

Beispiel:

• ein Mittwoch-Angebot darf nicht in ein Montag- oder Dienstag-Gericht eingeplant werden

Format des Wochenplans

Der Essensplan soll exakt dieses Muster nutzen:

Tag | Gericht | Zubereitung

Logik der Einkaufsliste

Die Einkaufsliste wird nicht nur nach Supermarkt, sondern zuerst nach Einkaufsfenster / Gültigkeitstag sortiert:

1. zuerst live ab Mo. ...
2. dann live ab Mi. ...
3. dann live ab Fr. ...

Danach innerhalb jedes Datumsblocks:

• nach Laden
• danach nach Warenart
• Gemüse & Obst
• Kühlregal
• Fleisch/Fisch
• Trockenwaren & Konserven
• Sonstiges

Format einzelner Einkaufszeilen

• Angebotsware mit erkennbarem Preis:
• Zutat, Menge — Laden — <Angebotspreis>
• reguläre Ware ohne belastbaren Angebotspreis:
• Zutat, Menge — Laden —

Zusätzlich wird bei Angebotsware der Starttag klar angegeben, z. B.:

• — live ab Mi. 13.5.

Was ausdrücklich nicht in die Einkaufsliste soll

• Zutaten, die im Rezept gar nicht vorkommen
• bloße Angebotsfunde ohne Verwendung
• unnötige Zusatzkäufe
• Obst oder Snacks ohne Rezeptbezug
• erfundene Vergleichspreise
• pseudo-genaue Gesamtersparnis ohne belastbare Vergleichsbasis

───

Rolle von OneNote im Ablauf

OneNote ist das endgültige Ziel des Wochenplans.

Der Plan wird auf eine neue Seite geschrieben in:

• Notizbuch: Family Glow Up
• Bereich: Aristaeus

Wichtig:

• A und B schreiben nicht nach OneNote
• nur C schreibt den fertigen Wochenplan nach OneNote

Dadurch bleibt die Trennung sauber:

• Angebotsdaten lokal
• Wochenplan final in OneNote

───

Wie der Python-Skript kaufda_weekly_offers.py funktioniert

Pfad:

• scripts/kaufda_weekly_offers.py

Zweck:

• aus Kaufda-Prospektlinks eine vollständige Angebotsbasis und eine Küchen-Shortlist erzeugen

Der Skript ist derzeit der bevorzugte technische Weg für Baustein B.

───

Technische Funktionsweise des Skripts – Schritt für Schritt

1. Feste Arbeitsorte definieren

Der Skript arbeitet mit festen Workspace-Pfaden:

• state/weekly-offers/direct-links.md
• state/weekly-offers/latest.md
• state/weekly-offers/cooking-shortlist.md
• state/weekly-offers/archive/

Außerdem sind die drei Zielhändler fest hinterlegt:

• Aldi
• Rewe
• Lidl

2. Direktlinks einlesen

Der Skript liest zuerst direct-links.md.

Dort wird pro Händler unter anderem erwartet:

• Zielgebiet
• Gültig ab
• Link
• Status
• Notiz

Aus dieser Datei zieht der Skript je Händler vor allem den Kaufda-Viewer-Link.

3. Aus dem Kaufda-Link die brochure-id herausziehen

Kaufda-Viewer-Links enthalten einen Abschnitt wie:

/contentViewer/static/<id>

Der Skript extrahiert daraus die brochure-id.

Diese ID ist der Schlüssel für den Zugriff auf die strukturierte Kaufda-API.

4. Strukturierte Kaufda-API aufrufen

Danach baut der Skript pro Prospekt eine API-URL der Form:

https://content-viewer-be.kaufda.de/v1/brochures/<brochure-id>/pages?...

Damit werden die Prospektseiten nicht nur als Bild, sondern als strukturierte JSON-Daten geladen.

Das ist der wichtigste technische Punkt des ganzen Systems.

5. Alle Prospektseiten lesen

Der Skript bleibt nicht bei Seite 1 stehen.

Er iteriert durch:

• pages
• darin offers
• darin content
• darin products und deals
[14.05.2026 18:23] Aristaeus: So entsteht aus dem ganzen Prospekt eine vollständige Datenmenge.

6. Angebotsdetails je Produkt extrahieren

Für jedes Produkt versucht der Skript u. a. folgende Felder zu bilden:
[14.05.2026 18:23] Aristaeus: • Produktname
• Preis
• Menge / Beschreibung
• Grundpreis
• Gültigkeit / Hinweis
• Laden
• zusätzlich intern: Seite, Kategorien, Starttag

Dabei gilt:

• wenn Marke und Produktname getrennt vorliegen, werden sie sinnvoll zusammengesetzt
• wenn Preisbereiche vorliegen, werden sie formatiert• wenn Daten fehlen, wird unbekannt genutzt

7. Gültigkeit richtig formulieren

Ein wichtiger Teil des Skripts ist die Behandlung von Zeitfenstern.

Der Skript versucht aus Kaufda-Daten und Angebotsbeschreibung Formulierungen wie diese sauber herzuleiten:

• live ab Mo. 11.5.
• live ab Mi. 13.5.
• gültig bis Sa. 16.5.

Wenn ein artikelbezogener Starttag erkennbar ist, hat dieser Vorrang vor dem bloßen allgemeinen Prospektstart.

Das ist wichtig, weil Baustein C diese Information später verbindlich für die Reihenfolge von Rezepten und Einkauf nutzt.

8. Doppelte Zeilen vermeiden

Der Skript merkt sich bereits erzeugte Angebotszeilen und überspringt Dubletten.

So wird vermieden, dass identische Artikel mehrfach im Ergebnis landen.

9. latest.md erzeugen

Nach der Extraktion baut der Skript den vollständigen Wochenstand auf.

Struktur:

• # Weekly Offers YYYY-MM-DD
• ## Aldi
• ## Rewe
• ## Lidl
• ## Hinweise zur Woche

Jede Zeile folgt dem Pflichtformat:

Produkt — Preis — Menge — Grundpreis — Ersparnis/Hinweis — Laden

Wichtig:

• latest.md soll möglichst vollständig sein
• keine Techniknotizen
• keine OCR-/Crawler-Kommentare

10. cooking-shortlist.md erzeugen

Danach filtert der Skript die Rohdaten.

Dafür nutzt er umfangreiche Keyword-Logik:

• Food-/Koch-Keywords
• Frische-/Gemüse-/Protein-/Pantry-Keywords
• Ausschlusslisten für Non-Food, Tierfutter, Snacks, Getränke, Haushaltsartikel

Das Ziel ist nicht perfekte Semantik, sondern eine robuste heuristische Trennung zwischen:

• kochrelevant
• eher nicht kochrelevant

Zusätzlich erzeugt der Skript in der Shortlist:

• „Beste Läden für die Woche“
• „Kochideen“
• „Hinweise zur Woche“

11. Dateien schreiben und archivieren

Am Ende schreibt der Skript:

• state/weekly-offers/latest.md
• state/weekly-offers/cooking-shortlist.md
• state/weekly-offers/archive/YYYY-MM-DD.md
• state/weekly-offers/archive/YYYY-MM-DD-shortlist.md

12. JSON-Zusammenfassung ausgeben

Zum Schluss druckt der Skript eine kleine JSON-Zusammenfassung, u. a. mit:

• Datum
• Anzahl gefundener Zeilen pro Händler
• Anzahl der Shortlist-Zeilen pro Händler

Das ist nützlich für schnelle Laufkontrolle.

───

Warum der Skript auf die Kaufda-API setzt statt primär auf OCR

Die bevorzugte Kette lautet:

Kaufda-Link → Viewer → brochure-id → Kaufda-API /v1/brochures/<id>/pages → Produkte/Deals extrahieren → nur bei Lücken OCR ergänzen

Vorteile:

• stabiler als direkte Händlerseiten
• deutlich strukturierter als reines Bildlesen
• vollständiger als bloßes Prüfen einzelner Seiten
• weniger fehleranfällig bei Preisen und Produktnamen

OCR oder Bildanalyse ist nur noch Ergänzung, wenn:

• Felder fehlen
• Text in der API unvollständig ist
• Hinweise im Bild klarer sind als in den API-Feldern

───

Welche Dateien im Ablauf welche Rolle haben

Eingänge / Overrides

• state/weekly-offers/inbox/current-lidl.md
• state/weekly-offers/inbox/current-rewe.md
• state/weekly-offers/inbox/current-aldi.md
• state/weekly-offers/direct-links.md

Konsolidierte Arbeitsdateien

• state/weekly-offers/latest.md
• state/weekly-offers/cooking-shortlist.md

Archiv

• state/weekly-offers/archive/YYYY-MM-DD.md
• state/weekly-offers/archive/YYYY-MM-DD-shortlist.md

Technik

• scripts/kaufda_weekly_offers.py

Workflow-Dokumentation

• features/weekly-offer-scout/WORKFLOW.md
• features/weekly-offer-scout/KAUFDA_PLAYBOOK.md
• features/weekly-offer-scout/SPEC.md

───

Aktuelle Cron-getriebene Ausführung
[14.05.2026 18:23] Aristaeus: Der derzeit hinterlegte Wochenablauf ist praktisch so verdrahtet:

• Samstag 16:00 — Aristaeus Weekly Meal Feedback
• Samstag 18:00 — Aristaeus Weekly Offer Request (Baustein A)
• Sonntag 08:00 — Angebots-Konsolidierung (Baustein B, Fallback/Refresh)
[14.05.2026 18:23] Aristaeus: • Sonntag 08:30 — Wochenplan aus Angeboten (Baustein C)
• Sonntag 16:00 — Aristaeus Weekly Meal Plan (klassischer Parallel-/Fallback-Lauf)

Damit existiert aktuell sowohl der neue angebotsbasierte Frühablauf als auch noch der ältere klassische Sonntagslauf.

───

Zusammenfassung der Systemlogik

Kurz gesagtDer gesamte Ablauf ist so gebaut, dass er:

1. verlässlich Angebotsdaten einsammelt
2. diese lokal und reproduzierbar konsolidiert
3. nur daraus die eigentliche Essensplanung erzeugt
4. eine ehrliche, verwendbare Einkaufsliste ausgibt
5. den fertigen Plan sauber in OneNote ablegt

Die eigentliche Stärke des Systems

Die Stärke liegt nicht nur in Rezeptvorschlägen, sondern in der Kombination aus:

• Wochenrhythmus
• Familienlogik
• Angebotsnutzung
• Starttagsensitivität (live ab ...)
• lokaler Datenhaltung
• sauberer Trennung zwischen Rohdaten, Shortlist und finalem Plan

So entsteht aus Werbeprospekten kein bloßes Sammelsurium, sondern ein strukturierter Küchen- und Einkaufsablauf für die kommende Woche.