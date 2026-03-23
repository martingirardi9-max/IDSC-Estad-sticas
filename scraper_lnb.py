"""
IDSC Oliva - LNB Scraper v8
365scores API — keys confirmadas: gamePlayed, gamesWon, gamesLost, for, against
Mejoras v8:
  - Bracket completo: 4 cruces proyectados (1vs8, 2vs7, 3vs6, 4vs5)
  - Proyeccion de rival playoff con posicion + porcentaje en po-card-rival
  - normalize_name() centralizado — tabla de aliases ampliada (Peniarol, Platense, Atenas...)
  - update_rivals_timeline() usa normalize_name() para mayor robustez
  - Deteccion mejorada de "ya jugado" en next_match
  - Version y log en consola al finalizar
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

NAME_MAP = {
    'independiente de oliva': 'idsc',
    'la union de formosa': 'la union fsa',
    'la union fsa': 'la union fsa',
    'ferro carril oeste': 'ferro',
    'obras sanitarias': 'obras',
    'obras basket': 'obras',
    'olimpico': 'olimpico',
    'ciclista olimpico': 'olimpico lb',
    'penarol': 'penarol',
    'penarol mar del plata': 'penarol mdp',
    'penariol mar del plata': 'penarol mdp',
    'gimnasia y esgrima': 'gimnasia',
    'argentino junin': 'argentino',
    'argentino de junin': 'argentino',
    'racing club chivilcoy': 'racing',
    'racing chivilcoy': 'racing',
    'san martin corrientes': 'san martin c',
    'union de santa fe': 'union sf',
    'boca juniors': 'boca',
    'platense bs as': 'platense',
    'platense vicente lopez': 'platense',
    'atenas cordoba': 'atenas c',
    'regatas corrientes': 'regatas c',
    'instituto atletico': 'instituto',
    'quimsa santiago': 'quimsa',
}

def normalize_name(name):
    import unicodedata
    n = name.lower().strip()
    # strip accents for comparison
    n = ''.join(c for c in unicodedata.normalize('NFD', n) if unicodedata.category(c) != 'Mn')
    for old, new in NAME_MAP.items():
        if old in n:
            return new
    return n

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
        for s in standings[:4]:
            pct = round(s['pg']/s['pj']*100,1) if s['pj'] > 0 else 0
            print(f"  {s['pos']} {s['team']}: {s['pj']}PJ {s['pg']}V {s['pp']}D {pct}%")
        return standings
    except Exception as e:
        print(f"  Error standings: {e}")
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

def get_idsc_results():
    url = "https://webws.365scores.com/web/games/results/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403&competitors=72002"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  Results HTTP {r.status_code}, {len(r.text)} chars")
        if r.status_code != 200: return []
        games = r.json().get('games', [])
        results = []
        for game in games:
            home = game.get('homeCompetitor', {})
            away = game.get('awayCompetitor', {})
            home_name = home.get('name', '')
            away_name = away.get('name', '')
            if not (any(k in home_name.lower() for k in IDSC_KEYWORDS) or
                    any(k in away_name.lower() for k in IDSC_KEYWORDS)):
                continue
            idsc_home = any(k in home_name.lower() for k in IDSC_KEYWORDS)
            rival = away_name if idsc_home else home_name
            idsc_score = int(home.get('score', 0) or 0) if idsc_home else int(away.get('score', 0) or 0)
            rival_score = int(away.get('score', 0) or 0) if idsc_home else int(home.get('score', 0) or 0)
            if idsc_score <= 0 and rival_score <= 0:
                continue
            win = idsc_score > rival_score
            results.append({
                'rival': rival,
                'idsc_score': idsc_score,
                'rival_score': rival_score,
                'win': win,
                'result_str': f"{'Victoria' if win else 'Derrota'} {idsc_score}-{rival_score}",
            })
            print(f"  Resultado: vs {rival} {'V' if win else 'D'} {idsc_score}-{rival_score}")
        return results
    except Exception as e:
        print(f"  Results error: {e}")
        return []

def update_rivals_timeline(results, next_rival, content):
    if not results:
        return content
    changed_rivals = []
    for res in results:
        rival_norm = normalize_name(res['rival'])
        words = [w for w in rival_norm.split() if len(w) > 3]
        if not words:
            words = rival_norm.split()[:2]
        pattern = r'(\{name:"[^"]*(?:' + '|'.join(re.escape(w) for w in words) + r')[^"]*"[^}]*?)status:"(?:next|pending)"([^}]*?\})'
        def replace_status(m, _rival=res['rival']):
            block = m.group(0)
            if 'status:"done"' in block:
                return block
            block = block.replace('status:"next"', 'status:"done"')
            block = block.replace('status:"pending"', 'status:"done"')
            changed_rivals.append(_rival)
            return block
        new_content = re.sub(pattern, replace_status, content, flags=re.IGNORECASE)
        if new_content != content:
            content = new_content
    if next_rival:
        nv_norm = normalize_name(next_rival)
        nv_words = [w for w in nv_norm.split() if len(w) > 3][:2]
        if nv_words:
            pattern2 = r'(data-status=")pending(".*?rival-name">(?:' + '|'.join(nv_words) + r')[^<]*</div>)'
            content = re.sub(pattern2, r'\g<1>next\g<2>', content, flags=re.IGNORECASE|re.DOTALL)
    if changed_rivals:
        print(f"  Rivales -> done: {changed_rivals}")
    return content

def update_fixture(results, next_rival, content):
    if not results:
        return content
    results_by_rival = {normalize_name(r['rival']): r for r in results}

    def find_result_for_fixture(fixture_text):
        ft_norm = normalize_name(fixture_text)
        for rival_norm, res in results_by_rival.items():
            words = [w for w in rival_norm.split() if len(w) > 3]
            if any(w in ft_norm for w in words):
                return res
        return None

    def update_card(m):
        card = m.group(0)
        if 'cup-card' in card or 'Copa' in card or 'COPA' in card:
            return card
        match_text = re.search(r'fixture-match">(.*?)</div>', card, re.DOTALL)
        if not match_text:
            return card
        match_str = match_text.group(1)
        match_clean = re.sub(r'<[^>]+>', '', match_str)
        match_clean = match_clean.replace('IDSC OLIVA', '').replace('VS', '').strip()
        res = find_result_for_fixture(match_clean)
        if 'badge-win' in card or 'badge-loss' in card:
            return card
        if res:
            badge_class = 'badge-win' if res['win'] else 'badge-loss'
            icon = 'V' if res['win'] else 'D'
            badge_text = f"{icon} {res['idsc_score']}-{res['rival_score']}"
            card = re.sub(r'class="badge badge-future">[^<]*</span>',
                          f'class="badge {badge_class}">{badge_text}</span>', card)
        if next_rival and normalize_name(next_rival) in normalize_name(match_clean):
            if 'fixture-card next' not in card:
                card = card.replace('class="fixture-card upcoming"', 'class="fixture-card next"')
        return card

    new_content = re.sub(
        r'<div class="fixture-card[^>]*>.*?</div>\s*</div>',
        update_card,
        content,
        flags=re.DOTALL
    )
    return new_content

def build_standings_html(standings):
    standings_sorted = sorted(standings, key=lambda s: s['pos'])
    rows = []
    for s in standings_sorted:
        is_idsc = any(k in s['team'].lower() for k in IDSC_KEYWORDS)
        pct = round(s['pg'] / s['pj'] * 100, 1) if s['pj'] > 0 else 0
        pts = s['pj'] + s['pg']
        if is_idsc:
            zone = 'playoff-zone' if s['pos'] <= 4 else ('playoffs-pre' if s['pos'] <= 12 else '')
            row_class = f'standings-row standings-idsc {zone}'.strip()
            team_name = 'INDEPENDIENTE (O)'
        elif s['pos'] <= 4:
            row_class = 'standings-row playoff-zone'
            team_name = s['team'].upper()
        elif s['pos'] <= 12:
            row_class = 'standings-row playoffs-pre'
            team_name = s['team'].upper()
        else:
            row_class = 'standings-row'
            team_name = s['team'].upper()
        rows.append(
            f'<div class="{row_class}">'
            f'<span class="st-pos st-pos-num">{s["pos"]}</span>'
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

def update_bracket_full(standings, content):
    """
    Actualiza el bracket completo de 4 cruces: 1vs8, 2vs7, 3vs6, 4vs5.
    Detecta posicion de IDSC y actualiza po-card-rival con su rival proyectado.
    """
    if not standings or len(standings) < 8:
        return content, None

    top8 = sorted(standings, key=lambda s: s['pos'])[:8]
    bracket_pairs = [(1,8),(2,7),(3,6),(4,5)]

    # Detectar posicion de IDSC
    idsc_team = next((s for s in top8 if any(k in s['team'].lower() for k in IDSC_KEYWORDS)), None)
    idsc_pos  = idsc_team['pos'] if idsc_team else None
    idsc_rival_name = None

    if idsc_pos:
        for h, l in bracket_pairs:
            if idsc_pos == h:
                rival_seed = l; break
            elif idsc_pos == l:
                rival_seed = h; break
        else:
            rival_seed = None
        if rival_seed:
            rt = next((s for s in top8 if s['pos'] == rival_seed), None)
            if rt:
                idsc_rival_name = rt['team'].upper()
                pct_r = round(rt['pg']/rt['pj']*100,1) if rt['pj']>0 else 0
                print(f"  Bracket IDSC: #{idsc_pos} vs #{rival_seed} {idsc_rival_name} ({pct_r}%)")
                # Update po-card-rival main name
                content = re.sub(
                    r'(class="po-card po-card-rival">.*?class="po-main">)(.*?)(</div>)',
                    r'\g<1>' + idsc_rival_name + r'\g<3>',
                    content, count=1, flags=re.DOTALL
                )
                # Update po-card-rival detail line
                content = re.sub(
                    r'(po-card-rival[^>]*>.*?po-detail">)[^<]*(</div>)',
                    r'\g<1>' + f'#{rt["pos"]} en tabla · {rt["pg"]}V {rt["pp"]}D · {pct_r}%' + r'\g<2>',
                    content, count=1, flags=re.DOTALL
                )

    # Update bracket-grid seeds
    for h, l in bracket_pairs:
        for seed in [h, l]:
            s = next((x for x in top8 if x['pos']==seed), None)
            if not s: continue
            pct = round(s['pg']/s['pj']*100,1) if s['pj']>0 else 0
            is_idsc = any(k in s['team'].lower() for k in IDSC_KEYWORDS)
            name = 'INDEPENDIENTE (O)' if is_idsc else s['team'].upper()
            content = re.sub(
                r'(<span class="bracket-pos">' + str(seed) + r'[^<]*</span>\s*<span class="bracket-name">)[^<]*(</span>\s*<span class="bracket-pct">)[^<]*(</span>)',
                r'\g<1>' + name + r'\g<2>' + str(pct) + r'%\g<3>',
                content
            )

    return content, idsc_rival_name

def update_html(standings, next_match, html_path='index.html'):
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    today = datetime.now().strftime('%d/%m/%Y')
    changed = []

    content = re.sub(r'Actualizada al \d{2}/\d{2}/\d{4}', f'Actualizada al {today}', content)
    changed.append('fecha')

    if standings:
        idsc = next((s for s in standings if any(k in s['team'].lower() for k in IDSC_KEYWORDS)), None)
        pj_html_match = re.search(r'standings-idsc.*?st-num">(\d+)</span>', content, re.DOTALL)
        pj_html = int(pj_html_match.group(1)) if pj_html_match else 0
        pj_api  = idsc['pj'] if idsc else 0
        print(f"  PJ check: API={pj_api} HTML={pj_html}")

        if idsc and pj_api >= pj_html:
            pct  = round(idsc['pg'] / idsc['pj'] * 100) if idsc['pj'] > 0 else 0
            rest = 36 - idsc['pj']
            diff = idsc['pf'] - idsc['pc']
            diff_str = f'+{diff}' if diff >= 0 else str(diff)
            content = re.sub(r'(<div class="stat-num">)\d+(</div>\s*<div class="stat-lbl">Victorias)', f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(<div class="stat-num">)\d+(</div>\s*<div class="stat-lbl">Partidos restantes)', f'\\g<1>{rest}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+(\s*</div>\s*<div class="t-stat-lbl">Victorias)', f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+(\s*</div>\s*<div class="t-stat-lbl">Derrotas)', f'\\g<1>{idsc["pp"]}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+%(\s*</div>\s*<div class="t-stat-lbl">% Victorias)', f'\\g<1>{pct}%\\2', content)
            content = re.sub(r'(t-stat-num">\s*)[^<]+(\s*</div>\s*<div class="t-stat-lbl">Diferencia)', f'\\g<1>{diff_str}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+(\s*</div>\s*<div class="t-stat-lbl">Restantes)', f'\\g<1>{rest}\\2', content)
            changed.append(f'IDSC {idsc["pos"]} {idsc["pg"]}V {idsc["pp"]}D {pct}%')
        elif idsc:
            print(f"  AVISO: Stats IDSC NO actualizados: API {pj_api}PJ < HTML {pj_html}PJ")

        standings_html = build_standings_html(standings)
        new = re.sub(r'(<!-- STANDINGS-START -->)(.*?)(<!-- STANDINGS-END -->)',
                     f'\\1\n      {standings_html}\n      \\3', content, flags=re.DOTALL)
        if new != content:
            content = new
            changed.append('tabla posiciones')
        else:
            changed.append('tabla sin cambios')

    results = get_idsc_results()

    if next_match:
        nm_norm = normalize_name(next_match['rival'])
        already_played = bool(results) and any(
            nm_norm in normalize_name(r['rival']) or normalize_name(r['rival']) in nm_norm
            for r in results
        )
        if already_played:
            print(f"  AVISO: Proximo ({next_match['rival']}) ya jugado")
            next_match = None

    if next_match:
        rival = next_match['rival'].upper()
        content = re.sub(r'(po-card-next.*?po-main">)(.*?)(</div>)', f'\\g<1>{rival}\\g<3>',
                         content, count=1, flags=re.DOTALL)
        changed.append(f'proximo: {rival}')

    if results:
        content = update_rivals_timeline(results, next_match['rival'] if next_match else None, content)
        changed.append(f'{len(results)} resultados')
        content = update_fixture(results, next_match['rival'] if next_match else None, content)
        changed.append('fixture')

    if standings and len(standings) >= 8:
        content, idsc_rival = update_bracket_full(standings, content)
        changed.append(f'bracket · rival: {idsc_rival or "sin data"}')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"OK HTML actualizado: {', '.join(changed)}")
    print(f"   Fecha: {today} · Scraper v8")

if __name__ == '__main__':
    print(f"IDSC Oliva - LNB Scraper v8 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("-" * 50)
    print("Tabla de posiciones...")
    standings = get_standings()
    if standings:
        print(f"OK {len(standings)} equipos obtenidos")
    else:
        print("AVISO Sin datos de tabla")
    print("Proximo partido...")
    nxt = get_next_match()
    if nxt:
        cond = 'LOCAL' if nxt['idsc_local'] else 'VISITANTE'
        print(f"OK vs {nxt['rival']} ({cond})")
    else:
        print("AVISO No encontrado")
    update_html(standings, nxt)
    print("-" * 50)
    print("OK Proceso completado v8")
