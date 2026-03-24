"""
IDSC Oliva - LNB Scraper v8
365scores API — keys confirmadas: gamePlayed, gamesWon, gamesLost, for, against

Novedades v8:
  - Racha actual (streak) calculada desde los resultados
  - Condición Local/Visitante del próximo partido actualizada automáticamente en po-card-next
  - Fecha/hora del próximo partido formateada e insertada
  - Tendencia últimos 5 partidos (ej: V V D V V)
  - Detalles del rival proyectado en playoff (pos, pct, record)
  - Diferencial PF-PC expuesto en po-card-qualify
  - Contador de partidos jugados en sección rivales actualizado
"""
import requests
import re
from datetime import datetime, timezone, timedelta

IDSC_KEYWORDS = ['independiente', 'oliva', 'idsc']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://www.365scores.com',
    'Referer': 'https://www.365scores.com/en/basketball/league/liga-nacional-403/standings',
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def calc_streak(results):
    """Devuelve string de racha actual, ej: '🔥 4V seguidas' o '⚠️ 2D seguidas'"""
    if not results:
        return ''
    count = 1
    last = results[0]['win']
    for r in results[1:]:
        if r['win'] == last:
            count += 1
        else:
            break
    label = 'Victoria' if last else 'Derrota'
    label_plural = 'Victorias' if last else 'Derrotas'
    icon = '🔥' if last else '⚠️'
    if count == 1:
        return f'{icon} 1 {label}'
    return f'{icon} {count} {label_plural} seguidas'

def calc_last5(results):
    """Devuelve string con los últimos 5 resultados, ej: 'V D V V V'"""
    if not results:
        return ''
    last5 = results[:5]
    return ' '.join('V' if r['win'] else 'D' for r in last5)

def format_next_match_date(iso_date_str):
    """
    Convierte el startTime de la API (ISO 8601 UTC) a formato legible en Argentina.
    Ej: '2026-03-23T22:30:00Z' → 'Dom 23/03 · 19:30 hs'
    """
    if not iso_date_str:
        return ''
    try:
        # Parsear fecha UTC
        dt_utc = datetime.fromisoformat(iso_date_str.replace('Z', '+00:00'))
        # Convertir a Argentina (UTC-3)
        ar_tz = timezone(timedelta(hours=-3))
        dt_ar = dt_utc.astimezone(ar_tz)
        dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        dia = dias[dt_ar.weekday()]
        return f'{dia} {dt_ar.strftime("%d/%m")} · {dt_ar.strftime("%H:%M")} hs'
    except Exception:
        return ''

# ─────────────────────────────────────────────────────────────────────────────
# SCRAPERS
# ─────────────────────────────────────────────────────────────────────────────

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
                    'date':       game.get('startTime', ''),
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
                'result_str': f"{'Victoria' if win else 'Derrota'} {idsc_score}–{rival_score}",
                'badge': f"✓ {'Victoria' if win else 'Derrota'} {idsc_score}–{rival_score}",
            })
            print(f"  Resultado: vs {rival} {'V' if win else 'D'} {idsc_score}-{rival_score}")
        return results
    except Exception as e:
        print(f"  Results error: {e}")
        return []

# ─────────────────────────────────────────────────────────────────────────────
# ACTUALIZADORES HTML
# ─────────────────────────────────────────────────────────────────────────────

def update_rivals_timeline(results, next_rival, content):
    if not results:
        return content
    changed_rivals = []
    for res in results:
        rival_name = res['rival'].lower()
        rival_keywords = rival_name.replace('la unión de formosa', 'la unión fsa').split()[:2]
        import re as _re
        pattern = r'(\{name:"[^"]*(?:' + '|'.join(rival_keywords) + r')[^"]*"[^}]*?)status:"(?:next|pending)"([^}]*?\})'
        def replace_status(m):
            block = m.group(0)
            if 'status:"done"' in block:
                return block
            block = block.replace('status:"next"', 'status:"done"')
            block = block.replace('status:"pending"', 'status:"done"')
            changed_rivals.append(res['rival'])
            return block
        new_content = _re.sub(pattern, replace_status, content, flags=_re.IGNORECASE)
        if new_content != content:
            content = new_content
    if next_rival:
        nv = next_rival.lower().split()[:2]
        pattern2 = r'(data-status=")pending(".*?rival-name">(?:' + '|'.join(nv) + r')[^<]*</div>)'
        content = _re.sub(pattern2, r'\g<1>next\g<2>', content, flags=_re.IGNORECASE|_re.DOTALL)
    if changed_rivals:
        print(f"  Rivales actualizados a done: {changed_rivals}")
    return content


def update_fixture(results, next_rival, content):
    import re as _re
    if not results:
        return content
    results_by_rival = {}
    for r in results:
        key = r['rival'].lower()
        results_by_rival[key] = r

    def normalize(name):
        name = name.lower()
        replacements = {
            'independiente de oliva': 'idsc',
            'la unión de formosa': 'la unión fsa',
            'la union de formosa': 'la unión fsa',
            'ferro carril oeste': 'ferro',
            'obras sanitarias': 'obras',
            'olimpico': 'olímpico',
            'penarol': 'peñarol',
            'gimnasia y esgrima': 'gimnasia',
            'argentino junin': 'argentino',
            'racing club chivilcoy': 'racing',
            'san martin': 'san martín',
            'union de santa fe': 'union (sf)',
            'boca juniors': 'boca',
            'ciclista olimpico': 'olímpico (lb)',
        }
        for old, new in replacements.items():
            name = name.replace(old, new)
        return name

    def find_result_for_fixture(fixture_text):
        fixture_norm = normalize(fixture_text)
        for rival_key, res in results_by_rival.items():
            rival_norm = normalize(rival_key)
            words = [w for w in rival_norm.split() if len(w) > 3]
            if any(w in fixture_norm for w in words):
                return res
        return None

    def update_card(m):
        card = m.group(0)
        if 'cup-card' in card or 'Copa' in card or 'COPA' in card:
            return card
        match_text = _re.search(r'fixture-match">(.*?)</div>', card, _re.DOTALL)
        if not match_text:
            return card
        match_str = match_text.group(1)
        match_clean = _re.sub(r'<[^>]+>', '', match_str)
        match_clean = match_clean.replace('IDSC OLIVA', '').replace('VS', '').strip()
        res = find_result_for_fixture(match_clean)
        if 'badge-win' in card:
            return card
        if res:
            badge_text = f"✓ {'Victoria' if res['win'] else 'Derrota'} {res['idsc_score']}–{res['rival_score']}"
            badge_class = 'badge-win' if res['win'] else 'badge-loss'
            card = _re.sub(r'class="fixture-card[^"]*"', 'class="fixture-card done"', card)
            card = _re.sub(r'<span class="badge[^"]*">.*?</span>', f'<span class="badge {badge_class}">{badge_text}</span>', card)
        else:
            if next_rival and any(w in match_clean.lower() for w in normalize(next_rival).split() if len(w) > 3):
                card = _re.sub(r'class="fixture-card[^"]*"', 'class="fixture-card next"', card)
                card = _re.sub(r'<span class="badge[^"]*">.*?</span>', '<span class="badge badge-next">⚡ Próximo</span>', card)
            else:
                if 'fixture-card done' not in card and 'badge-win' not in card:
                    card = _re.sub(r'class="fixture-card next"', 'class="fixture-card upcoming"', card)
        return card

    new_content = _re.sub(
        r'<div class="fixture-card[^>]*>.*?</div>\s*</div>',
        update_card,
        content,
        flags=_re.DOTALL
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
            pos_class = 'st-pos st-pos-num'
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

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def update_html(standings, next_match, html_path='index.html'):
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    today = datetime.now().strftime('%d/%m/%Y')
    changed = []

    # ── Fecha ─────────────────────────────────────────────────────────────────
    content = re.sub(r'Actualizada al \d{2}/\d{2}/\d{4}',
                     f'Actualizada al {today}', content)
    changed.append('fecha')

    # ── Resultados (se necesitan antes de todo para racha/tendencia) ──────────
    results = get_idsc_results()

    # ── Racha actual ──────────────────────────────────────────────────────────
    if results:
        streak_str = calc_streak(results)
        last5_str  = calc_last5(results)
        print(f"  Racha: {streak_str} | Últimos 5: {last5_str}")

        # Actualizar racha en po-card-qualify (po-detail)
        content = re.sub(
            r'(class="po-card po-card-qualify".*?class="po-detail">)(.*?)(</div>)',
            lambda m: m.group(1) + _rebuild_qualify_detail(m.group(2), streak_str) + m.group(3),
            content, count=1, flags=re.DOTALL
        )

        # Actualizar tendencia últimos 5 en stats-strip
        # Busca el stat-item de "Victorias" y agrega/reemplaza el sub-dato de tendencia
        # Si ya existe un stat-item con "Últimos 5" lo reemplaza; si no, lo deja para el ciclo siguiente
        content = re.sub(
            r'(stat-lbl">Últimos 5</div></div>)',
            r'\1',   # placeholder; se actualizará con el bloque completo abajo
            content
        )
        content = re.sub(
            r'(<div class="stat-item"><div class="stat-num">)[^<]+(</div><div class="stat-lbl">Últimos 5</div></div>)',
            f'\\g<1>{last5_str}\\g<2>',
            content
        )
        changed.append(f'racha: {streak_str}')
        changed.append(f'últimos 5: {last5_str}')

    # ── Standings ─────────────────────────────────────────────────────────────
    if standings:
        idsc = next((s for s in standings
                     if any(k in s['team'].lower() for k in IDSC_KEYWORDS)), None)

        import re as _re
        pj_html_match = _re.search(r'standings-idsc.*?st-num">(\d+)</span>', content, _re.DOTALL)
        pj_html = int(pj_html_match.group(1)) if pj_html_match else 0
        pj_api  = idsc['pj'] if idsc else 0
        print(f"  PJ check: API={pj_api} HTML={pj_html}")

        if idsc and pj_api >= pj_html:
            pct  = round(idsc['pg'] / idsc['pj'] * 100) if idsc['pj'] > 0 else 0
            rest = 36 - idsc['pj']
            diff = idsc['pf'] - idsc['pc']
            diff_str = f'+{diff}' if diff >= 0 else str(diff)

            # Stats strip
            content = re.sub(r'(<div class="stat-num">)\d+(</div>\s*<div class="stat-lbl">Victorias)',
                             f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(<div class="stat-num">)\d+(</div>\s*<div class="stat-lbl">Partidos restantes)',
                             f'\\g<1>{rest}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+(\s*</div>\s*<div class="t-stat-lbl">Victorias)',
                             f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+(\s*</div>\s*<div class="t-stat-lbl">Derrotas)',
                             f'\\g<1>{idsc["pp"]}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+%(\s*</div>\s*<div class="t-stat-lbl">% Victorias)',
                             f'\\g<1>{pct}%\\2', content)
            content = re.sub(r'(t-stat-num">\s*)[^<]+(\s*</div>\s*<div class="t-stat-lbl">Diferencia)',
                             f'\\g<1>{diff_str}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+(\s*</div>\s*<div class="t-stat-lbl">Restantes)',
                             f'\\g<1>{rest}\\2', content)

            # ── NUEVO: Actualizar po-card-qualify con posición y diferencial ──
            pos_badge_text = f'{idsc["pos"]}° PUESTO · {pct}% VICTORIAS'
            content = re.sub(
                r'(class="po-card po-card-qualify".*?class="po-pos-badge">)[^<]*(</div>)',
                f'\\g<1>{pos_badge_text}\\g<2>',
                content, count=1, flags=re.DOTALL
            )
            qualify_detail = f'PJ: {idsc["pj"]} · PG: {idsc["pg"]} · PP: {idsc["pp"]} · Restantes: {rest} · Dif: {diff_str}'
            content = re.sub(
                r'(class="po-card po-card-qualify".*?class="po-detail">)(.*?)(</div>)',
                f'\\g<1>{qualify_detail}\\g<3>',
                content, count=1, flags=re.DOTALL
            )

            changed.append(f'IDSC {idsc["pos"]}° {idsc["pg"]}V {idsc["pp"]}D {pct}%')
        elif idsc:
            print(f"  ⚠️  Stats IDSC NO actualizados: API {pj_api}PJ < HTML {pj_html}PJ")

        # ── Tabla completa ────────────────────────────────────────────────────
        standings_html = build_standings_html(standings)
        new = re.sub(
            r'(<!-- STANDINGS-START -->)(.*?)(<!-- STANDINGS-END -->)',
            f'\\1\n      {standings_html}\n      \\3',
            content, flags=re.DOTALL
        )
        if new != content:
            content = new
            changed.append('tabla posiciones')
        else:
            changed.append('tabla sin cambios')

        # ── NUEVO: Playoff rival — detalles del 5° (o rival proyectado) ──────
        if len(standings) >= 8:
            top8 = sorted(standings, key=lambda s: s['pos'])[:8]
            rival_8 = top8[7]
            rival_8_name  = rival_8['team'].upper()
            rival_8_pct   = round(rival_8['pg'] / rival_8['pj'] * 100, 1) if rival_8['pj'] > 0 else 0
            rival_8_sub   = f'{rival_8["pos"]}° en la tabla · {rival_8["pg"]}V {rival_8["pp"]}D · {rival_8_pct}% victorias'
            rival_8_detail = f'Cuartos: {idsc["pos"] if idsc else "?"}° IDSC vs {rival_8["pos"]}° · según tabla {today}'

            content = re.sub(
                r'(class="po-card po-card-rival">.*?class="po-main">)(.*?)(</div>)',
                r'\g<1>' + rival_8_name + r'\g<3>',
                content, count=1, flags=re.DOTALL
            )
            content = re.sub(
                r'(class="po-card po-card-rival".*?class="po-sub">)(.*?)(</div>)',
                f'\\g<1>{rival_8_sub}\\g<3>',
                content, count=1, flags=re.DOTALL
            )
            content = re.sub(
                r'(class="po-card po-card-rival".*?class="po-detail">)(.*?)(</div>)',
                f'\\g<1>{rival_8_detail}\\g<3>',
                content, count=1, flags=re.DOTALL
            )
            changed.append(f'playoff rival: {rival_8_name}')

            # ── Bracket ───────────────────────────────────────────────────────
            for s in top8:
                pos = s['pos']
                pct_b = round(s['pg']/s['pj']*100,1) if s['pj']>0 else 0
                is_idsc = any(k in s['team'].lower() for k in ['independiente','oliva'])
                name = '⭐ INDEPENDIENTE (O)' if is_idsc else s['team'].upper()
                content = re.sub(
                    r'(<span class="bracket-pos">' + str(pos) + r'°</span>\s*<span class="bracket-name">)[^<]*(</span>\s*<span class="bracket-pct">)[^<]*(</span>)',
                    r'\g<1>' + name + r'\g<2>' + str(pct_b) + r'%\g<3>',
                    content
                )
            changed.append('bracket')

    # ── Próximo partido ───────────────────────────────────────────────────────
    if next_match:
        already_played = bool(results) and any(
            any(k in r['rival'].lower() for k in next_match['rival'].lower().split()[:2])
            for r in results
        )
        if already_played:
            print(f"  ⚠️  Próximo ({next_match['rival']}) ya jugado — buscando siguiente...")
            next_match = None

    if next_match:
        rival = next_match['rival'].upper()

        # Nombre del rival en po-card-next
        content = re.sub(
            r'(po-card-next.*?po-main">)(.*?)(</div>)',
            f'\\g<1>{rival}\\g<3>',
            content, count=1, flags=re.DOTALL
        )

        # ── NUEVO: Condición Local / Visitante en po-card-next po-detail ─────
        condicion = 'Local' if next_match['idsc_local'] else 'Visitante'
        condicion_icon = '🏠' if next_match['idsc_local'] else '✈️'
        fecha_fmt = format_next_match_date(next_match['date'])
        next_detail = f'Liga Nacional · {condicion_icon} {condicion}'
        if fecha_fmt:
            next_detail += f' · {fecha_fmt}'

        content = re.sub(
            r'(class="po-card po-card-next".*?class="po-detail">)(.*?)(</div>)',
            f'\\g<1>{next_detail}\\g<3>',
            content, count=1, flags=re.DOTALL
        )

        # ── NUEVO: po-pos-badge con fecha formateada ─────────────────────────
        if fecha_fmt:
            content = re.sub(
                r'(class="po-card po-card-next".*?class="po-pos-badge">)[^<]*(</div>)',
                f'\\g<1>{fecha_fmt} · Liga Nacional\\g<2>',
                content, count=1, flags=re.DOTALL
            )

        # ── NUEVO: Condición en po-sub de la card ────────────────────────────
        # Si hay standings, intentar mostrar datos del rival
        if standings:
            rival_standing = next((s for s in standings
                                   if any(w in s['team'].lower()
                                          for w in next_match['rival'].lower().split()[:2]
                                          if len(w) > 3)), None)
            if rival_standing:
                rpct = round(rival_standing['pg']/rival_standing['pj']*100,1) if rival_standing['pj']>0 else 0
                next_sub = f'{rival_standing["pos"]}° en la tabla · {rival_standing["pg"]}V {rival_standing["pp"]}D · {rpct}% victorias'
                content = re.sub(
                    r'(class="po-card po-card-next".*?class="po-sub">)(.*?)(</div>)',
                    f'\\g<1>{next_sub}\\g<3>',
                    content, count=1, flags=re.DOTALL
                )

        changed.append(f'próximo: {rival} ({condicion})')

    # ── Timeline y fixture ────────────────────────────────────────────────────
    if results:
        content = update_rivals_timeline(results, next_match['rival'] if next_match else None, content)
        changed.append(f'{len(results)} resultados en rivales')
        content = update_fixture(results, next_match['rival'] if next_match else None, content)
        changed.append('fixture')

        # ── NUEVO: Contador de partidos jugados en sección rivales ────────────
        # Actualiza "XX partidos · Y con informe · Z pendientes"
        # Solo actualiza el número total de PJ en el contador de la sección
        if standings:
            idsc_s = next((s for s in standings
                           if any(k in s['team'].lower() for k in IDSC_KEYWORDS)), None)
            if idsc_s:
                pj_total = idsc_s['pj']
                content = re.sub(
                    r'(\d+) partidos · (\d+ con informe · \d+ pendientes)',
                    f'{pj_total} partidos · \\2',
                    content
                )
                changed.append(f'contador rivales: {pj_total}PJ')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ HTML actualizado: {', '.join(changed)}")
    print(f"   Fecha: {today}")


def _rebuild_qualify_detail(current_text, streak_str):
    """
    Auxiliar: si la racha ya está en el texto del po-detail de qualify, la reemplaza.
    Si no existe, la agrega al final.
    """
    # Remover racha anterior si existía
    cleaned = re.sub(r' · [🔥⚠️][^·<]+', '', current_text).strip(' ·')
    if streak_str:
        return f'{cleaned} · {streak_str}'
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f"🏀 IDSC Oliva - LNB Scraper v8 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
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
        fecha_fmt = format_next_match_date(nxt['date'])
        print(f"✅ vs {nxt['rival']} ({cond}) — {fecha_fmt or nxt['date']}")
    else:
        print("⚠️  No encontrado")
    update_html(standings, nxt)
    print("─" * 50)
    print("✅ Proceso completado")
