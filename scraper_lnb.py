"""
IDSC Oliva - LNB Auto-updater
Corre via GitHub Actions, actualiza index.html con datos reales de Flashscore
"""
import requests
import json
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

# ── FLASHSCORE IDs ──────────────────────────────────────────────────────
COUNTRY      = "argentina"
TOURNAMENT   = "liga-a"
IDSC_TEAM_ID = "independiente-de-oliva-bX27OjMs"
IDSC_NAME_FS = "Independiente de Oliva"

# ── STANDINGS ───────────────────────────────────────────────────────────
def get_standings():
    """Obtiene tabla de posiciones desde Flashscore"""
    # Flashscore expone datos via endpoint interno con el tournament ID
    # El ID de la Liga A Argentina en Flashscore es: Vy3psK4K
    session = requests.Session()
    session.headers.update(HEADERS)

    # Primero obtener la página principal para las cookies
    session.get("https://www.flashscore.com/", timeout=10)
    time.sleep(1)

    # Endpoint de standings
    url = "https://www.flashscore.com/basketball/argentina/liga-a/standings/"
    r = session.get(url, timeout=15)

    if r.status_code != 200:
        print(f"Standings HTTP {r.status_code} - usando datos del HTML existente")
        return None

    soup = BeautifulSoup(r.text, 'lxml')

    # Buscar datos en script tags (Flashscore embeds JSON en algunos casos)
    standings = []
    for script in soup.find_all('script'):
        if script.string and ('"standings"' in script.string or '"rows"' in script.string):
            try:
                # Extraer JSON del script
                match = re.search(r'"rows"\s*:\s*(\[.*?\])', script.string, re.DOTALL)
                if match:
                    rows = json.loads(match.group(1))
                    for row in rows:
                        standings.append({
                            'pos':  row.get('position', 0),
                            'team': row.get('team', {}).get('name', ''),
                            'pj':   row.get('matches', 0),
                            'pg':   row.get('wins', 0),
                            'pp':   row.get('losses', 0),
                            'pf':   row.get('scoresFor', 0),
                            'pc':   row.get('scoresAgainst', 0),
                        })
                    print(f"Standings: {len(standings)} equipos encontrados")
                    return standings
            except Exception as e:
                print(f"Error parsing standings JSON: {e}")
                continue

    # Si no encontró JSON, parsear HTML directamente
    rows_html = soup.select('.standings__row, .table__row')
    for i, row in enumerate(rows_html):
        cells = row.select('span, td, div')
        if len(cells) >= 5:
            try:
                team_el = row.select_one('.teamName, .team__name, [class*="team"]')
                team_name = team_el.text.strip() if team_el else f"Equipo {i+1}"
                standings.append({
                    'pos': i + 1,
                    'team': team_name,
                    'pj': int(cells[2].text.strip() or 0),
                    'pg': int(cells[3].text.strip() or 0),
                    'pp': int(cells[4].text.strip() or 0),
                    'pf': int(cells[5].text.strip() or 0) if len(cells) > 5 else 0,
                    'pc': int(cells[6].text.strip() or 0) if len(cells) > 6 else 0,
                })
            except:
                continue

    print(f"Standings HTML: {len(standings)} equipos")
    return standings if standings else None

# ── FIXTURES ────────────────────────────────────────────────────────────
def get_idsc_next_match():
    """Obtiene el próximo partido de IDSC"""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get("https://www.flashscore.com/", timeout=10)
    time.sleep(1)

    url = f"https://www.flashscore.com/team/{IDSC_TEAM_ID}/fixtures/"
    r = session.get(url, timeout=15)

    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, 'lxml')

    # Buscar el próximo partido
    matches = soup.select('.event__match, [class*="fixtu"]')
    for match in matches[:5]:
        date_el  = match.select_one('.event__time, [class*="date"]')
        home_el  = match.select_one('.event__homeParticipant, [class*="home"]')
        away_el  = match.select_one('.event__awayParticipant, [class*="away"]')

        if home_el and away_el:
            home = home_el.text.strip()
            away = away_el.text.strip()
            date = date_el.text.strip() if date_el else ''

            if IDSC_NAME_FS in home or IDSC_NAME_FS in away:
                rival = away if IDSC_NAME_FS in home else home
                idsc_local = IDSC_NAME_FS in home
                return {
                    'rival': rival,
                    'idsc_local': idsc_local,
                    'date': date
                }
    return None

# ── HTML UPDATER ─────────────────────────────────────────────────────────
def build_standings_html(standings):
    """Genera el HTML de la tabla de posiciones"""
    rows = []
    for s in standings:
        is_idsc = IDSC_NAME_FS.lower() in s['team'].lower() or 'independiente' in s['team'].lower()
        pct = round(s['pg'] / s['pj'] * 100, 1) if s['pj'] > 0 else 0
        pts = s['pj'] + s['pg']

        if is_idsc:
            row_class = 'standings-row standings-idsc'
            team_name = f'⭐ INDEPENDIENTE (O)'
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
    """Actualiza el index.html con todos los datos nuevos"""
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    today = datetime.now().strftime('%d/%m/%Y')
    changed = []

    # 1. Fecha de actualización
    new_content = re.sub(
        r'Actualizada al \d{2}/\d{2}/\d{4}',
        f'Actualizada al {today}',
        content
    )
    if new_content != content:
        changed.append('fecha tabla')
    content = new_content

    if standings:
        # 2. Tabla de posiciones completa
        idsc = next((s for s in standings if 'independiente' in s['team'].lower()), None)

        # Reemplazar filas de la tabla
        standings_html = build_standings_html(standings)
        new_content = re.sub(
            r'(<div class="standings-row standings-idsc">.*?</div>.*?)(<!-- STANDINGS-END -->)',
            standings_html + r'\n      \2',
            content,
            flags=re.DOTALL
        )

        # 3. Stats IDSC en temporada
        if idsc:
            pct = round(idsc['pg'] / idsc['pj'] * 100, 1) if idsc['pj'] > 0 else 0
            restantes = 36 - idsc['pj']
            diff = idsc['pf'] - idsc['pc']
            diff_str = f'+{diff}' if diff >= 0 else str(diff)

            replacements = [
                # Victorias
                (r'(<div class="t-stat-num">)(18)(</div>\s*<div class="t-stat-lbl">Victorias)',
                 f'\\g<1>{idsc["pg"]}\\g<3>'),
                # Derrotas
                (r'(<div class="t-stat-num">)(9)(</div>\s*<div class="t-stat-lbl">Derrotas)',
                 f'\\g<1>{idsc["pp"]}\\g<3>'),
                # % Victorias
                (r'(<div class="t-stat-num">)(67%)(</div>\s*<div class="t-stat-lbl">% Victorias)',
                 f'\\g<1>{round(pct)}%\\g<3>'),
                # Diferencia
                (r'(<div class="t-stat-num">)(\+\d+)(</div>\s*<div class="t-stat-lbl">Diferencia)',
                 f'\\g<1>{diff_str}\\g<3>'),
                # Restantes
                (r'(<div class="t-stat-num">)(9)(</div>\s*<div class="t-stat-lbl">Restantes)',
                 f'\\g<1>{restantes}\\g<3>'),
            ]

            for pattern, replacement in replacements:
                content = re.sub(pattern, replacement, content)
                changed.append('stats IDSC')

    # 4. Próximo rival
    if next_match:
        rival = next_match['rival'].upper()
        cond = 'Local' if next_match['idsc_local'] else 'Visitante'
        # Actualizar tarjeta de próximo rival en HOME
        content = re.sub(
            r'(po-card po-card-next.*?po-main">)(.*?)(</div>)',
            f'\\g<1>{rival}\\g<3>',
            content,
            count=1,
            flags=re.DOTALL
        )
        changed.append(f'próximo rival: {rival}')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ HTML actualizado: {', '.join(set(changed))}")
    print(f"   Fecha: {today}")

# ── MAIN ─────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f"🏀 IDSC Oliva - LNB Scraper - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("─" * 50)

    standings = get_standings()
    if standings:
        print(f"✅ Tabla obtenida: {len(standings)} equipos")
        idsc = next((s for s in standings if 'independiente' in s['team'].lower()), None)
        if idsc:
            print(f"   IDSC: {idsc['pos']}° | {idsc['pg']}V {idsc['pp']}D | {round(idsc['pg']/idsc['pj']*100,1)}%")
    else:
        print("⚠️  Tabla no disponible - manteniendo datos existentes")

    next_match = get_idsc_next_match()
    if next_match:
        cond = "LOCAL" if next_match['idsc_local'] else "VISITANTE"
        print(f"✅ Próximo partido: vs {next_match['rival']} ({cond}) - {next_match['date']}")
    else:
        print("⚠️  Próximo partido no encontrado")

    update_html(standings, next_match)
    print("─" * 50)
    print("✅ Proceso completado")
