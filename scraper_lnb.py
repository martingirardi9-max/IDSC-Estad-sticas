"""
IDSC Oliva - LNB Scraper v6 — FINAL
365scores API — keys confirmadas: gamePlayed, gamesWon, gamesLost, for, against
"""
import requests
import re
from datetime import datetime

IDSC_KEYWORDS = ['independiente', 'oliva', 'idsc']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://www.365scores.com',
    'Referer': 'https://www.365scores.com/en/basketball/league/liga-nacional-403/standings',
}

def get_standings():
    url = "https://webws.365scores.com/web/standings/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&userCountryId=7&competitions=403"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  HTTP {r.status_code}, {len(r.text)} chars")
        rows = r.json()['standings'][0]['rows']
        standings = []
        for row in rows:
            standings.append({
                'pos':  row.get('position', 0),
                'team': row.get('competitor', {}).get('name', '?'),
                'pj':   int(row.get('gamePlayed', 0) or 0),
                'pg':   int(row.get('gamesWon', 0) or 0),
                'pp':   int(row.get('gamesLost', 0) or 0),
                'pf':   int(row.get('for', 0) or 0),
                'pc':   int(row.get('against', 0) or 0),
            })
        # Verificar primeros 3
        for s in standings[:3]:
            pct = round(s['pg']/s['pj']*100,1) if s['pj'] > 0 else 0
            print(f"  {s['pos']}° {s['team']}: {s['pj']}PJ {s['pg']}V {s['pp']}D {pct}%")
        return standings
    except Exception as e:
        print(f"  Error: {e}")
        return None

def get_next_match():
    url = "https://webws.365scores.com/web/games/current/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        for game in r.json().get('games', []):
            home = game.get('homeCompetitor', {}).get('name', '')
            away = game.get('awayCompetitor', {}).get('name', '')
            if any(k in home.lower() for k in IDSC_KEYWORDS) or \
               any(k in away.lower() for k in IDSC_KEYWORDS):
                idsc_home = any(k in home.lower() for k in IDSC_KEYWORDS)
                return {
                    'rival':      away if idsc_home else home,
                    'idsc_local': idsc_home,
                    'date':       game.get('startTime', '')
                }
    except Exception as e:
        print(f"  Fixtures error: {e}")
    return None

def build_standings_html(standings):
    rows = []
    for s in standings:
        is_idsc = any(k in s['team'].lower() for k in IDSC_KEYWORDS)
        pct = round(s['pg'] / s['pj'] * 100, 1) if s['pj'] > 0 else 0
        pts = s['pj'] + s['pg']
        if is_idsc:
            row_class, pos_class = 'standings-row standings-idsc', 'st-pos st-pos-gold'
            team_name = '⭐ INDEPENDIENTE (O)'
        elif s['pos'] <= 4:
            row_class, pos_class = 'standings-row playoff-zone', 'st-pos st-pos-num'
            team_name = s['team'].upper()
        elif s['pos'] <= 12:
            row_class, pos_class = 'standings-row playoffs-pre', 'st-pos st-pos-num'
            team_name = s['team'].upper()
        else:
            row_class, pos_class = 'standings-row', 'st-pos st-pos-num'
            team_name = s['team'].upper()
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
    content = re.sub(r'Actualizada al \d{2}/\d{2}/\d{4}',
                     f'Actualizada al {today}', content)
    changed.append('fecha')

    if standings:
        idsc = next((s for s in standings
                     if any(k in s['team'].lower() for k in IDSC_KEYWORDS)), None)
        if idsc:
            pct  = round(idsc['pg'] / idsc['pj'] * 100) if idsc['pj'] > 0 else 0
            rest = 36 - idsc['pj']
            diff = idsc['pf'] - idsc['pc']
            diff_str = f'+{diff}' if diff >= 0 else str(diff)
            # Stats strip home
            content = re.sub(r'(stat-num">)18(</div>\s*<div class="stat-lbl">Victorias)',
                             f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(stat-num">)9(</div>\s*<div class="stat-lbl">Partidos restantes)',
                             f'\\g<1>{rest}\\2', content)
            content = re.sub(r'(stat-num">)19(</div>\s*<div class="stat-lbl">PDFs disponibles)',
                             f'\\g<1>19\\2', content)
            # Stats temporada
            content = re.sub(r'(t-stat-num">)\d+(</div>\s*<div class="t-stat-lbl">Victorias)',
                             f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(t-stat-num">)\d+(</div>\s*<div class="t-stat-lbl">Derrotas)',
                             f'\\g<1>{idsc["pp"]}\\2', content)
            content = re.sub(r'(t-stat-num">)\d+%(</div>\s*<div class="t-stat-lbl">% Victorias)',
                             f'\\g<1>{pct}%\\2', content)
            content = re.sub(r'(t-stat-num">\+?-?\d+)(</div>\s*<div class="t-stat-lbl">Diferencia)',
                             f'\\g<1>{diff_str}\\2', content)
            content = re.sub(r'(t-stat-num">)\d+(</div>\s*<div class="t-stat-lbl">Restantes)',
                             f'\\g<1>{rest}\\2', content)
            changed.append(f'IDSC {idsc["pos"]}° {idsc["pg"]}V {idsc["pp"]}D {pct}%')

        # Tabla completa
        standings_html = build_standings_html(standings)
        new = re.sub(
            r'(<!-- STANDINGS-START -->)(.*?)(<!-- STANDINGS-END -->)',
            f'\\1\n      {standings_html}\n      \\3',
            content, flags=re.DOTALL
        )
        if new != content:
            content = new
            changed.append('tabla posiciones')

    if next_match:
        rival = next_match['rival'].upper()
        content = re.sub(
            r'(po-card-next.*?po-main">)(.*?)(</div>)',
            f'\\g<1>{rival}\\g<3>',
            content, count=1, flags=re.DOTALL
        )
        changed.append(f'próximo: {rival}')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ HTML actualizado: {', '.join(changed)}")
    print(f"   Fecha: {today}")

if __name__ == '__main__':
    print(f"🏀 IDSC Oliva - LNB Scraper v6 FINAL - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("─" * 50)

    print("Tabla de posiciones...")
    standings = get_standings()
    if standings:
        print(f"✅ {len(standings)} equipos obtenidos")
    else:
        print("⚠️  Sin datos de tabla")

    print("Próximo partido...")
    nxt = get_next_match()
    if nxt:
        cond = 'LOCAL' if nxt['idsc_local'] else 'VISITANTE'
        print(f"✅ vs {nxt['rival']} ({cond})")
    else:
        print("⚠️  No encontrado")

    update_html(standings, nxt)
    print("─" * 50)
    print("✅ Proceso completado")
