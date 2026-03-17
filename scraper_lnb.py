"""
IDSC Oliva - LNB Scraper v4
365scores API — parser corregido + idioma inglés
"""
import requests
import json
import re
from datetime import datetime

IDSC_KEYWORDS = ['independiente', 'oliva', 'idsc']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
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
        if r.status_code != 200 or len(r.text) < 100:
            return None
        data = r.json()
        
        # Debug: mostrar estructura real de standings
        standings_raw = data.get('standings', [])
        print(f"  standings count: {len(standings_raw)}")
        if standings_raw:
            s0 = standings_raw[0]
            print(f"  standings[0] keys: {list(s0.keys())}")
            groups = s0.get('groups', [])
            print(f"  groups count: {len(groups)}")
            if groups:
                g0 = groups[0]
                print(f"  groups[0] keys: {list(g0.keys())}")
                rows = g0.get('rows', [])
                print(f"  rows count: {len(rows)}")
                if rows:
                    print(f"  rows[0] keys: {list(rows[0].keys())}")
                    print(f"  rows[0] sample: {str(rows[0])[:300]}")
                    return parse_standings(rows)
                # Intentar 'competitors' en lugar de 'rows'
                competitors = g0.get('competitors', [])
                print(f"  competitors count: {len(competitors)}")
                if competitors:
                    print(f"  competitors[0]: {str(competitors[0])[:300]}")
                    return parse_standings(competitors)
            # Sin grupos — intentar rows directo en standings[0]
            rows = s0.get('rows', [])
            print(f"  direct rows: {len(rows)}")
            if rows:
                print(f"  row[0]: {str(rows[0])[:300]}")
                return parse_standings(rows)
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None

def parse_standings(rows):
    standings = []
    for i, row in enumerate(rows):
        try:
            # Intentar diferentes estructuras de nombre
            team = (row.get('competitor') or row.get('team') or row.get('name') or {})
            if isinstance(team, dict):
                name = team.get('name') or team.get('shortName') or f'Equipo {i+1}'
            else:
                name = str(team) or f'Equipo {i+1}'
            
            # Stats — pueden estar como lista o dict
            stats = row.get('stats', [])
            
            def get_stat(*keys):
                for s in stats:
                    for k in keys:
                        if s.get('name','').lower() == k.lower() or \
                           s.get('shortName','').lower() == k.lower() or \
                           s.get('type','') == k:
                            return int(s.get('value', 0) or 0)
                return 0
            
            pj = get_stat('GP','gamesPlayed','played','PJ','G')
            pg = get_stat('W','wins','won','PG','V')
            pp = get_stat('L','losses','lost','PP','D')
            pf = get_stat('PF','pointsFor','scored','PF')
            pc = get_stat('PA','pointsAgainst','conceded','PC')
            
            # Si stats vacío, buscar directo en row
            if pj == 0:
                pj = int(row.get('played') or row.get('gamesPlayed') or row.get('GP') or 0)
                pg = int(row.get('wins') or row.get('won') or row.get('W') or 0)
                pp = int(row.get('losses') or row.get('lost') or row.get('L') or 0)
            
            standings.append({
                'pos':  row.get('position') or row.get('rank') or i+1,
                'team': name,
                'pj':   pj,
                'pg':   pg,
                'pp':   pp,
                'pf':   pf,
                'pc':   pc,
            })
        except Exception as e:
            print(f"  Parse row {i} error: {e}")
    print(f"  Parseados: {len(standings)} equipos")
    return standings if standings else None

def get_next_match():
    url = "https://webws.365scores.com/web/games/current/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  Fixtures HTTP {r.status_code}, {len(r.text)} chars")
        if r.status_code == 200 and len(r.text) > 100:
            data = r.json()
            games = data.get('games', [])
            print(f"  Games encontrados: {len(games)}")
            for game in games:
                home = game.get('homeCompetitor', {}).get('name', '')
                away = game.get('awayCompetitor', {}).get('name', '')
                print(f"  Partido: {home} vs {away}")
                if any(k in home.lower() for k in IDSC_KEYWORDS) or \
                   any(k in away.lower() for k in IDSC_KEYWORDS):
                    idsc_home = any(k in home.lower() for k in IDSC_KEYWORDS)
                    rival = away if idsc_home else home
                    start = game.get('startTime', '')
                    return {'rival': rival, 'idsc_local': idsc_home, 'date': start}
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
    content = re.sub(r'Actualizada al \d{2}/\d{2}/\d{4}', f'Actualizada al {today}', content)
    changed.append('fecha')
    if standings:
        idsc = next((s for s in standings if any(k in s['team'].lower() for k in IDSC_KEYWORDS)), None)
        if idsc:
            pct  = round(idsc['pg'] / idsc['pj'] * 100) if idsc['pj'] > 0 else 0
            rest = 36 - idsc['pj']
            diff = idsc['pf'] - idsc['pc']
            content = re.sub(r'(stat-num">)18(</div>\s*<div class="stat-lbl">Victorias)', f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(stat-num">)9(</div>\s*<div class="stat-lbl">Partidos restantes)', f'\\g<1>{rest}\\2', content)
            content = re.sub(r'(t-stat-num">)18(</div>\s*<div class="t-stat-lbl">Victorias)', f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(t-stat-num">)9(</div>\s*<div class="t-stat-lbl">Derrotas)', f'\\g<1>{idsc["pp"]}\\2', content)
            content = re.sub(r'(t-stat-num">)67%(</div>\s*<div class="t-stat-lbl">% Victorias)', f'\\g<1>{pct}%\\2', content)
            content = re.sub(r'(t-stat-num">)9(</div>\s*<div class="t-stat-lbl">Restantes)', f'\\g<1>{rest}\\2', content)
            changed.append(f'IDSC {idsc["pos"]}° {idsc["pg"]}V {idsc["pp"]}D')
        standings_html = build_standings_html(standings)
        new = re.sub(
            r'(<!-- STANDINGS-START -->)(.*?)(<!-- STANDINGS-END -->)',
            f'\\1\n      {standings_html}\n      \\3',
            content, flags=re.DOTALL
        )
        if new != content:
            content = new
            changed.append('tabla')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ HTML: {', '.join(changed)}")

if __name__ == '__main__':
    print(f"🏀 IDSC - LNB Scraper v4 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("─" * 50)
    print("Tabla de posiciones...")
    standings = get_standings()
    if standings:
        print(f"✅ Tabla: {len(standings)} equipos")
        idsc = next((s for s in standings if any(k in s['team'].lower() for k in IDSC_KEYWORDS)), None)
        if idsc:
            print(f"   IDSC: {idsc['pos']}° {idsc['pg']}V {idsc['pp']}D")
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
