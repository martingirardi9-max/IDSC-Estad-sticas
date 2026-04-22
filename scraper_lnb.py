"""
IDSC Oliva - LNB Scraper v10
365scores API — Reclasificación + Cuartos de Final Playoff 2025/26

Novedades v10:
  - Trackea las 4 series de Reclasificación (A/B/C/D) automáticamente
  - Actualiza marcadores, estado y badges de partidos jugados de TODAS las series
  - Busca partidos por par de keywords de cada equipo (estrategia robusta)
  - Preparado para Cuartos de Final: cuando terminen las reclasificaciones,
    los cruces de cuartos se definen en CUARTOS_SERIES y se trackeará igual
  - Mantiene toda la lógica v9 para IDSC (serie vs La Unión FSA)
"""
import requests
import re
from datetime import datetime, timezone, timedelta

IDSC_KEYWORDS    = ['independiente', 'oliva', 'idsc']
UNION_KEYWORDS   = ['uni', 'formosa', 'unión', 'union']

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://www.365scores.com',
    'Referer': 'https://www.365scores.com/en/basketball/league/liga-nacional-403/standings',
}

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE SERIES
# Cada serie define:
#   html_id       → prefijo de los id="po-X-..." en el HTML
#   home_kw       → keywords para el equipo "home" (el de mayor seed/local J1)
#   away_kw       → keywords para el equipo "away"
#   dates         → fechas de cada juego (para badges pendientes)
#   playoff_start → fecha ISO mínima para filtrar partidos (evita fase regular)
# ─────────────────────────────────────────────────────────────────────────────

RECLASIF_SERIES = [
    {
        'label':         'Serie B · Ferro vs Peñarol',
        'html_id':       'b',
        'home_kw':       ['ferro', 'carril'],
        'away_kw':       ['peñarol', 'penarol'],
        'dates':         {1:'24/4', 2:'26/4', 3:'30/4', 4:'2/5', 5:'5/5'},
        'playoff_start': '2026-04-23',
    },
    {
        'label':         'Serie C · Obras vs Instituto',
        'html_id':       'c',
        'home_kw':       ['obras'],
        'away_kw':       ['instituto'],
        'dates':         {1:'25/4', 2:'27/4', 3:'30/4', 4:'2/5', 5:'5/5'},
        'playoff_start': '2026-04-23',
    },
    {
        'label':         'Serie D · Boca vs San Martín',
        'html_id':       'd',
        'home_kw':       ['boca'],
        'away_kw':       ['san martín', 'san martin', 'corrientes'],
        'dates':         {1:'25/4', 2:'27/4', 3:'30/4', 4:'2/5', 5:'5/5'},
        'playoff_start': '2026-04-23',
    },
]

# ── Cuartos de Final ──────────────────────────────────────────────────────────
# Completar con los cruces reales cuando terminen las reclasificaciones.
# Agregar los id="po-qfX-..." correspondientes en el HTML y descomentar.
#
# CUARTOS_SERIES = [
#     {
#         'label':         'QF1 · Quimsa vs Ganador A',
#         'html_id':       'qf1',
#         'home_kw':       ['quimsa'],
#         'away_kw':       ['...'],
#         'dates':         {1:'X/5', 2:'X/5', 3:'X/5', 4:'X/5', 5:'X/5'},
#         'playoff_start': '2026-05-08',
#     },
# ]
CUARTOS_SERIES = []  # Vacío hasta conocer los cruces

# Calendario serie IDSC (para home card)
RECLASIF_CALENDAR = {
    1: '2026-04-24',
    2: '2026-04-26',
    3: '2026-04-30',
    4: '2026-05-02',
    5: '2026-05-05',
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def calc_streak(results):
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
    if not results:
        return ''
    return ' '.join('V' if r['win'] else 'D' for r in results[:5])

def format_date(iso_date_str):
    """ISO 8601 UTC → 'Jue 24/04 · 21:00 hs' en Argentina (UTC-3)"""
    if not iso_date_str:
        return ''
    try:
        dt_utc = datetime.fromisoformat(iso_date_str.replace('Z', '+00:00'))
        ar_tz = timezone(timedelta(hours=-3))
        dt_ar = dt_utc.astimezone(ar_tz)
        dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        dia = dias[dt_ar.weekday()]
        return f'{dia} {dt_ar.strftime("%d/%m")} · {dt_ar.strftime("%H:%M")} hs'
    except Exception:
        return ''

def is_idsc(name):
    return any(k in name.lower() for k in IDSC_KEYWORDS)

def is_union(name):
    return any(k in name.lower() for k in UNION_KEYWORDS)

def match_team(name, keywords):
    """True si el nombre del equipo contiene alguno de los keywords."""
    name_lower = name.lower()
    return any(k in name_lower for k in keywords)

def serie_estado_text(home_wins, away_wins):
    """Genera texto de estado y color CSS para una serie genérica."""
    if home_wins == 3:
        return f'✅ GANÓ HOME · {home_wins}–{away_wins}', '#4AE382'
    elif away_wins == 3:
        return f'✅ GANÓ AWAY · {home_wins}–{away_wins}', '#4AE382'
    elif home_wins > 0 or away_wins > 0:
        if home_wins > away_wins:
            color = '#4AE382'
        elif away_wins > home_wins:
            color = '#F1948A'
        else:
            color = 'var(--gold)'
        return f'EN CURSO · {home_wins}–{away_wins}', color
    else:
        return 'EN CURSO', '#5B9BF0'

# ─────────────────────────────────────────────────────────────────────────────
# SCRAPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_standings():
    url = "https://webws.365scores.com/web/standings/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&userCountryId=7&competitions=403"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  Standings HTTP {r.status_code}, {len(r.text)} chars")
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
        return standings
    except Exception as e:
        print(f"  Standings error: {e}")
        return None


def get_next_match():
    """Busca el próximo partido de IDSC (liga o playoff)."""
    url = "https://webws.365scores.com/web/games/current/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403"
    now_utc = datetime.now(timezone.utc)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        candidates = []
        for game in r.json().get('games', []):
            home = game.get('homeCompetitor', {})
            away = game.get('awayCompetitor', {})
            home_name = home.get('name', '')
            away_name = away.get('name', '')
            if not (is_idsc(home_name) or is_idsc(away_name)):
                continue
            status_id = game.get('statusId', 0)
            if status_id == 5:
                continue
            home_score = int(home.get('score', 0) or 0)
            away_score = int(away.get('score', 0) or 0)
            if home_score > 0 or away_score > 0:
                continue
            start_str = game.get('startTime', '')
            if start_str:
                try:
                    dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    if (now_utc - dt).total_seconds() > 14400:
                        continue
                except Exception:
                    pass
            idsc_home = is_idsc(home_name)
            candidates.append({
                'rival':      away_name if idsc_home else home_name,
                'idsc_local': idsc_home,
                'date':       start_str,
                'game_id':    game.get('id'),
            })
        if candidates:
            candidates.sort(key=lambda g: g['date'])
            return candidates[0]
    except Exception as e:
        print(f"  Next match error: {e}")
    return None


def get_idsc_results():
    """Resultados de IDSC en liga regular."""
    url = "https://webws.365scores.com/web/games/results/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403&competitors=72002"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  Results HTTP {r.status_code}")
        if r.status_code != 200:
            return []
        results = []
        for game in r.json().get('games', []):
            home = game.get('homeCompetitor', {})
            away = game.get('awayCompetitor', {})
            home_name = home.get('name', '')
            away_name = away.get('name', '')
            if not (is_idsc(home_name) or is_idsc(away_name)):
                continue
            idsc_home = is_idsc(home_name)
            rival = away_name if idsc_home else home_name
            idsc_score  = int(home.get('score', 0) or 0) if idsc_home else int(away.get('score', 0) or 0)
            rival_score = int(away.get('score', 0) or 0) if idsc_home else int(home.get('score', 0) or 0)
            if idsc_score <= 0 and rival_score <= 0:
                continue
            win = idsc_score > rival_score
            results.append({
                'rival': rival, 'idsc_score': idsc_score, 'rival_score': rival_score,
                'win': win,
                'result_str': f"{'Victoria' if win else 'Derrota'} {idsc_score}–{rival_score}",
            })
        return results
    except Exception as e:
        print(f"  Results error: {e}")
        return []


def get_playoff_serie_results():
    """Resultados de la serie IDSC vs La Unión FSA."""
    results = []
    url = "https://webws.365scores.com/web/games/results/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403&competitors=72002"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            for game in r.json().get('games', []):
                home = game.get('homeCompetitor', {})
                away = game.get('awayCompetitor', {})
                home_name = home.get('name', '')
                away_name = away.get('name', '')
                if not ((is_idsc(home_name) and is_union(away_name)) or
                        (is_union(home_name) and is_idsc(away_name))):
                    continue
                start = game.get('startTime', '')
                if start and start[:10] < '2026-04-23':
                    continue
                idsc_home = is_idsc(home_name)
                idsc_score  = int(home.get('score', 0) or 0) if idsc_home else int(away.get('score', 0) or 0)
                union_score = int(away.get('score', 0) or 0) if idsc_home else int(home.get('score', 0) or 0)
                if idsc_score <= 0 and union_score <= 0:
                    continue
                results.append({'idsc_score': idsc_score, 'union_score': union_score,
                                 'win': idsc_score > union_score, 'start': start})
            print(f"  Serie IDSC: {len(results)} partidos vía /results/")
    except Exception as e:
        print(f"  Playoff serie error: {e}")

    # Fallback: /games/current/ con statusId=5
    if not results:
        url2 = "https://webws.365scores.com/web/games/current/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403"
        try:
            r2 = requests.get(url2, headers=HEADERS, timeout=15)
            if r2.status_code == 200:
                for game in r2.json().get('games', []):
                    home = game.get('homeCompetitor', {})
                    away = game.get('awayCompetitor', {})
                    home_name = home.get('name', '')
                    away_name = away.get('name', '')
                    if not ((is_idsc(home_name) and is_union(away_name)) or
                            (is_union(home_name) and is_idsc(away_name))):
                        continue
                    if game.get('statusId', 0) != 5:
                        continue
                    idsc_home = is_idsc(home_name)
                    idsc_score  = int(home.get('score', 0) or 0) if idsc_home else int(away.get('score', 0) or 0)
                    union_score = int(away.get('score', 0) or 0) if idsc_home else int(home.get('score', 0) or 0)
                    if idsc_score > 0 or union_score > 0:
                        results.append({'idsc_score': idsc_score, 'union_score': union_score,
                                         'win': idsc_score > union_score, 'start': game.get('startTime', '')})
        except Exception as e:
            print(f"  Playoff fallback error: {e}")

    results.sort(key=lambda g: g.get('start', ''))
    for i, g in enumerate(results):
        g['game_num'] = i + 1
    return results


def get_all_league_games():
    """
    Descarga todos los partidos de la liga (current + results) en una sola pasada.
    Se reutiliza para buscar resultados de todas las series sin hacer requests extra.
    """
    all_games = []
    seen = set()
    for endpoint in [
        "https://webws.365scores.com/web/games/current/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403",
        "https://webws.365scores.com/web/games/results/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403",
    ]:
        try:
            r = requests.get(endpoint, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                for g in r.json().get('games', []):
                    gid = g.get('id')
                    if gid not in seen:
                        seen.add(gid)
                        all_games.append(g)
        except Exception as e:
            print(f"  get_all_league_games error: {e}")
    print(f"  Total juegos descargados: {len(all_games)}")
    return all_games


def get_serie_results(serie_config, all_games_cache=None):
    """
    Obtiene los resultados de una serie entre dos equipos usando keywords.
    Filtra por playoff_start para no confundir con partidos de fase regular.
    Devuelve lista ordenada por fecha con game_num asignado.
    """
    home_kw = serie_config['home_kw']
    away_kw = serie_config['away_kw']
    playoff_start = serie_config.get('playoff_start', '2026-04-23')
    label = serie_config.get('label', '')

    games_to_check = all_games_cache or []

    # Si no hay cache, descargar ambos endpoints
    if not games_to_check:
        for endpoint in [
            "https://webws.365scores.com/web/games/current/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403",
            "https://webws.365scores.com/web/games/results/?appTypeId=5&langId=1&timezoneName=America/Argentina/Buenos_Aires&competitions=403",
        ]:
            try:
                r = requests.get(endpoint, headers=HEADERS, timeout=15)
                if r.status_code == 200:
                    games_to_check.extend(r.json().get('games', []))
            except Exception as e:
                print(f"  {label} endpoint error: {e}")

    results = []
    seen_ids = set()

    for game in games_to_check:
        game_id = game.get('id')
        if game_id in seen_ids:
            continue

        home = game.get('homeCompetitor', {})
        away = game.get('awayCompetitor', {})
        home_name = home.get('name', '')
        away_name = away.get('name', '')

        # Verificar el cruce en ambas direcciones
        home_vs_away = match_team(home_name, home_kw) and match_team(away_name, away_kw)
        away_vs_home = match_team(home_name, away_kw) and match_team(away_name, home_kw)
        if not (home_vs_away or away_vs_home):
            continue

        # Solo partidos post-playoff_start
        start = game.get('startTime', '')
        if start and start[:10] < playoff_start:
            continue

        # Solo partidos terminados
        status_id = game.get('statusId', 0)
        home_score = int(home.get('score', 0) or 0)
        away_score = int(away.get('score', 0) or 0)

        if status_id != 5 and (home_score <= 0 and away_score <= 0):
            continue
        if home_score <= 0 and away_score <= 0:
            continue

        seen_ids.add(game_id)

        # Normalizar: siempre home=equipo home_kw, away=equipo away_kw
        if home_vs_away:
            h_score, a_score = home_score, away_score
        else:
            h_score, a_score = away_score, home_score

        results.append({
            'home_score': h_score,
            'away_score': a_score,
            'home_won':   h_score > a_score,
            'start':      start,
        })

    results.sort(key=lambda g: g.get('start', ''))
    for i, g in enumerate(results):
        g['game_num'] = i + 1

    print(f"  {label}: {len(results)} partidos encontrados")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# ACTUALIZADORES HTML
# ─────────────────────────────────────────────────────────────────────────────

def _games_badges_html(results_by_num, dates, total=5):
    """HTML de los badges de juegos para una serie (jugados y pendientes)."""
    spans = []
    for num in range(1, total + 1):
        g = results_by_num.get(num)
        is_opt = num >= 4
        if g:
            won = g['home_won']
            bg     = 'rgba(46,204,113,.18)' if won else 'rgba(231,76,60,.15)'
            border = f'1px solid {"rgba(46,204,113,.5)" if won else "rgba(231,76,60,.4)"}'
            color  = '#4AE382' if won else '#F1948A'
            text   = f"J{num} {g['home_score']}–{g['away_score']}"
        else:
            if is_opt:
                bg = 'rgba(245,166,35,.04)'; border = '1px dashed rgba(245,166,35,.2)'
                color = 'rgba(245,166,35,.5)'; text = f'*J{num} · {dates.get(num, "")}'
            else:
                bg = 'rgba(245,166,35,.08)'; border = '1px solid rgba(245,166,35,.25)'
                color = 'var(--gold)'; text = f'J{num} · {dates.get(num, "")}'
        spans.append(
            f'<span style="font-family:\'DM Mono\',monospace;font-size:.6rem;'
            f'background:{bg};{border};border-radius:20px;padding:.2rem .6rem;color:{color};">'
            f'{text}</span>'
        )
    return '\n          '.join(spans)


def update_serie_html(serie_config, serie_results, content):
    """
    Actualiza en el HTML los elementos de una serie genérica (B, C, D, QF1...):
      id="po-X-home-wins"  → nº de victorias del equipo home
      id="po-X-away-wins"  → nº de victorias del equipo away
      id="po-X-estado"     → texto y color del estado de la serie
      id="po-X-games"      → badges de cada juego (jugado o pendiente)
    """
    if not serie_results:
        return content

    html_id = serie_config['html_id']
    dates   = serie_config['dates']

    home_wins = sum(1 for g in serie_results if g['home_won'])
    away_wins = sum(1 for g in serie_results if not g['home_won'])

    # Contadores de victorias
    content = re.sub(
        r'(id="po-' + html_id + r'-home-wins"[^>]*>)[^<]*(<)',
        r'\g<1>' + str(home_wins) + r'\g<2>',
        content
    )
    content = re.sub(
        r'(id="po-' + html_id + r'-away-wins"[^>]*>)[^<]*(<)',
        r'\g<1>' + str(away_wins) + r'\g<2>',
        content
    )

    # Estado de la serie
    estado_text, estado_color = serie_estado_text(home_wins, away_wins)
    content = re.sub(
        r'(id="po-' + html_id + r'-estado"[^>]*)style="[^"]*"([^>]*>)[^<]*(<)',
        r'\g<1>style="font-family:\'DM Mono\',monospace;font-size:.62rem;color:' + estado_color + r';letter-spacing:1px;"\g<2>' + estado_text + r'\g<3>',
        content
    )

    # Badges de partidos
    results_by_num = {g['game_num']: g for g in serie_results}
    badges_html = _games_badges_html(results_by_num, dates)
    content = re.sub(
        r'(id="po-' + html_id + r'-games"[^>]*>).*?(</div>)',
        r'\g<1>\n          ' + badges_html + r'\n        \g<2>',
        content, flags=re.DOTALL
    )

    print(f"  {serie_config['label']}: HTML actualizado · {home_wins}–{away_wins} · {len(serie_results)} jugados")
    return content


def update_playoff_serie(serie_results, content):
    """Actualiza el cuadro específico de la serie IDSC vs La Unión FSA (estructura v9)."""
    if not serie_results:
        print("  Playoff serie IDSC: sin resultados aún")
        return content

    union_wins = sum(1 for g in serie_results if not g['win'])
    idsc_wins  = sum(1 for g in serie_results if g['win'])

    content = re.sub(r'id="po-union-wins">[^<]*<', f'id="po-union-wins">{union_wins}<', content)
    content = re.sub(r'id="po-idsc-wins">[^<]*<',  f'id="po-idsc-wins">{idsc_wins}<',  content)

    if idsc_wins == 3:
        estado = '✅ IDSC AVANZA'; estado_color = '#4AE382'
    elif union_wins == 3:
        estado = '❌ ELIMINA IDSC'; estado_color = '#F1948A'
    elif idsc_wins > 0 or union_wins > 0:
        estado = f'EN CURSO · {idsc_wins}–{union_wins}'
        estado_color = '#4AE382' if idsc_wins > union_wins else ('#F1948A' if idsc_wins < union_wins else 'var(--gold)')
    else:
        estado = 'EN CURSO'; estado_color = 'var(--gold)'

    content = re.sub(
        r'(id="po-serie-idsc-estado" style="[^"]*")[^>]*(>[^<]*<)',
        f'id="po-serie-idsc-estado" style="font-family:\'DM Mono\',monospace;font-size:.63rem;color:{estado_color};letter-spacing:1px;">{estado}<',
        content
    )

    DATES = {1:'24/4', 2:'26/4', 3:'30/4', 4:'2/5', 5:'5/5'}
    played = {g['game_num']: g for g in serie_results}

    for num in range(1, 6):
        g = played.get(num)
        is_opt = num >= 4
        if g:
            won = g['win']
            bg    = 'rgba(46,204,113,.18)' if won else 'rgba(231,76,60,.15)'
            border_color = 'rgba(46,204,113,.5)' if won else 'rgba(231,76,60,.4)'
            color = '#4AE382' if won else '#F1948A'
            text  = f"J{num} {g['idsc_score']}–{g['union_score']}"
            new_style = (f"background:{bg};border:1px solid {border_color};"
                         f"border-radius:8px;padding:.3rem .7rem;cursor:pointer;"
                         f"font-family:'DM Mono',monospace;font-size:.62rem;color:{color};transition:all .2s;")
        else:
            if is_opt:
                bg = 'rgba(245,166,35,.04)'; border = '1px dashed rgba(245,166,35,.2)'
                color = 'rgba(245,166,35,.5)'; text = f'*J{num} · {DATES[num]}'
            else:
                bg = 'rgba(245,166,35,.08)'; border = '1px solid rgba(245,166,35,.25)'
                color = 'var(--gold)'; text = f'J{num} · {DATES[num]}'
            new_style = (f"background:{bg};{border};"
                         f"border-radius:8px;padding:.3rem .7rem;cursor:pointer;"
                         f"font-family:'DM Mono',monospace;font-size:.62rem;color:{color};transition:all .2s;")

        content = re.sub(
            r'(<div class="po-game-idsc[^"]*" data-game="' + str(num) + r'"[^>]*style=")[^"]*("[^>]*>)[^<]*(<)',
            r'\g<1>' + new_style.replace('\\', '\\\\') + r'\g<2>' + text + r'\g<3>',
            content
        )

    print(f"  Playoff serie IDSC: {idsc_wins}–{union_wins} · {len(serie_results)} partidos jugados")
    return content


def update_home_next_rival(next_match, serie_results, content):
    if not next_match:
        return content

    fecha_fmt = format_date(next_match['date'])
    games_played = len(serie_results)
    next_game_num = games_played + 1
    next_game_date = RECLASIF_CALENDAR.get(next_game_num, '')

    if fecha_fmt:
        badge_text = f'⚡ RECLASIFICACIÓN · J{next_game_num} · {fecha_fmt}'
    elif next_game_date:
        badge_text = f'⚡ RECLASIFICACIÓN · J{next_game_num} · {next_game_date}'
    else:
        badge_text = f'⚡ RECLASIFICACIÓN · J{next_game_num}'

    content = re.sub(
        r'(class="po-pos-badge">⚡ RECLASIFICACIÓN[^<]*</div>)',
        f'class="po-pos-badge">{badge_text}</div>',
        content, count=1
    )

    union_wins = sum(1 for g in serie_results if not g['win'])
    idsc_wins  = sum(1 for g in serie_results if g['win'])
    if serie_results:
        serie_status = f'Serie: IDSC {idsc_wins}–{union_wins} Unión'
        content = re.sub(
            r'(class="po-detail"[^>]*>)(J1 · 24/4[^<]*)',
            f'\\g<1>{serie_status} · J{next_game_num} próximo',
            content, count=1
        )

    print(f"  Home card: J{next_game_num} · {fecha_fmt or next_game_date}")
    return content


def update_rivals_timeline(results, next_rival, content):
    if not results:
        return content
    changed_rivals = []
    for res in results:
        rival_keywords = res['rival'].lower().replace('la unión de formosa', 'la unión fsa').split()[:2]
        pattern = r'(\{name:"[^"]*(?:' + '|'.join(rival_keywords) + r')[^"]*"[^}]*?)status:"(?:next|pending)"([^}]*?\})'
        def replace_status(m):
            block = m.group(0)
            if 'status:"done"' in block:
                return block
            block = block.replace('status:"next"', 'status:"done"').replace('status:"pending"', 'status:"done"')
            changed_rivals.append(res['rival'])
            return block
        new_content = re.sub(pattern, replace_status, content, flags=re.IGNORECASE)
        if new_content != content:
            content = new_content
    if next_rival:
        nv = next_rival.lower().split()[:2]
        pattern2 = r'(data-status=")pending(".*?rival-name">(?:' + '|'.join(nv) + r')[^<]*</div>)'
        content = re.sub(pattern2, r'\g<1>next\g<2>', content, flags=re.IGNORECASE|re.DOTALL)
    if changed_rivals:
        print(f"  Rivales actualizados a done: {changed_rivals}")
    return content


def update_fixture(results, next_rival, content):
    if not results:
        return content
    results_by_rival = {r['rival'].lower(): r for r in results}

    def normalize(name):
        name = name.lower()
        for old, new in {
            'independiente de oliva': 'idsc', 'la unión de formosa': 'la unión fsa',
            'la union de formosa': 'la unión fsa', 'ferro carril oeste': 'ferro',
            'obras sanitarias': 'obras', 'boca juniors': 'boca',
            'san martin': 'san martín', 'penarol': 'peñarol',
        }.items():
            name = name.replace(old, new)
        return name

    def find_result(fixture_text):
        fixture_norm = normalize(fixture_text)
        for rival_key, res in results_by_rival.items():
            words = [w for w in normalize(rival_key).split() if len(w) > 3]
            if any(w in fixture_norm for w in words):
                return res
        return None

    def update_card(m):
        card = m.group(0)
        if 'cup-card' in card or 'Copa' in card:
            return card
        mt = re.search(r'fixture-match">(.*?)</div>', card, re.DOTALL)
        if not mt:
            return card
        match_clean = re.sub(r'<[^>]+>', '', mt.group(1)).replace('IDSC OLIVA', '').replace('VS', '').strip()
        res = find_result(match_clean)
        if 'badge-win' in card or 'badge-loss' in card:
            return card
        if res:
            badge_text = f"✓ {'Victoria' if res['win'] else 'Derrota'} {res['idsc_score']}–{res['rival_score']}"
            badge_class = 'badge-win' if res['win'] else 'badge-loss'
            card = re.sub(r'class="fixture-card[^"]*"', 'class="fixture-card done"', card)
            card = re.sub(r'<span class="badge[^"]*">.*?</span>', f'<span class="badge {badge_class}">{badge_text}</span>', card)
        elif next_rival and any(w in match_clean.lower() for w in normalize(next_rival).split() if len(w) > 3):
            card = re.sub(r'class="fixture-card[^"]*"', 'class="fixture-card next"', card)
            card = re.sub(r'<span class="badge[^"]*">.*?</span>', '<span class="badge badge-next">⚡ Próximo</span>', card)
        return card

    return re.sub(r'<div class="fixture-card[^>]*>.*?</div>\s*</div>', update_card, content, flags=re.DOTALL)


def build_standings_html(standings):
    rows = []
    for s in sorted(standings, key=lambda s: s['pos']):
        idsc = is_idsc(s['team'])
        pct = round(s['pg'] / s['pj'] * 100, 1) if s['pj'] > 0 else 0
        pts = s['pj'] + s['pg']
        if idsc:
            zone = 'playoff-zone' if s['pos'] <= 4 else ('playoffs-pre' if s['pos'] <= 12 else '')
            row_class = f'standings-row standings-idsc {zone}'.strip()
            team_name = '⭐ INDEPENDIENTE (O)'
        elif s['pos'] <= 4:
            row_class, team_name = 'standings-row playoff-zone', s['team'].upper()
        elif s['pos'] <= 12:
            row_class, team_name = 'standings-row playoffs-pre', s['team'].upper()
        else:
            row_class, team_name = 'standings-row out-zone', s['team'].upper()
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


def _rebuild_qualify_detail(current_text, streak_str):
    cleaned = re.sub(r' · [🔥⚠️][^·<]+', '', current_text).strip(' ·')
    return f'{cleaned} · {streak_str}' if streak_str else cleaned


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def update_html(standings, next_match, html_path='index.html'):
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    today = datetime.now().strftime('%d/%m/%Y')
    changed = []

    # Fecha
    content = re.sub(r'Actualizada al \d{2}/\d{2}/\d{4}', f'Actualizada al {today}', content)
    changed.append('fecha')

    # Resultados liga regular IDSC
    results = get_idsc_results()

    # Racha y últimos 5
    if results:
        streak_str = calc_streak(results)
        last5_str  = calc_last5(results)
        print(f"  Racha: {streak_str} | Últimos 5: {last5_str}")
        content = re.sub(
            r'(class="po-card po-card-qualify".*?class="po-detail">)(.*?)(</div>)',
            lambda m: m.group(1) + _rebuild_qualify_detail(m.group(2), streak_str) + m.group(3),
            content, count=1, flags=re.DOTALL
        )
        content = re.sub(
            r'(<div class="stat-num">)[^<]+(</div><div class="stat-lbl">Últimos 5</div></div>)',
            f'\\g<1>{last5_str}\\g<2>', content
        )
        changed.append(f'racha: {streak_str}')

    # Standings
    if standings:
        idsc = next((s for s in standings if is_idsc(s['team'])), None)
        pj_html_match = re.search(r'standings-idsc.*?st-num">(\d+)</span>', content, re.DOTALL)
        pj_html = int(pj_html_match.group(1)) if pj_html_match else 0
        pj_api  = idsc['pj'] if idsc else 0
        print(f"  PJ check: API={pj_api} HTML={pj_html}")

        if idsc and pj_api >= pj_html:
            pct  = round(idsc['pg'] / idsc['pj'] * 100) if idsc['pj'] > 0 else 0
            rest = max(0, 36 - idsc['pj'])
            diff = idsc['pf'] - idsc['pc']
            diff_str = f'+{diff}' if diff >= 0 else str(diff)
            content = re.sub(r'(<div class="stat-num">)\d+(</div>\s*<div class="stat-lbl">Victorias)', f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(<div class="stat-num">)\d+(</div>\s*<div class="stat-lbl">Partidos restantes)', f'\\g<1>{rest}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+(\s*</div>\s*<div class="t-stat-lbl">Victorias)', f'\\g<1>{idsc["pg"]}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+(\s*</div>\s*<div class="t-stat-lbl">Derrotas)', f'\\g<1>{idsc["pp"]}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+%(\s*</div>\s*<div class="t-stat-lbl">% Victorias)', f'\\g<1>{pct}%\\2', content)
            content = re.sub(r'(t-stat-num">\s*)[^<]+(\s*</div>\s*<div class="t-stat-lbl">Diferencia)', f'\\g<1>{diff_str}\\2', content)
            content = re.sub(r'(t-stat-num">\s*)\d+(\s*</div>\s*<div class="t-stat-lbl">Restantes)', f'\\g<1>{rest}\\2', content)
            changed.append(f'IDSC {idsc["pos"]}° {idsc["pg"]}V {idsc["pp"]}D')

        standings_html = build_standings_html(standings)
        new = re.sub(
            r'(<!-- STANDINGS-START -->)(.*?)(<!-- STANDINGS-END -->)',
            f'\\1\n      {standings_html}\n      \\3',
            content, flags=re.DOTALL
        )
        if new != content:
            content = new
            changed.append('tabla posiciones')

    # ── PLAYOFF: Serie IDSC vs La Unión FSA ──────────────────────────────────
    print("Serie IDSC vs La Unión FSA...")
    serie_idsc = get_playoff_serie_results()
    content = update_playoff_serie(serie_idsc, content)
    content = update_home_next_rival(next_match, serie_idsc, content)
    changed.append(f'serie IDSC: {len(serie_idsc)} partidos')

    # ── PLAYOFF: Otras series (B, C, D + futuros Cuartos) ────────────────────
    # Una sola descarga para todas las series
    print("Descargando juegos de la liga para series B/C/D...")
    all_games = get_all_league_games()

    for serie_cfg in (RECLASIF_SERIES + CUARTOS_SERIES):
        print(f"Procesando {serie_cfg['label']}...")
        serie_results = get_serie_results(serie_cfg, all_games_cache=all_games)
        content = update_serie_html(serie_cfg, serie_results, content)
        changed.append(f"{serie_cfg['html_id']}: {len(serie_results)} partidos")

    # Timeline y fixture (liga regular IDSC)
    if results:
        content = update_rivals_timeline(results, next_match['rival'] if next_match else None, content)
        content = update_fixture(results, next_match['rival'] if next_match else None, content)
        changed.append(f'{len(results)} resultados fixture')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ HTML actualizado: {', '.join(changed)}")
    print(f"   Fecha: {today}")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f"🏀 IDSC Oliva - LNB Scraper v10 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("─" * 50)
    print("Tabla de posiciones...")
    standings = get_standings()
    print(f"✅ {len(standings)} equipos" if standings else "⚠️  Sin datos de tabla")
    print("Próximo partido...")
    nxt = get_next_match()
    if nxt:
        cond = 'LOCAL' if nxt['idsc_local'] else 'VISITANTE'
        print(f"✅ vs {nxt['rival']} ({cond}) — {format_date(nxt['date']) or nxt['date']}")
    else:
        print("⚠️  No encontrado")
    update_html(standings, nxt)
    print("─" * 50)
    print("✅ Proceso completado")
