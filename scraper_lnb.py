"""
IDSC Oliva - LNB Scraper v2
Usa la API interna de Flashscore (JSON directo, sin necesidad de JS)
"""
import requests
import json
import re
from datetime import datetime

# ── HEADERS que imitan un navegador real ────────────────────────────────
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'es-AR,es;q=0.9',
    'Referer': 'https://www.flashscore.com/basketball/argentina/liga-a/standings/',
    'x-fsign': 'SW9D1eZo',
    'x-requested-with': 'XMLHttpRequest',
}

IDSC_KEYWORDS = ['independiente', 'oliva', 'idsc']

# ── STANDINGS via API interna ────────────────────────────────────────────
def get_standings():
    """
    Flashscore expone standings via endpoint de datos interno.
    El tournament ID de Liga A Argentina es: Vy3psK4K
    El season ID 2025/26 es: zIhkfCmE
    """
    # Endpoint directo de standings de Flashscore
    urls_to_try = [
        "https://d.flashscore.com/x/feed/ss_1_Vy3psK4K_zIhkfCmE_en_1",
        "https://d.flashscore.com/x/feed/ss_1_Vy3psK4K_zIhkfCmE_es_1",
        "https://flashscore.com/x/feed/ss_1_Vy3psK4K_zIhkfCmE_en_1",
    ]

    for url in urls_to_try:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            print(f"  Standings API {url[-30:]}: HTTP {r.status_code}")
            if r.status_code == 200 and len(r.text) > 100:
                return parse_flashscore_standings(r.text)
        except Exception as e:
            print(f"  Error: {e}")
            continue

    # Fallback: intentar via página de standings con sesión completa
    return get_standings_via_session()

def parse_flashscore_standings(raw):
    """Parsea el formato propietario de Flashscore"""
    standings = []
    # Flashscore usa formato: ¬~AA÷1¬AB÷TeamName¬...
    # Cada equipo está separado por ~
    teams = raw.split('~')
    pos = 1
    for team_str in teams:
        if 'AB÷' not in team_str:
            continue
        try:
            def extract(key):
                match = re.search(rf'{key}÷([^¬~]+)', team_str)
                return match.group(1).strip() if match else '0'

            name = extract('AB')
            if not name or name == '0':
                continue

            standings.append({
                'pos': pos,
                'team': name,
                'pj':   int(extract('AC') or 0),
                'pg':   int(extract('AD') or 0),
                'pp':   int(extract('AE') or 0),
                'pf':   int(extract('AF') or 0),
                'pc':   int(extract('AG') or 0),
            })
            pos += 1
        except:
            continue

    print(f"  Parseados: {len(standings)} equipos")
    return standings if standings else None

def get_standings_via_session():
    """Intento alternativo con sesión y cookies"""
    session = requests.Session()
    session.headers.update(HEADERS)

    # Obtener cookies de la página principal primero
    try:
        session.get("https://www.flashscore.com/basketball/argentina/liga-a/", timeout=10)
    except:
        pass

    # Intentar endpoint alternativo de API
    api_urls = [
        "https://d.flashscore.com/x/feed/tb_1_Vy3psK4K_zIhkfCmE_en_1_0",
        "https://d.flashscore.com/x/feed/tb_1_Vy3psK4K_zIhkfCmE_en_1_1",
    ]

    for url in api_urls:
        try:
            r = session.get(url, timeout=15)
            print(f"  Alt API: HTTP {r.status_code}, {len(r.text)} chars")
            if r.status_code == 200 and len(r.text) > 200:
                result = parse_flashscore_standings(r.text)
                if result:
                    return result
        except Exception as e:
            print(f"  Alt error: {e}")

    return None

# ── NEXT MATCH ───────────────────────────────────────────────────────────
def get_next_match():
    """Obtiene próximo partido de IDSC via API de fixtures"""
    # Team ID de IDSC en Flashscore: bX27OjMs
    urls = [
        "https://d.flashscore.com/x/feed/tp_1_bX27OjMs_en_1",
        "https://d.flashscore.com/x/feed/tf_1_bX27OjMs_en_1",
    ]

    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            print(f"  Fixtures API: HTTP {r.status_code}, {len(r.text)} chars")
            if r.status_code == 200 and len(r.text) > 50:
                return parse_next_match(r.text)
        except Exception as e:
            print(f"  Fixtures error: {e}")

    return None

def parse_next_match(raw):
    """Extrae próximo partido del formato Flashscore"""
    # Buscar partidos de IDSC
    matches = raw.split('~')
    for m in matches[:10]:
        if any(k in m.lower() for k in IDSC_KEYWORDS):
            home = re.search(r'CL÷([^¬~]+)', m)
            away = re.search(r'CW÷([^¬~]+)', m)
            date = re.search(r'AD÷(\d+)', m)
            if home and away:
                home_name = home.group(1)
                away_name = away.group(1)
                idsc_home = any(k in home_name.lower() for k in IDSC_KEYWORDS)
                rival = away_name if idsc_home else home_name
                return {
                    'rival': rival,
                    'idsc_local': idsc_home,
                    'date': date.group(1) if date else ''
                }
    return None

# ── HTML UPDATER ─────────────────────────────────────────────────────────
def build_standings_html(standings):
    rows = []
    for s in standings:
        is_idsc = any(k in s['team'].lower() for k in IDSC_KEYWORDS)
        pct = round(s['pg'] / s['pj'] * 100, 1) if s['pj'] > 0 else 0
        pts = s['pj'] + s['pg']

        if is_idsc:
            row_class = 'standings-row standings-idsc'
            team_name = '⭐ INDEPENDIENTE (O)'
            pos_class = 'st-pos st-pos-gold'
        elif s['pos'] <= 4:
            row_class = 'standings-row playoff-zone'
            team_name = s['team'].upper()
            pos_class = 'st-pos st-pos-num'
        elif s['pos'] <= 12:
            row_class = 'standings-row playoffs-pre'
            team_name = s['team'].upper()
            pos_class = 'st-pos st-pos-num'
        else:
            row_class = 'standings-row'
            team_name = s['team'].upper()
            pos_class = 'st-pos st-pos-num'

        rows.append(
            f'<div class="{row_class}">'
            f'<span class="{pos_class}">{s["pos"]}</span>'
            f'<span class="st-team">{team_name}</span>'
            f'<span class="st-num">{s["pj"]}</span>'
            f'<span class="st-num">{s["pg"]}</span>'
            f'<span class="st-num">{s["pp"]}</span>'
            f'<span class="st-num">{s["pf"]}</span>'
            f'<span class="st-num">{s["pc"]}</span>'
            f'<span class="st-num">{pts}</span>'
            f'<span class="st-num">{pct}%</span>'
            f'</div>'
        )
    return '\n      '.join(rows)

def update_html(standings, next_match, html_path='index.html'):
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    today = datetime.now().strftime('%d/%m/%Y')
    changed = []

    # Fecha
    new = re.sub(r'Actualizada al \d{2}/\d{2}/\d{4}', f'Actualizada al {today}', content)
    if new != content:
        changed.append('fecha')
    content = new

    if standings:
        idsc = next((s for s in standings if any(k in s['team'].lower() for k in IDSC_KEYWORDS)), None)

        if idsc:
            pct  = round(idsc['pg'] / idsc['pj'] * 100) if idsc['pj'] > 0 else 0
            rest = 36 - idsc['pj']
            diff = idsc['pf'] - idsc['pc']
            diff_str = f'+{diff}' if diff >= 0 else str(diff)

            # Stats strip home
            content = re.sub(r'(stat-num">)18(</div>\s*<div class="stat-lbl">Victorias)', f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(stat-num">)9(</div>\s*<div class="stat-lbl">Partidos restantes)', f'\\g<1>{rest}\\2', content)

            # Stats temporada
            content = re.sub(r'(t-stat-num">)18(</div>\s*<div class="t-stat-lbl">Victorias)', f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(t-stat-num">)9(</div>\s*<div class="t-stat-lbl">Derrotas)', f'\\g<1>{idsc["pp"]}\\2', content)
            content = re.sub(r'(t-stat-num">)67%(</div>\s*<div class="t-stat-lbl">% Victorias)', f'\\g<1>{pct}%\\2', content)
            content = re.sub(r'(t-stat-num">\+)\d+(</div>\s*<div class="t-stat-lbl">Diferencia)', f'\\g<1>{diff}\\2', content)
            content = re.sub(r'(t-stat-num">)9(</div>\s*<div class="t-stat-lbl">Restantes)', f'\\g<1>{rest}\\2', content)

            changed.append(f'IDSC: {idsc["pos"]}° {idsc["pg"]}V {idsc["pp"]}D')

        # Tabla de posiciones completa
        standings_html = build_standings_html(standings)
        # Reemplazar entre el header y el divider
        new = re.sub(
            r'(<!-- STANDINGS-START -->)(.*?)(<!-- STANDINGS-END -->)',
            f'\\1\n      {standings_html}\n      \\3',
            content,
            flags=re.DOTALL
        )
        if new != content:
            content = new
            changed.append('tabla posiciones')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ HTML actualizado: {', '.join(set(changed)) if changed else 'sin cambios'}")
    print(f"   Fecha: {today}")

# ── MAIN ─────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f"🏀 IDSC Oliva - LNB Scraper v2 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("─" * 50)

    print("Obteniendo tabla de posiciones...")
    standings = get_standings()

    if standings:
        print(f"✅ Tabla: {len(standings)} equipos")
        idsc = next((s for s in standings if any(k in s['team'].lower() for k in IDSC_KEYWORDS)), None)
        if idsc:
            print(f"   IDSC: {idsc['pos']}° | {idsc['pg']}V {idsc['pp']}D | {round(idsc['pg']/idsc['pj']*100,1)}%")
    else:
        print("⚠️  Tabla no disponible - HTML sin cambios en standings")

    print("Obteniendo próximo partido...")
    next_match = get_next_match()
    if next_match:
        cond = "LOCAL" if next_match['idsc_local'] else "VISITANTE"
        print(f"✅ Próximo: vs {next_match['rival']} ({cond})")
    else:
        print("⚠️  Próximo partido no encontrado")

    update_html(standings, next_match)
    print("─" * 50)
    print("✅ Proceso completado")
