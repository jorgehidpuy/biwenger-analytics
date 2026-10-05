"""Puente entre la API de Biwenger y el Excel.

Este módulo NO sustituye a bot_diario.py: le quita de encima la parte de
escribir las hojas del mercado, para que el dato llegue al Excel con el id
numérico y con el reparto de casa y fuera EXACTO que publica Biwenger.

Por qué importa el id:
    Todos los cruces del Excel van por nombre + equipo. Biwenger renombra
    jugadores sin avisar (tres oleadas en dos semanas: "Yassir Zabiri" pasó a
    "Zabiri" y "Canales" a "Sergio Canales") y los traspasa de club a mitad de
    temporada. Cada vez que pasa hay que salir a fusionar fichas a mano o con
    detectores de parecido. El id no cambia nunca.

Por qué importan pointsHome/pointsAway:
    Hasta ahora los puntos en casa y fuera se DEDUCÍAN comparando el export de
    hoy con el de ayer: si subía el contador de partidos en casa y no el de
    fuera, los puntos nuevos eran de casa. De ahí salían los repartos "por
    proporción" cuando se jugaban dos partidos entre importaciones, las
    siembras de los jugadores nuevos y las reconciliaciones cuando Biwenger
    rectificaba la puntuación de una jornada ya dada. La API los da exactos.

Uso desde bot_diario.py:

    import api_biwenger

    jugadores, equipos = api_biwenger.descargar_jugadores()
    api_biwenger.escribir_export(wb, jugadores, equipos)          # hoja de hoy
    api_biwenger.escribir_export(wb, jugadores, equipos,
                                 hoja='Biwenger_Ayer', de_ayer=True)

Después, el resto del bot sigue igual: guardar_excel, recalcular fórmulas y
llamar a las funciones de app.py.
"""

import json
import urllib.request

URL_DATOS = ('https://cf.biwenger.com/api/v2/competitions/la-liga/data'
             '?lang=es&score=2')

# Biwenger numera las posiciones del 1 al 4. Cualquier otra cosa NO es un
# jugador: los entrenadores viajan en el mismo JSON (Flick, Mourinho, Simeone…)
# y en su día se colaron 20 como centrocampistas, contaminando medias,
# calibraciones y onces ideales.
POSICIONES = {1: 'Portero', 2: 'Defensa', 3: 'Centrocampista', 4: 'Delantero'}

# Cabecera del export, con las tres columnas nuevas al final. Van al final a
# propósito: las nueve primeras son las de siempre y ninguna fórmula del libro
# (que apunta a Biwenger_Export!$D:$D, $G:$G, $H:$H…) se entera del cambio.
COLUMNAS_EXPORT = ['Equipo', 'Jugador', 'Posición', 'Puntos', 'Precio', 'PJ',
                   'Casa', 'Fuera', 'Media', 'ID', 'Pts Casa', 'Pts Fuera',
                   'Goles', 'Asistencias', 'Estado']

# El 'status' que devuelve Biwenger. 'ok' es estar disponible; el resto son
# motivos distintos de no poder jugar, y al Excel le basta con saber que no
# está disponible (su columna Lesion solo entiende 'si' y 'no').
ESTADOS_FUERA = ('injured', 'injury', 'doubt', 'sanctioned', 'suspended', 'banned',
                 'out', 'unknown')

TIEMPO_ESPERA = 20

# 🧭 MULTIPOSICIÓN
# Biwenger deja alinear a algunos jugadores en dos o tres posiciones y decide él
# a quién (a Eric García le quitó la de medio). Aquí se leen del mismo JSON de
# jugadores: TODOS los campos que hablen de posición, se llamen como se llamen
# ('altPositions', 'positions'…), se juntan con la principal. Así no depende de
# adivinar el nombre exacto del campo.
CLAVES_MULTIPOSICION = ('altPositions', 'alternativePositions', 'secondaryPositions',
                        'otherPositions', 'positions')
CAMPO_MULTIPOSICION = None      # el campo que resultó traerlas, para el log
CAMPOS_DE_MUESTRA = []          # los campos de un jugador, por si no aparecen


def _numeros_de_posicion(valor):
    """Las posiciones 1-4 que haya en un valor del JSON: un número, una lista de
    números o una lista de objetos con 'id'/'position'. [] si no es eso."""
    if isinstance(valor, bool):
        return []
    if isinstance(valor, (int, float)):
        return [int(valor)] if 1 <= int(valor) <= 4 else []
    if isinstance(valor, list) and valor:
        salida = []
        for v in valor:
            if isinstance(v, dict):
                v = v.get('id', v.get('position'))
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 1 <= int(v) <= 4:
                return []
            salida.append(int(v))
        return salida
    return []


def _posiciones_extra(bruto):
    """(posiciones además de la principal, campos de donde salen)."""
    extra, campos = set(), []
    for clave, valor in bruto.items():
        if clave == 'position':
            continue
        if clave in CLAVES_MULTIPOSICION or 'position' in str(clave).lower():
            numeros = _numeros_de_posicion(valor)
            if numeros:
                extra.update(numeros)
                campos.append(clave)
    return extra, campos



NAVEGADOR = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}


def _pedir(url, cabeceras=None):
    # Las cabeceras propias se SUMAN a las de navegador, no las sustituyen: sin
    # User-Agent, cf.biwenger.com responde vacío.
    peticion = urllib.request.Request(url, headers={**NAVEGADOR, **(cabeceras or {})})
    with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as respuesta:
        return json.loads(respuesta.read().decode('utf-8'))


def descargar_jugadores(url=URL_DATOS):
    """(lista de jugadores limpia, mapa id_equipo -> nombre).

    Devuelve solo jugadores de verdad: con posición 1-4 y con un club que se
    pueda resolver. Los descartados se quedan fuera aquí mismo, que es donde
    hay que filtrarlos; si entran al Excel, luego hay que barrerlos de cuatro
    hojas distintas.
    """
    datos = _pedir(url).get('data', {})
    equipos = {int(k): v.get('name') for k, v in (datos.get('teams') or {}).items()}

    jugadores, descartados = [], {'sin_posicion': 0, 'sin_equipo': 0}
    # Se separan a propósito: los de posición rara NUNCA son jugadores (son los
    # entrenadores) y se pueden barrer del Excel sin pensarlo. Los que no tienen
    # club reconocible SÍ son jugadores de verdad a los que Biwenger no les
    # resuelve el equipo ese día, así que con esos hay que tener cuidado.
    entrenadores, sin_club = [], []
    global CAMPO_MULTIPOSICION, CAMPOS_DE_MUESTRA
    campos_multi = {}
    for bruto in (datos.get('players') or {}).values():
        if not CAMPOS_DE_MUESTRA or 'olmo' in str(bruto.get('name', '')).lower():
            CAMPOS_DE_MUESTRA = sorted(bruto.keys())
        posicion = POSICIONES.get(bruto.get('position'))
        if posicion is None:
            descartados['sin_posicion'] += 1
            entrenadores.append((bruto.get('name') or '').strip())
            continue
        equipo = equipos.get(bruto.get('teamID'))
        if not equipo:
            descartados['sin_equipo'] += 1
            sin_club.append((bruto.get('name') or '').strip())
            continue
        pj_casa = int(bruto.get('playedHome') or 0)
        pj_fuera = int(bruto.get('playedAway') or 0)
        pts_casa = int(bruto.get('pointsHome') or 0)
        pts_fuera = int(bruto.get('pointsAway') or 0)
        precio = int(bruto.get('price') or 0)
        extra, campos = _posiciones_extra(bruto)
        todas = sorted({bruto.get('position')} | extra)
        if len(todas) > 1:
            for campo in campos:
                campos_multi[campo] = campos_multi.get(campo, 0) + 1
        jugadores.append({
            'id': int(bruto.get('id')),
            'nombre': (bruto.get('name') or '').strip(),
            'equipo': equipo,
            'posicion': posicion,
            # La posición completa según Biwenger: «Defensa/Centrocampista» si le
            # deja las dos, «Defensa» si solo una.
            'posiciones': '/'.join(POSICIONES[p] for p in todas if p in POSICIONES),
            'puntos': int(bruto.get('points') or 0),
            'precio': precio,
            # priceIncrement es lo que ha subido o bajado HOY, así que el precio
            # de ayer es el de hoy menos ese incremento.
            'precio_ayer': precio - int(bruto.get('priceIncrement') or 0),
            'pj': pj_casa + pj_fuera,
            'pj_casa': pj_casa,
            'pj_fuera': pj_fuera,
            'pts_casa': pts_casa,
            'pts_fuera': pts_fuera,
            'goles': None,
            'asistencias': None,
            'estado': (bruto.get('status') or 'ok').strip().lower(),
        })
    CAMPO_MULTIPOSICION = max(campos_multi, key=campos_multi.get) if campos_multi else None
    return jugadores, {'equipos': equipos, 'descartados': descartados,
                       'entrenadores': sorted(n for n in entrenadores if n),
                       'sin_club': sorted(n for n in sin_club if n)}


def _media(puntos, pj):
    return round(puntos / pj, 2) if pj else 0


def escribir_export(wb, jugadores, info=None, hoja='Biwenger_Export', de_ayer=False):
    """Vuelca la lista en la hoja indicada y devuelve cuántas filas ha escrito.

    Reescribe la hoja entera: es un volcado del mercado de hoy, no un diario.
    Las filas sobrantes de un día con más jugadores se limpian para que no
    queden restos que luego lea nadie.
    """
    ws = wb[hoja] if hoja in wb.sheetnames else wb.create_sheet(hoja)
    filas_previas = ws.max_row

    for i, titulo in enumerate(COLUMNAS_EXPORT, start=1):
        ws.cell(1, i, titulo)

    for fila, j in enumerate(sorted(jugadores, key=lambda x: x['nombre']), start=2):
        precio = j['precio_ayer'] if de_ayer else j['precio']
        valores = [j['equipo'], j['nombre'], j['posicion'], j['puntos'], precio,
                   j['pj'], j['pj_casa'], j['pj_fuera'], _media(j['puntos'], j['pj']),
                   j['id'], j['pts_casa'], j['pts_fuera'],
                   j['goles'], j['asistencias'], j.get('estado', 'ok')]
        for c, v in enumerate(valores, start=1):
            ws.cell(fila, c, v)

    # ⚠️ LAS FILAS SOBRANTES SE BORRAN DE VERDAD, NO CON cell(f, c, None).
    # openpyxl solo asigna cuando el valor NO es None, así que ws.cell(f, c, None)
    # no borra nada: deja la celda como estaba. Por eso, al pasar de 550 jugadores
    # a 523, las 27 filas de más siguieron ahí con los datos de ayer, y como eran
    # las últimas del alfabeto (Yamal, Yeremay, Ángel Pérez...) el libro acabó con
    # 24 jugadores DUPLICADOS. Mercado_Global los busca con LOOKUP(2,1/…), que se
    # queda con la ÚLTIMA coincidencia, así que esos 24 cogían el valor de la
    # fila vieja: Ángel Pérez salía a 17,68 M€ e inflaba el valor de Nike en
    # 14 millones.
    ultima = len(jugadores) + 1
    if filas_previas > ultima:
        ws.delete_rows(ultima + 1, filas_previas - ultima)

    # Y se comprueba, que es barato y evita repetir la historia.
    claves = set()
    repetidos = []
    for fila in range(2, ws.max_row + 1):
        nombre = ws.cell(fila, 2).value
        if not nombre:
            continue
        clave = (str(nombre).strip(), str(ws.cell(fila, 1).value or '').strip())
        if clave in claves:
            repetidos.append(clave[0])
        claves.add(clave)
    if repetidos:
        raise RuntimeError(f"La hoja {hoja} ha quedado con {len(repetidos)} jugador/es "
                           f"repetidos ({', '.join(repetidos[:5])}). No se sigue: con "
                           "duplicados, los valores del Excel salen mal.")
    return len(jugadores)


# ---------------------------------------------------------------------------
# Goles y asistencias
# ---------------------------------------------------------------------------
# Dónde NO están: la ficha por jugador. Se comprobó con la sonda, y sus
# 'reports' solo devuelven si jugó en casa o fuera:
#     {"home": false}
#
# Dónde SÍ están: la jornada. rounds/la-liga devuelve los diez partidos y, en
# cada equipo, un 'reports' por jugador con sus 'events' y sus puntos. Así que
# los goles y las asistencias se acumulan recorriendo las jornadas jugadas, no
# preguntando jugador por jugador: 6 peticiones en vez de 550.
#
# QUÉ NÚMERO ES CADA COSA. La sonda contó los eventos de siete jornadas y sacó
# quién acumula más de cada tipo. Comparando esos nombres con las clasificaciones
# oficiales de LaLiga no queda duda:
#   · tipo 1 = GOL. 179 eventos (2,6 por partido) y arriba Mbappé, Roberto
#     Fernández, Raphinha, Aubameyang, Camello, Yamal: es el pichichi.
#   · tipo 3 = ASISTENCIA. 134 eventos (1,9 por partido) y arriba Mariano, Javi
#     Hernández, Gordon, Ángel Pérez, Bellingham, Vinícius: los mismos nombres y
#     en el mismo orden que la tabla oficial de asistentes.
# Los demás se reconocen por el reparto, y NO se cuentan: el 4 y el 5 son los
# cambios (674 cada uno, entran y salen), el 6 la tarjeta (295), y el 11 y el 12
# van emparejados de cuatro en cuatro entre delanteros y porteros, o sea penalti
# fallado y penalti parado.
#
# EL TIPO 2 SÍ CUENTA COMO GOL: es el penalti transformado, y Biwenger lo lleva
# aparte del tipo 1. Lo destapó comparar la primera tanda con la clasificación
# real: a Raphinha le faltaban goles (7 contando solo el tipo 1, cuando lleva 9)
# y justo tiene 3 eventos de tipo 2, siendo el lanzador del Barcelona. Arriba
# del tipo 2 están Budimir y Raphinha, o sea los que tiran los penaltis.
EVENTOS_GOL = (1, 2)
EVENTOS_ASISTENCIA = (3,)

URL_JORNADA_ACTUAL = 'https://cf.biwenger.com/api/v2/rounds/la-liga'
URL_JORNADA = 'https://cf.biwenger.com/api/v2/rounds/la-liga/{id}'


def _tipo_evento(evento):
    """El identificador del evento, venga como número o como texto."""
    if isinstance(evento, dict):
        return evento.get('type', evento.get('event'))
    return evento


def _cuantos(evento):
    if isinstance(evento, dict):
        for clave in ('quantity', 'amount', 'count', 'value'):
            if isinstance(evento.get(clave), int):
                return evento[clave]
    return 1


def recorrer_jornadas(registro=print):
    """(conteo por jugador y tipo de evento, jornadas leídas).

    Devuelve {id_jugador: {tipo: veces}}. No interpreta nada: solo cuenta. La
    interpretación (qué tipo es un gol) se decide arriba, en EVENTOS_GOL y
    EVENTOS_ASISTENCIA, y mientras esas listas estén vacías esto sirve para
    mirar, no para escribir.
    """
    actual = _pedir(URL_JORNADA_ACTUAL).get('data', {})
    temporada = actual.get('season') or {}
    jornadas = [r for r in (temporada.get('rounds') or [])
                if r.get('status') == 'finished' and r.get('id')]
    if not jornadas and actual.get('id'):
        jornadas = [{'id': actual['id'], 'name': actual.get('name')}]

    conteo, leidas, vistos, repetidos = {}, 0, set(), 0
    for jornada in jornadas:
        try:
            datos = _pedir(URL_JORNADA.format(id=jornada['id'])).get('data', {})
        except Exception as error:
            registro(f"No se pudo leer {jornada.get('name') or jornada['id']}: {error}")
            continue
        leidas += 1
        for partido in (datos.get('games') or []):
            # ⚠️ EL MISMO PARTIDO SALE EN DOS JORNADAS.
            # Cuando se aplaza una jornada, Biwenger publica una segunda entrada
            # ("Round 6 (postponed)") que vuelve a listar los partidos que YA se
            # jugaron en la primera. Se ve en los propios datos: dentro de esa
            # jornada aplazada, cada partido lleva su round con el id y el
            # nombre de la jornada original. Contando las dos, los goles de esos
            # partidos se apuntaban dos veces.
            id_partido = partido.get('id')
            if id_partido in vistos:
                repetidos += 1
                continue
            vistos.add(id_partido)
            for lado in ('home', 'away'):
                equipo = partido.get(lado) or {}
                for parte in (equipo.get('reports') or []):
                    jugador = (parte.get('player') or {}).get('id')
                    if not jugador:
                        continue
                    casilla = conteo.setdefault(int(jugador), {})
                    for evento in (parte.get('events') or []):
                        tipo = _tipo_evento(evento)
                        if tipo is None:
                            continue
                        casilla[tipo] = casilla.get(tipo, 0) + _cuantos(evento)
    if repetidos:
        registro(f"   ({repetidos} partido/s repetidos entre jornadas, contados una sola vez)")
    return conteo, leidas


# Los goles y asistencias de cada jugador en cada jornada de la última lectura:
# {(jornada, id_jugador): {tipo: veces}}. El bot los guarda en la hoja
# Eventos_Jornada para pintarlos en el «jornada a jornada» de Comparar.
ULTIMOS_EVENTOS_POR_JORNADA = {}


def rellenar_estadisticas(jugadores, registro=print):
    """Completa goles y asistencias de la lista de jugadores.

    Si todavía no se sabe qué tipo de evento es cada cosa, no toca nada y lo
    dice: los valores se quedan en None, que significa "no lo sé". La app
    conserva entonces lo que hubiera escrito a mano en Plantillas, en vez de
    machacarlo con ceros.
    """
    if not EVENTOS_GOL and not EVENTOS_ASISTENCIA:
        registro('Goles y asistencias: sin confirmar qué tipo de evento es cada '
                 'cosa, no se escribe nada (ejecuta sonda_jornada.py).')
        return 0

    # Una sola pasada por las jornadas: con el detalle por jornada se sacan
    # también los totales, y se ahorra leer dos veces todas las jornadas (que
    # es lo que más tarda de esta parte).
    por_jornada = eventos_por_jornada(registro)
    ULTIMOS_EVENTOS_POR_JORNADA.clear()
    ULTIMOS_EVENTOS_POR_JORNADA.update(por_jornada)
    conteo = {}
    for (_, id_jugador), tipos in por_jornada.items():
        casilla = conteo.setdefault(id_jugador, {})
        for tipo, veces in tipos.items():
            casilla[tipo] = casilla.get(tipo, 0) + veces
    leidas = len({jornada for jornada, _ in por_jornada})
    resueltos = 0
    for j in jugadores:
        casilla = conteo.get(j['id'])
        if casilla is None:
            # Ha jugado cero minutos en todas las jornadas leídas: cero goles.
            j['goles'] = j['asistencias'] = 0
            continue
        j['goles'] = sum(v for t, v in casilla.items() if t in EVENTOS_GOL)
        j['asistencias'] = sum(v for t, v in casilla.items() if t in EVENTOS_ASISTENCIA)
        resueltos += 1
    registro(f'Goles y asistencias: {leidas} jornada/s leídas, {resueltos} jugadores '
             'con eventos.')

    # El control de calidad: los diez primeros, para cotejarlos de un vistazo
    # con la tabla de goleadores. Si aquí falta un lanzador de penaltis
    # conocido, es que el tipo 2 va aparte y hay que sumarlo a EVENTOS_GOL.
    for etiqueta, clave in (('goleadores', 'goles'), ('asistentes', 'asistencias')):
        mejores = sorted((j for j in jugadores if j.get(clave)),
                         key=lambda x: -x[clave])[:10]
        registro(f"   {etiqueta}: " + ', '.join(f"{j['nombre']} {j[clave]}" for j in mejores))
    return resueltos


# ---------------------------------------------------------------------------
# Calendario y resultados
# ---------------------------------------------------------------------------

def descargar_calendario(registro=print, solo_proximas=None):
    """Todos los partidos de la temporada: [{jornada, local, visitante, fecha,
    goles_local, goles_visitante, estado}].

    La fecha se deja en None cuando Biwenger no la tiene puesta. Los partidos
    que aún no se han jugado vienen sin marcador, y también se devuelven: el
    calendario sirve para saber contra quién se juega, no solo lo que pasó.
    """
    actual = _pedir(URL_JORNADA_ACTUAL).get('data', {})
    temporada = actual.get('season') or {}
    jornadas = [r for r in (temporada.get('rounds') or []) if r.get('id')]
    if not jornadas and actual.get('id'):
        jornadas = [actual]
    # Modo rápido: solo la jornada en curso y las siguientes (para horarios y
    # resultados recientes), en vez de las 41 de la temporada.
    if solo_proximas and actual.get('id'):
        indice = next((i for i, r in enumerate(jornadas) if r.get('id') == actual.get('id')), None)
        if indice is not None:
            jornadas = jornadas[indice:indice + solo_proximas]

    registro(f'Calendario: leyendo {len(jornadas)} jornada/s, una petición cada una.'
             + ('' if solo_proximas else ' Tarda un par de minutos.'))
    partidos, vistos, fallos = [], set(), 0
    for numero, jornada in enumerate(jornadas, start=1):
        if numero % 5 == 0 or numero == len(jornadas):
            registro(f'   {numero} de {len(jornadas)} jornadas, '
                     f'{len(partidos)} partidos hasta ahora')
        try:
            datos = _pedir(URL_JORNADA.format(id=jornada['id'])).get('data', {})
        except Exception:
            fallos += 1
            continue
        for partido in (datos.get('games') or []):
            # El mismo partido aparece en la jornada normal y en la "postponed",
            # así que se cuenta una sola vez.
            if partido.get('id') in vistos:
                continue
            vistos.add(partido.get('id'))
            local, visitante = partido.get('home') or {}, partido.get('away') or {}
            if not local.get('name') or not visitante.get('name'):
                continue
            # La jornada la dice el propio partido: en una jornada aplazada, sus
            # partidos siguen siendo de la jornada original.
            nombre_ronda = ((partido.get('round') or {}).get('name')
                            or jornada.get('name') or '')
            partidos.append({
                'jornada': _numero_de_jornada(nombre_ronda),
                'local': str(local.get('name')).strip(),
                'visitante': str(visitante.get('name')).strip(),
                'fecha': partido.get('date'),
                'goles_local': local.get('score'),
                'goles_visitante': visitante.get('score'),
                'estado': partido.get('status'),
            })
    registro(f'Calendario: {len(partidos)} partidos de {len(jornadas)} jornadas'
             + (f' ({fallos} jornada/s no se pudieron leer)' if fallos else ''))
    return partidos


def _numero_de_jornada(nombre):
    for trozo in str(nombre or '').replace('(', ' ').split():
        if trozo.isdigit():
            return int(trozo)
    return None


def eventos_por_jornada(registro=print):
    """{(jornada, id_jugador): {tipo: veces}} — los eventos SIN agregar.

    recorrer_jornadas() suma toda la temporada, y eso sirve para escribir el
    total en el Excel pero no para medir nada: para saber si los goles predicen
    el rendimiento futuro hay que saber cuántos llevaba cada jugador ANTES de
    cada jornada, no cuántos lleva hoy. Usar el total de hoy para explicar un
    partido de agosto es mirar el futuro, y las métricas saldrían infladas.
    """
    actual = _pedir(URL_JORNADA_ACTUAL).get('data', {})
    temporada = actual.get('season') or {}
    jornadas = [r for r in (temporada.get('rounds') or [])
                if r.get('status') == 'finished' and r.get('id')] or [actual]

    conteo, vistos = {}, set()
    for jornada in jornadas:
        try:
            datos = _pedir(URL_JORNADA.format(id=jornada['id'])).get('data', {})
        except Exception:
            continue
        for partido in (datos.get('games') or []):
            if partido.get('id') in vistos:
                continue
            vistos.add(partido.get('id'))
            numero = _numero_de_jornada((partido.get('round') or {}).get('name')
                                        or jornada.get('name'))
            for lado in ('home', 'away'):
                for parte in ((partido.get(lado) or {}).get('reports') or []):
                    jugador = (parte.get('player') or {}).get('id')
                    if not jugador or numero is None:
                        continue
                    casilla = conteo.setdefault((numero, int(jugador)), {})
                    for evento in (parte.get('events') or []):
                        tipo = _tipo_evento(evento)
                        if tipo is not None:
                            casilla[tipo] = casilla.get(tipo, 0) + _cuantos(evento)
    registro(f'Eventos por jornada: {len(conteo)} fichas de {len(jornadas)} jornadas')
    return conteo
