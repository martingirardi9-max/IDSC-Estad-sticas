"""
IDSC Oliva - LNB Scraper v3
Usa 365scores API con league ID 403 (Liga Nacional Argentina)
"""
import requests
import json
import re
from datetime import datetime

IDSC_KEYWORDS = ['independiente', 'oliva', 'idsc']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'es-AR,es;q=0.9',
    'Origin': 'https://www.365scores.com',
    'Referer': 'https://www.365scores.com/es/basketball/league/liga-nacional-403/standings',
}

def get_standings_365():
    """API de 365scores — league ID 403 = Liga Nacional Argentina"""
    urls = [
        "https://webws.365scores.com/web/standings/?appTypeId=5&langId=2&timezoneName=America/Argentina/Buenos_Aires&userCountryId=7&competitions=403",
        "https://webws.365scores.com/web/standings/?appTypeId=5&langId=31&competitions=403",
        "https://webws.365scores.com/web/standings/?competitions=403&appTypeId=5",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            print(f"  365scores: HTTP {r.status_code}, {len(r.text)} chars")
            if r.status_code == 200 and len(r.text) > 100:
                data = r.json()
                print(f"  JSON keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                return parse_365_standings(data)
        except Exception as e:
            print(f"  Error: {e}")
    return None

def parse_365_standings(data):
    """Parsea respuesta JSON de 365scores"""
    standings = []
    try:
        # 365scores estructura: data -> standings -> groups -> rows
        groups = data.get('standings', [{}])[0].get('groups', [{}])[0].get('rows', [])
        if not groups:
            # Intentar estructura alternativa
            groups = data.get('rows', [])
        
        print(f"  Rows encontrados: {len(groups)}")
        
        for i, row in enumerate(groups):
            team = row.get('competitor', {})
            name = team.get('name', f'Equipo {i+1}')
            stats = row.get('stats', [])
            
            # Stats vienen como lista ordenada: GP, W, L, PF, PA, etc.
            def get_stat(key):
                for s in stats:
                    if s.get('name') == key or s.get('shortName') == key:
                        return s.get('value', 0)
                return 0
            
            standings.append({
                'pos': row.get('position', i+1),
                'team': name,
                'pj': int(get_stat('GP') or get_stat('gamesPlayed') or 0),
                'pg': int(get_stat('W') or get_stat('wins') or 0),
                'pp': int(get_stat('L') or get_stat('losses') or 0),
                'pf': int(get_stat('PF') or get_stat('pointsFor') or 0),
                'pc': int(get_stat('PA') or get_stat('pointsAgainst') or 0),
            })
    except Exception as e:
        print(f"  Parse error: {e}")
        # Debug: mostrar estructura real
        print(f"  Data sample: {str(data)[:300]}")
    
    return standings if standings else None

def get_next_match_365():
    """Próximo partido de IDSC desde 365scores"""
    url = "https://webws.365scores.com/web/games/current/?appTypeId=5&langId=2&timezoneName=America/Argentina/Buenos_Aires&competitions=403"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  Fixtures 365: HTTP {r.status_code}, {len(r.text)} chars")
        if r.status_code == 200 and len(r.text) > 100:
            data = r.json()
            games = data.get('games', [])
            for game in games:
                home = game.get('homeCompetitor', {}).get('name', '')
                away = game.get('awayCompetitor', {}).get('name', '')
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
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ HTML: {', '.join(changed)}")

if __name__ == '__main__':
    print(f"🏀 IDSC - LNB Scraper v3 (365scores) - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("─" * 50)
    print("Tabla de posiciones...")
    standings = get_standings_365()
    if standings:
        print(f"✅ {len(standings)} equipos")
        idsc = next((s for s in standings if any(k in s['team'].lower() for k in IDSC_KEYWORDS)), None)
        if idsc:
            print(f"   IDSC: {idsc['pos']}° | {idsc['pg']}V {idsc['pp']}D")
    else:
        print("⚠️  Sin datos")
    print("Próximo partido...")
    nxt = get_next_match_365()
    if nxt:
        print(f"✅ vs {nxt['rival']} ({'LOCAL' if nxt['idsc_local'] else 'VISITANTE'})")
    else:
        print("⚠️  No encontrado")
    update_html(standings, nxt)
    print("✅ Completado")
