"""
IDSC Oliva - LNB Scraper v5
365scores — parser corregido con estructura real confirmada
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
        data = r.json()
        rows = data['standings'][0]['rows']
        print(f"  Rows: {len(rows)}")
        
        # Debug primera fila para ver estructura de stats
        if rows:
            print(f"  row[0] keys: {list(rows[0].keys())}")
            stats = rows[0].get('stats', [])
            print(f"  stats count: {len(stats)}")
            if stats:
                print(f"  stats[0]: {stats[0]}")
                print(f"  stats[1]: {stats[1]}")
                print(f"  stats sample: {[s.get('name','?') + '=' + str(s.get('value','?')) for s in stats[:8]]}")

        standings = []
        for i, row in enumerate(rows):
            team_info = row.get('competitor', {})
            name = team_info.get('name', f'Equipo {i+1}')
            stats = row.get('stats', [])
            
            # Los stats vienen indexados — necesitamos mapearlos por nombre
            # Del log vemos que hay headers en standings[0]['headers']
            # Construimos dict por nombre
            stats_dict = {}
            for s in stats:
                key = s.get('name') or s.get('shortName') or s.get('type') or ''
                stats_dict[key.lower()] = s.get('value', 0)
            
            # También intentar por índice según orden típico LNB:
            # pos, team, PJ, PG, PP, PF, PC, PTOS, %V
            def sv(idx, *keys):
                """Get stat by index or key"""
                for k in keys:
                    if k.lower() in stats_dict:
                        return int(stats_dict[k.lower()] or 0)
                # Por índice
                if idx < len(stats):
                    return int(stats[idx].get('value', 0) or 0)
                return 0
            
            standings.append({
                'pos':  row.get('position', i+1),
                'team': name,
                'pj':   sv(0, 'gp', 'played', 'pj', 'g', 'gamesPlayed'),
                'pg':   sv(1, 'w', 'wins', 'won', 'pg'),
                'pp':   sv(2, 'l', 'losses', 'lost', 'pp'),
                'pf':   sv(3, 'pf', 'pointsFor', 'scored', 'ptsFor'),
                'pc':   sv(4, 'pa', 'pointsAgainst', 'conceded', 'ptsAgainst'),
            })

        print(f"  Parseados: {len(standings)}")
        # Mostrar primeros 3 para verificar
        for s in standings[:3]:
            print(f"  {s['pos']}° {s['team']}: {s['pj']}PJ {s['pg']}V {s['pp']}D {s['pf']}PF {s['pc']}PC")
        return standings

    except Exception as e:
        print(f"  Error: {e}")
        import traceback; traceback.print_exc()
        return None

def get_next_match():
    url = "https://webws.365scores.com/web/games/current/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        for game in data.get('games', []):
            home = game.get('homeCompetitor', {}).get('name', '')
            away = game.get('awayCompetitor', {}).get('name', '')
            if any(k in home.lower() for k in IDSC_KEYWORDS) or \
               any(k in away.lower() for k in IDSC_KEYWORDS):
                idsc_home = any(k in home.lower() for k in IDSC_KEYWORDS)
                return {
                    'rival': away if idsc_home else home,
                    'idsc_local': idsc_home,
                    'date': game.get('startTime', '')
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
            diff_str = f'+{diff}' if diff >= 0 else str(diff)
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
    if next_match:
        rival = next_match['rival'].upper()
        cond = 'Local' if next_match['idsc_local'] else 'Visitante'
        content = re.sub(
            r'(po-card-next.*?po-main">)(.*?)(</div>)',
            f'\\g<1>{rival}\\g<3>',
            content, count=1, flags=re.DOTALL
        )
        changed.append(f'próximo: {rival}')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ HTML: {', '.join(changed)}")

if __name__ == '__main__':
    print(f"🏀 IDSC - LNB Scraper v5 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("─" * 50)
    print("Tabla de posiciones...")
    standings = get_standings()
    if standings:
        print(f"✅ Tabla: {len(standings)} equipos")
    else:
        print("⚠️  Sin datos")
    print("Próximo partido...")
    nxt = get_next_match()
    if nxt:
        print(f"✅ vs {nxt['rival']} ({'LOCAL' if nxt['idsc_local'] else 'VISITANTE'})")
    else:
        print("⚠️  No encontrado")
    update_html(standings, nxt)
    print("─" * 50)
    print("✅ Completado")
