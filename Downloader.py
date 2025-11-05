#!/usr/bin/env python3
"""
DGUV Publikationen Crawler - Vollständige Bibliothek
Durchsucht systematisch die DGUV-Publikationsdatenbank und lädt ALLE verfügbaren PDFs herunter
Crawler für Vorschriften, Regeln, Informationen, Grundsätze und weitere Publikationen
"""

import os
import requests
from pathlib import Path
import time
from datetime import datetime
import re
from bs4 import BeautifulSoup
import json

# Projektstruktur
BASE_DIR = "DGUV_Bibliothek_Komplett"
CATEGORIES = {
    "vorschriften": "01_DGUV_Vorschriften",
    "regeln": "02_DGUV_Regeln",
    "informationen": "03_DGUV_Informationen",
    "grundsaetze": "04_DGUV_Grundsaetze",
    "sonstige": "05_Sonstige_Publikationen"
}

# Basis-URLs für die Publikationsdatenbank
BASE_URL = "https://publikationen.dguv.de"
REGELWERK_URLS = {
    "vorschriften": f"{BASE_URL}/regelwerk/dguv-vorschriften/",
    "regeln": f"{BASE_URL}/regelwerk/dguv-regeln/",
    "informationen": f"{BASE_URL}/regelwerk/dguv-informationen/",
    "grundsaetze": f"{BASE_URL}/regelwerk/dguv-grundsaetze/",
    "alle": f"{BASE_URL}/alle/"
}

# Globale Statistik
stats = {
    "gefunden": 0,
    "erfolgreich": 0,
    "fehlgeschlagen": 0,
    "übersprungen": 0
}

downloaded_files = set()  # Tracking bereits heruntergeladener Dateien


def create_directory_structure():
    """Erstellt die Projektstruktur"""
    print(f"\n{'='*70}")
    print(f"Erstelle Projektstruktur in: {BASE_DIR}")
    print(f"{'='*70}\n")
    
    Path(BASE_DIR).mkdir(exist_ok=True)
    
    for key, folder_name in CATEGORIES.items():
        folder_path = Path(BASE_DIR) / folder_name
        folder_path.mkdir(exist_ok=True)
        print(f"✓ Erstellt: {folder_path}")
    
    print()


def extract_article_links(url, category):
    """Extrahiert alle Artikel-Links von einer Übersichtsseite"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Finde alle Artikel-Links
        article_links = []
        
        # Suche nach verschiedenen Link-Mustern
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Prüfe auf Artikel-Links (verschiedene Muster)
            if '/regelwerk/' in href and '?c=' in href:
                full_url = href if href.startswith('http') else BASE_URL + href
                
                # Extrahiere Artikelnummer aus URL
                match = re.search(r'/(\d+)/', href)
                if match:
                    article_id = match.group(1)
                    title = link.get_text(strip=True)
                    
                    article_links.append({
                        'id': article_id,
                        'url': full_url,
                        'title': title,
                        'category': category
                    })
        
        return article_links
        
    except Exception as e:
        print(f"  ✗ Fehler beim Extrahieren von {url}: {str(e)}")
        return []


def extract_pdf_link(article_url, article_id):
    """Extrahiert PDF-Download-Link von einer Artikel-Seite"""
    try:
        # Direkter PDF-Download-Link (bekanntes Muster)
        pdf_url = f"{BASE_URL}/widgets/pdf/download/article/{article_id}"
        
        # Teste ob PDF verfügbar ist
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.head(pdf_url, headers=headers, timeout=15, allow_redirects=True)
        
        if response.status_code == 200:
            return pdf_url
        else:
            return None
            
    except Exception as e:
        return None


def sanitize_filename(title, article_id):
    """Erstellt einen sicheren Dateinamen"""
    # Entferne ungültige Zeichen
    title = re.sub(r'[<>:"/\\|?*]', '', title)
    title = re.sub(r'\s+', '_', title)
    title = title[:150]  # Begrenze Länge
    
    return f"DGUV_{article_id}_{title}.pdf"


def download_pdf(pdf_url, target_path, filename, title):
    """Lädt ein PDF herunter"""
    global stats
    
    # Check ob bereits heruntergeladen
    file_path = target_path / filename
    if file_path.exists():
        print(f"  ⊘ Übersprungen (existiert bereits): {filename}")
        stats["übersprungen"] += 1
        return True
    
    if filename in downloaded_files:
        print(f"  ⊘ Übersprungen (bereits in Session): {filename}")
        stats["übersprungen"] += 1
        return True
    
    try:
        print(f"  → {title}")
        print(f"    Datei: {filename}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/pdf,*/*',
            'Referer': 'https://publikationen.dguv.de/'
        }
        
        response = requests.get(pdf_url, headers=headers, timeout=45, allow_redirects=True)
        response.raise_for_status()
        
        # Prüfe Content-Type
        content_type = response.headers.get('content-type', '').lower()
        if 'pdf' not in content_type and len(response.content) < 1000:
            print(f"  ⚠ Kein gültiges PDF ({content_type})")
            stats["fehlgeschlagen"] += 1
            return False
        
        # Speichern
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        file_size = len(response.content) / 1024
        print(f"  ✓ Erfolgreich ({file_size:.1f} KB)\n")
        
        downloaded_files.add(filename)
        stats["erfolgreich"] += 1
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Fehler: {str(e)}\n")
        stats["fehlgeschlagen"] += 1
        return False
    except Exception as e:
        print(f"  ✗ Unerwarteter Fehler: {str(e)}\n")
        stats["fehlgeschlagen"] += 1
        return False


def crawl_category(category_name, category_url, max_pages=10):
    """Crawlt eine komplette Kategorie mit Pagination"""
    print(f"\n{'='*70}")
    print(f"Crawle Kategorie: {category_name.upper()}")
    print(f"URL: {category_url}")
    print(f"{'='*70}\n")
    
    all_articles = []
    
    # Crawle Seiten mit Pagination
    for page in range(1, max_pages + 1):
        if page == 1:
            page_url = category_url
        else:
            page_url = f"{category_url}?p={page}"
        
        print(f"📄 Seite {page}: {page_url}")
        
        articles = extract_article_links(page_url, category_name)
        
        if not articles:
            print(f"  → Keine weiteren Artikel gefunden, Kategorie abgeschlossen.\n")
            break
        
        print(f"  → {len(articles)} Artikel gefunden\n")
        all_articles.extend(articles)
        
        time.sleep(1)  # Rate limiting
    
    print(f"📊 Kategorie {category_name}: {len(all_articles)} Artikel insgesamt\n")
    stats["gefunden"] += len(all_articles)
    
    return all_articles


def download_articles(articles):
    """Lädt alle Artikel-PDFs herunter"""
    print(f"\n{'='*70}")
    print(f"Starte Download von {len(articles)} Artikeln")
    print(f"{'='*70}\n")
    
    for idx, article in enumerate(articles, 1):
        print(f"[{idx}/{len(articles)}] Artikel-ID: {article['id']}")
        
        # Bestimme Zielordner
        category_folder = CATEGORIES.get(article['category'], CATEGORIES['sonstige'])
        target_path = Path(BASE_DIR) / category_folder
        
        # Extrahiere PDF-Link
        pdf_url = extract_pdf_link(article['url'], article['id'])
        
        if not pdf_url:
            print(f"  ✗ Kein PDF-Download verfügbar für: {article['title']}\n")
            stats["fehlgeschlagen"] += 1
            continue
        
        # Erstelle Dateinamen
        filename = sanitize_filename(article['title'], article['id'])
        
        # Download
        download_pdf(pdf_url, target_path, filename, article['title'])
        
        time.sleep(0.5)  # Rate limiting


def crawl_all_categories():
    """Crawlt alle DGUV-Kategorien"""
    all_articles = []
    
    for category_name, category_url in REGELWERK_URLS.items():
        if category_name == "alle":
            continue  # Separat behandeln
        
        articles = crawl_category(category_name, category_url, max_pages=20)
        all_articles.extend(articles)
    
    return all_articles


def create_summary():
    """Erstellt Zusammenfassung und Statistik"""
    summary_path = Path(BASE_DIR) / "DOWNLOAD_SUMMARY.md"
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f"""# DGUV Bibliothek - Download-Zusammenfassung

**Crawler-Durchlauf:** {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

## Statistik

- **Gefundene Artikel**: {stats['gefunden']}
- **Erfolgreich heruntergeladen**: {stats['erfolgreich']}
- **Fehlgeschlagen**: {stats['fehlgeschlagen']}
- **Übersprungen (bereits vorhanden)**: {stats['übersprungen']}

## Download-Rate

{stats['erfolgreich']} / {stats['gefunden']} Artikel erfolgreich heruntergeladen 
({100 * stats['erfolgreich'] / max(stats['gefunden'], 1):.1f}%)

## Verteilung nach Kategorien

""")
        
        # Zähle Dateien pro Kategorie
        for cat_key, cat_folder in CATEGORIES.items():
            folder_path = Path(BASE_DIR) / cat_folder
            if folder_path.exists():
                file_count = len(list(folder_path.glob("*.pdf")))
                f.write(f"- **{cat_folder}**: {file_count} PDFs\n")
        
        f.write(f"""
## Weitere Informationen

Alle PDFs stammen von der offiziellen DGUV-Publikationsdatenbank:
https://publikationen.dguv.de/

Für Updates und neue Publikationen:
- Vorschriften: https://publikationen.dguv.de/regelwerk/dguv-vorschriften/
- Regeln: https://publikationen.dguv.de/regelwerk/dguv-regeln/
- Informationen: https://publikationen.dguv.de/regelwerk/dguv-informationen/
- Grundsätze: https://publikationen.dguv.de/regelwerk/dguv-grundsaetze/

## Rechtliche Hinweise

Die Dokumente sind urheberrechtlich geschützt und dienen ausschließlich 
zur persönlichen Information und Anwendung im Arbeitsschutz.

Kommerzielle Nutzung oder Weitergabe nur mit Genehmigung der DGUV.

---
*Automatisch erstellt durch DGUV Publikationen Crawler v1.0*
""")
    
    print(f"\n✓ Zusammenfassung erstellt: {summary_path}")


def create_article_index(articles):
    """Erstellt einen Index aller gefundenen Artikel"""
    index_path = Path(BASE_DIR) / "ARTIKEL_INDEX.json"
    
    # Konvertiere zu JSON-Format
    articles_json = []
    for article in articles:
        articles_json.append({
            'id': article['id'],
            'title': article['title'],
            'category': article['category'],
            'url': article['url'],
            'pdf_url': f"{BASE_URL}/widgets/pdf/download/article/{article['id']}"
        })
    
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(articles_json, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Artikel-Index erstellt: {index_path}")


def main():
    """Hauptfunktion - Crawler-Workflow"""
    print(f"\n{'#'*70}")
    print(f"# DGUV Publikationen Crawler - Vollständige Bibliothek")
    print(f"# Version 1.0 - {datetime.now().strftime('%d.%m.%Y')}")
    print(f"{'#'*70}")
    print(f"\nQuelle: DGUV Publikationsdatenbank")
    print(f"Web: https://publikationen.dguv.de/\n")
    print(f"⚠️  ACHTUNG: Dieser Crawler lädt ALLE verfügbaren DGUV-PDFs herunter!")
    print(f"   Das kann mehrere Stunden dauern und mehrere GB Speicherplatz benötigen.\n")
    
    # Verzeichnisstruktur erstellen
    create_directory_structure()
    
    # Crawle alle Kategorien
    print(f"🔍 Starte Crawler für alle DGUV-Kategorien...\n")
    all_articles = crawl_all_categories()
    
    # Erstelle Artikel-Index
    create_article_index(all_articles)
    
    # Lade alle gefundenen PDFs herunter
    download_articles(all_articles)
    
    # Erstelle Zusammenfassung
    create_summary()
    
    # Finale Statistik
    print(f"\n{'='*70}")
    print(f"CRAWLER ABGESCHLOSSEN")
    print(f"{'='*70}")
    print(f"\n📊 Finale Statistik:")
    print(f"   Gefundene Artikel: {stats['gefunden']}")
    print(f"   ✓ Erfolgreich: {stats['erfolgreich']}")
    print(f"   ✗ Fehlgeschlagen: {stats['fehlgeschlagen']}")
    print(f"   ⊘ Übersprungen: {stats['übersprungen']}")
    print(f"\n📁 Projektverzeichnis: {BASE_DIR}")
    print(f"\n{'#'*70}")
    print(f"# Vollständige DGUV-Bibliothek erstellt!")
    print(f"{'#'*70}\n")


if __name__ == "__main__":
    # Installationshinweis
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("\n⚠️  FEHLER: BeautifulSoup4 nicht installiert!")
        print("Bitte installieren Sie die Abhängigkeiten:")
        print("\n  pip install beautifulsoup4 requests\n")
        exit(1)
    
    main()
