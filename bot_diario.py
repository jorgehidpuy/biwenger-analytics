# -*- coding: utf-8 -*-
"""Actualiza la base de datos biwenger.db sola, sin abrir la app ni pulsar botones.

Qué hace, en orden:

  1. Se identifica en Biwenger y consigue un token nuevo (no uno pegado a mano,
     que caduca a los pocos días y deja el bot muerto en silencio).
  2. Descarga la base de datos pública de La Liga y rellena Biwenger_Export y
     Biwenger_Ayer. El precio de ayer NO hace falta guardarlo de un día para
     otro: sale de restar el incremento diario que da el propio servidor.
  3. Lee el tablón privado de la liga y añade a Contabilidad las compras, ventas
     y abonos que no estuvieran ya, con las PUJAS PERDIDAS de cada compra.
  4. Ejecuta los mismos procesos que los botones de la app: importar el día al
     Histórico, repartir casa/fuera y poner las plantillas al día.

Todo se guarda en biwenger.db (ver almacen.py); los cálculos que antes hacían
las fórmulas del Excel están en calculos.py.

Las pujas perdidas NO hace falta pagarlas. La web cobra una moneda por
enseñarlas, pero el tablón las trae igual, pagues o no: comprobado el
20/09/2026 con Osorio (no se pagó y su puja salió), y las 72 subastas ajenas
que se apuntaron a mano estaban todas en el tablón. Lo ya apuntado no se pisa:
si algún importe no coincide con Biwenger, el log lo avisa.

Uso:
    python bot_diario.py

Credenciales: se leen de config_bot.json, que debe estar junto a este archivo y
NO debe subirse a ningún sitio:

    {"email": "tu@correo.com", "password": "tu_contraseña"}
"""

import difflib
import json
import time
import os
import runpy
import sys
import types
import unicodedata
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api_biwenger
import almacen

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_CONFIG = os.path.join(CARPETA, "config_bot.json")
# Los datos viven en biwenger.db (ver almacen.py). La variable conserva el
# nombre de cuando eran un Excel para no tocar las decenas de sitios que la usan.
RUTA_EXCEL = almacen.RUTA_DB
RUTA_APP = os.path.join(CARPETA, "app.py")
RUTA_LOG = os.path.join(CARPETA, "bot_diario.log")

URL_PUBLICA = "https://cf.biwenger.com/api/v2/competitions/la-liga/data?lang=es&score=2"
URL_LOGIN = "https://biwenger.as.com/api/v2/auth/login"
URL_CUENTA = "https://biwenger.as.com/api/v2/account"
URL_TABLON = "https://biwenger.as.com/api/v2/home"

NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Las posiciones y las columnas del export viven ahora en api_biwenger.py, que
# es quien descarga y quien escribe: tenerlas en dos sitios era pedir que un día
# dejaran de coincidir.
POSICIONES = api_biwenger.POSICIONES

# Con lo que empieza cada mánager. Está en la fórmula del saldo de la hoja
# Participantes, así que el abono que Biwenger publica el día del sorteo no
# debe apuntarse: ya está contado.
SALDO_INICIAL_LIGA = 50_000_000


def aviso(texto):
    """Escribe por pantalla y en el log, volcando a disco de inmediato.

    Sin el volcado inmediato, si el proceso se muere de golpe se pierden las
    últimas líneas y el log se queda cortado justo donde estaba el problema,
    que es exactamente lo que pasó la primera vez.
    """
    linea = f"[{datetime.now():%d/%m/%Y %H:%M:%S}] {texto}"
    try:
        print(linea)
    except Exception:
        pass
    try:
        with open(RUTA_LOG, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass


# ----------------------------------------------------------------------------
# 1. Conexión
# ----------------------------------------------------------------------------

def leer_credenciales():
    if not os.path.exists(RUTA_CONFIG):
        raise SystemExit(
            f"Falta {RUTA_CONFIG}. Crea ese archivo con este contenido:\n"
            '   {"email": "tu@correo.com", "password": "tu_contraseña"}')
    with open(RUTA_CONFIG, encoding="utf-8") as f:
        datos = json.load(f)
    if not datos.get("email") or not datos.get("password"):
        raise SystemExit("config_bot.json necesita 'email' y 'password'.")
    return datos["email"], datos["password"]


def abrir_sesion():
    """(cabeceras con token fresco, id de liga). El token caduca, así que se
    pide uno nuevo en cada ejecución en vez de dejarlo escrito en el código."""
    email, password = leer_credenciales()
    cabeceras = {"User-Agent": NAVEGADOR, "Content-Type": "application/json"}

    respuesta = requests.post(URL_LOGIN, json={"email": email, "password": password},
                              headers=cabeceras, timeout=30)
    respuesta.raise_for_status()
    token = respuesta.json().get("token")
    if not token:
        raise SystemExit("Biwenger no ha devuelto token: revisa el correo y la contraseña.")
    cabeceras["Authorization"] = f"Bearer {token}"

    cuenta = requests.get(URL_CUENTA, headers=cabeceras, timeout=30).json()
    ligas = cuenta.get("data", {}).get("leagues") or []
    if not ligas:
        raise SystemExit("La cuenta no tiene ninguna liga.")
    liga = ligas[0]
    cabeceras["X-League"] = str(liga["id"])
    cabeceras["X-User"] = str(liga.get("user", {}).get("id") or cuenta["data"]["id"])
    aviso(f"Conectado a «{liga.get('name')}» como usuario {cabeceras['X-User']}.")
    return cabeceras


# ----------------------------------------------------------------------------
# 2. Mercado
# ----------------------------------------------------------------------------

def descargar_mercado():
    """(lista de jugadores limpia, mapa de equipos, índice por id).

    La descarga y el filtrado viven en api_biwenger.py: es el mismo código que
    escribe las hojas, así que no puede haber dos criterios distintos sobre qué
    es un jugador.

    Lo que se filtra, y por qué importa:
      · ENTRENADORES. Vienen en el mismo JSON que los jugadores, con una
        posición que no es 1-4, y caían en el "Centrocampista" por defecto.
        Ahora mismo hay once en tu Excel (Flick, Mourinho, Simeone, Pellegrini,
        Bordalás…), y contaminan medias, calibraciones y onces ideales.
      · JUGADORES SIN CLUB RECONOCIBLE. Entraban con equipo "Desconocido" y
        disparaban falsos traspasos que reescribían fichas buenas.
    """
    jugadores, info = api_biwenger.descargar_jugadores()
    descartados = info["descartados"]
    aviso(f"Mercado descargado: {len(jugadores)} jugadores "
          f"({descartados['sin_posicion']} descartados por no tener posición de "
          f"jugador —entrenadores— y {descartados['sin_equipo']} sin club reconocible).")
    return jugadores, info["equipos"], {j["id"]: j for j in jugadores}


# ----------------------------------------------------------------------------
# 2b. Multiposición: la que diga Biwenger
# ----------------------------------------------------------------------------
# Biwenger deja alinear a algunos jugadores en dos o tres posiciones y cambia
# esa lista cuando quiere (a Eric García le quitó la de medio). Hasta ahora eso
# se copiaba a mano en la hoja Multiposicion, que se quedaba desfasada. Ahora
# api_biwenger lo lee en la misma descarga de jugadores de cada mañana y aquí se
# reescribe la hoja con lo que diga Biwenger en cada actualización.
#
# Con red de seguridad: si Biwenger no trae posiciones alternativas donde se
# esperan, la hoja NO se toca y se deja en el log qué campos trae, para poder
# ajustarlo. Una hoja manual correcta es mejor que una vacía.
MIN_MULTIPOSICIONES_FIABLES = 10     # menos que esto en toda La Liga sería un dato roto


def descargar_multiposiciones(jugadores):
    """{id de Biwenger: "Defensa/Centrocampista"} con los jugadores que Biwenger
    deja alinear en más de una posición, o None si no se ha podido saber.

    Sale de la MISMA descarga de jugadores de api_biwenger (que lee todos los
    campos de posición de cada uno). La primera versión hacía su propia
    petición sin identificarse como navegador, y Biwenger le devolvía una
    respuesta vacía: por eso no funcionaba."""
    posiciones = {int(j["id"]): j["posiciones"] for j in jugadores
                  if j.get("id") is not None and "/" in str(j.get("posiciones") or "")}
    if len(posiciones) < MIN_MULTIPOSICIONES_FIABLES:
        aviso(f"AVISO Multiposición: Biwenger no trae posiciones alternativas donde se esperaban "
              f"({len(posiciones)} jugadores con varias). La hoja Multiposicion no se toca. "
              f"Campos que trae cada jugador: {getattr(api_biwenger, 'CAMPOS_DE_MUESTRA', '?')}")
        return None
    aviso(f"Multiposición de Biwenger: {len(posiciones)} jugadores con varias posiciones "
          f"(campo «{getattr(api_biwenger, 'CAMPO_MULTIPOSICION', '?')}»).")
    return posiciones


def escribir_eventos_jornada(wb, jugadores):
    """La hoja Eventos_Jornada: goles y asistencias de cada jugador en cada
    jornada, para los iconos del «jornada a jornada» de Comparar. Se reescribe
    entera en cada actualización porque Biwenger da la temporada completa."""
    eventos = getattr(api_biwenger, "ULTIMOS_EVENTOS_POR_JORNADA", None)
    if not eventos:
        aviso("Eventos por jornada: sin datos de esta lectura, la hoja no se toca.")
        return
    quien = {int(j["id"]): (j["nombre"], j["equipo"]) for j in jugadores if j.get("id") is not None}
    filas = []
    for (jornada, ident), tipos in eventos.items():
        goles = sum(v for t, v in tipos.items() if t in api_biwenger.EVENTOS_GOL)
        asistencias = sum(v for t, v in tipos.items() if t in api_biwenger.EVENTOS_ASISTENCIA)
        if (goles or asistencias) and ident in quien:
            filas.append((jornada, *quien[ident], goles, asistencias))
    ws = wb["Eventos_Jornada"] if "Eventos_Jornada" in wb.sheetnames else wb.create_sheet("Eventos_Jornada")
    if ws.max_row:
        ws.delete_rows(1, ws.max_row)
    ws.append(["Jornada", "Jugador", "Equipo", "Goles", "Asistencias"])
    for fila in sorted(filas):
        ws.append(list(fila))
    aviso(f"Eventos por jornada: {len(filas)} filas de goles y asistencias en "
          f"{len({f[0] for f in filas})} jornadas.")


def aplicar_multiposiciones(wb, jugadores, posiciones):
    """Deja en el Excel la multiposición que dice Biwenger.

      · Biwenger_Export gana una columna «Posiciones» con la posición completa
        de cada jugador («Defensa/Centrocampista» o solo «Defensa»). La app la
        usa tal cual.
      · La hoja Multiposicion se reescribe con los que tienen varias
        (calculos.mercado_global la consulta para la posición del mercado)."""
    if not posiciones:
        return
    principal = {int(j["id"]): j.get("posicion") for j in jugadores if j.get("id") is not None}
    nombre = {int(j["id"]): j.get("nombre") for j in jugadores if j.get("id") is not None}

    if "Biwenger_Export" in wb.sheetnames:
        ws = wb["Biwenger_Export"]
        cabecera = {str(c.value).strip(): c.column for c in ws[1] if c.value}
        if "ID" in cabecera:
            col = cabecera.get("Posiciones") or ws.max_column + 1
            ws.cell(1, col, "Posiciones")
            for fila in range(2, ws.max_row + 1):
                try:
                    ident = int(ws.cell(fila, cabecera["ID"]).value)
                except (TypeError, ValueError):
                    continue
                ws.cell(fila, col, posiciones.get(ident) or principal.get(ident))

    if "Multiposicion" not in wb.sheetnames:
        return
    ws = wb["Multiposicion"]
    antes = {str(a).strip(): str(b).strip() for a, b in ws.iter_rows(min_row=2, max_col=2, values_only=True)
             if a and b}
    ahora = {nombre[i]: p for i, p in posiciones.items() if nombre.get(i)}
    for fila in range(2, ws.max_row + 1):
        ws.cell(fila, 1).value = None
        ws.cell(fila, 2).value = None
    for fila, jugador in enumerate(sorted(ahora), start=2):
        ws.cell(fila, 1, jugador)
        ws.cell(fila, 2, ahora[jugador])

    cambios = []
    principal_por_nombre = {nombre[i]: principal.get(i) for i in nombre}
    for jugador in sorted(set(antes) | set(ahora)):
        viejo, nuevo = antes.get(jugador), ahora.get(jugador)
        if viejo == nuevo:
            continue
        if nuevo is None:
            cambios.append(f"{jugador}: ya solo {principal_por_nombre.get(jugador) or '?'} (tenía {viejo})")
        elif viejo is None:
            cambios.append(f"{jugador}: ahora {nuevo}")
        else:
            cambios.append(f"{jugador}: {viejo} → {nuevo}")
    aviso(f"Multiposicion al día con Biwenger: {len(ahora)} jugadores, {len(cambios)} cambio/s.")
    for linea in cambios[:20]:
        aviso(f"   · {linea}")


# ----------------------------------------------------------------------------
# 3. Tablón de la liga
# ----------------------------------------------------------------------------

def descargar_movimientos(cabeceras, por_id, personas, pujas=None):
    """Compras, ventas y abonos del tablón, listos para Contabilidad.

    Si se pasa una lista en `pujas`, se rellena con las pujas perdidas de cada
    compra (una entrada por compra, las tenga o no). Es opcional para que
    cualquier otro script que llame a esta función siga funcionando igual.

    El valor de mercado se toma del precio de HOY, que es correcto mientras el
    bot corra a diario: un fichaje de esta madrugada se valora con el precio de
    esta mañana. Si se deja de ejecutar varios días, las sobrepujas de los
    movimientos atrasados saldrán algo desviadas, y eso importa porque la
    sobrepuja es lo que aprende el predictor de pujas.
    """
    # Biwenger ha ido moviendo de sitio el historial de fichajes, así que se
    # prueban varias rutas y nos quedamos con la que traiga movimientos de
    # dinero. Se deja constancia en el log de qué devuelve cada una: si un día
    # vuelven a cambiarlo, el propio log dirá dónde buscar.
    id_liga = cabeceras.get("X-League", "")
    rutas = [
        # 200 en vez de 50: con 50 eventos solo se ven unos días, y los abonos
        # de una jornada que se cierra tarde (o una ejecución que se salta un
        # día) quedaban por debajo del corte y no se recuperaban nunca. El
        # antiduplicados y el corte por fecha se encargan de lo repetido.
        f"https://biwenger.as.com/api/v2/league/{id_liga}/board?limit=200",
        f"https://biwenger.as.com/api/v2/league/{id_liga}/board?limit=50",
        "https://biwenger.as.com/api/v2/league/board?limit=50",
        f"{URL_TABLON}?limit=50",
    ]

    eventos, ruta_buena = [], ""
    for ruta in rutas:
        try:
            respuesta = requests.get(ruta, headers=cabeceras, timeout=30)
            cuerpo = respuesta.json()
        except Exception as error:
            aviso(f"   ruta {ruta.split('/api/v2/')[-1][:40]} -> error: {error}")
            continue

        datos = cuerpo.get("data")
        if isinstance(datos, list):
            candidatos = datos
        elif isinstance(datos, dict):
            candidatos = datos.get("events") or []
        else:
            candidatos = []

        tipos = sorted({str(e.get("type")) for e in candidatos if isinstance(e, dict)})
        aviso(f"   ruta …{ruta.split('/api/v2/')[-1][:44]} -> "
              f"{len(candidatos)} evento/s {tipos if tipos else ''}")

        if any(str(e.get("type")) in ("transfers", "transfer", "market", "bonus")
               for e in candidatos if isinstance(e, dict)):
            eventos, ruta_buena = candidatos, ruta
            break
        if candidatos and not eventos:
            eventos, ruta_buena = candidatos, ruta   # algo es algo

    if not eventos:
        aviso("   ninguna ruta devolvió eventos.")
        # Dos listas vacías, no una: quien llama espera (movimientos, abonos), y
        # con [] el bot entero se paraba sin actualizar nada más.
        return [], []

    # 📜 SEGUIR HACIA ATRÁS HASTA EL PRINCIPIO DE LA LIGA.
    # Una sola tanda de 200 eventos solo llega al 15 de agosto, y la liga
    # empezó el 1. Todo lo anterior —las subastas del arranque, los primeros
    # abonos— quedaba fuera, así que el cuadre de saldos no podía verlo y
    # cualquier movimiento mal apuntado de esos días era invisible. Se pide
    # página a página con offset hasta que el tablón se acaba.
    if "offset" not in ruta_buena:
        pagina, tope = len(eventos), 12
        while tope > 0:
            tope -= 1
            try:
                respuesta = requests.get(f"{ruta_buena}&offset={pagina}",
                                         headers=cabeceras, timeout=30)
                datos = respuesta.json().get("data")
            except Exception as error:
                aviso(f"   paginando: se corta en {pagina} ({error})")
                break
            mas = datos if isinstance(datos, list) else (datos or {}).get("events") or []
            if not mas:
                break
            eventos.extend(mas)
            pagina += len(mas)
        aviso(f"   tablón completo: {len(eventos)} evento/s")

    movimientos = []
    descartados_tablon = []
    abonos_jornada = []
    sin_traducir = []
    for evento in eventos:
        tipo = evento.get("type")
        marca = evento.get("date")
        if not marca:
            continue
        # Objeto fecha, NO texto: la columna A del Excel guarda fechas de verdad
        # y escribir "15/09/2026" como cadena reventaría al leerlas (ya pasó con
        # las fechas de 1900). Sin hora, para que cuadre con lo ya registrado.
        fecha = datetime.fromtimestamp(marca).replace(hour=0, minute=0, second=0,
                                                      microsecond=0)

        if tipo in ("transfers", "transfer", "market"):
            contenido = evento.get("content") or []
            if isinstance(contenido, dict):
                contenido = [contenido]
            if not contenido and evento.get("player"):
                contenido = [evento]

            for traspaso in contenido:
                try:
                    id_jugador = int(traspaso.get("player"))
                except (TypeError, ValueError):
                    continue
                # Si no está en el índice es porque el filtro lo descartó: un
                # entrenador o alguien sin club. No entra a Contabilidad.
                info = por_id.get(id_jugador)
                if not info:
                    descartados_tablon.append(str(traspaso.get("player")))
                    continue
                nombre = info["nombre"]
                equipo = info["equipo"]
                posicion = info["posicion"]
                importe = traspaso.get("amount", 0) or 0
                valor = info["precio"]
                sobrepuja = importe - valor

                destino = traspaso.get("to")
                origen = traspaso.get("from")
                comprador = personas.traducir(destino.get("name")) if isinstance(destino, dict) else None
                vendedor = personas.traducir(origen.get("name")) if isinstance(origen, dict) else None
                # ⚠️ Si el nombre no es uno de los diez del Excel, NO se escribe.
                # Escribirlo tal cual crea un mánager fantasma y parte su saldo
                # en dos: pasó con "NIKE FC (MUNDIAL 🏅)", que se llevó 52 M€ a
                # una persona que no existe.
                for quien in (comprador, vendedor):
                    if quien and not personas.es_valido(quien):
                        sin_traducir.append(quien)
                if comprador and not personas.es_valido(comprador):
                    comprador = None
                if vendedor and not personas.es_valido(vendedor):
                    vendedor = None

                if comprador:
                    movimientos.append([fecha, comprador, "Compra", nombre, equipo,
                                        posicion, importe, valor, sobrepuja])
                    # Las pujas perdidas van aparte y SIN el corte por fecha que
                    # se aplica luego a los movimientos: así también se
                    # completan compras antiguas a las que les faltan.
                    if pujas is not None:
                        pujas.append(_pujas_de_subasta(fecha, comprador, nombre,
                                                       importe, traspaso, personas))
                if vendedor:
                    # 💶 Una venta no tiene sobrepuja: se cobra el valor de
                    # mercado y ya. La diferencia entre el importe y el precio de
                    # hoy es solo lo que se movió el precio desde la venta.
                    movimientos.append([fecha, vendedor, "Venta", nombre, equipo,
                                        posicion, importe, valor, 0])

        elif tipo == "roundFinished":
            # 💶 LOS ABONOS DE JORNADA NO SON MOVIMIENTOS, SON ESTADO.
            # Se apartan aquí y los cuadra sincronizar_abonos(), porque una
            # jornada puede pagarse DOS VECES: cuando se aplaza, Biwenger da un
            # abono provisional con lo jugado hasta ese momento y, al
            # completarse, lo RECTIFICA con el definitivo. La jornada 6 pagó
            # 400.000 € y luego 2.300.000 €, y sumando los dos el saldo del
            # Excel se quedaba 400.000 € por encima del real.
            contenido = evento.get("content") or {}
            ronda = contenido.get("round") or {}
            for resultado in (contenido.get("results") or []):
                quien = resultado.get("user") or {}
                persona = personas.traducir(quien.get("name"))
                if persona and not personas.es_valido(persona):
                    sin_traducir.append(persona)
                    continue
                if persona:
                    abonos_jornada.append({
                        "fecha": fecha, "persona": persona,
                        "jornada": _numero_jornada(ronda.get("name")),
                        "nombre": (ronda.get("name") or "").strip(),
                        "importe": resultado.get("bonus") or 0,
                        "puntos": resultado.get("points") or 0,
                    })

        elif tipo == "bonus":
            contenido = evento.get("content") or []
            if isinstance(contenido, dict):
                contenido = [contenido]
            if not contenido and evento.get("amount"):
                contenido = [evento]
            for abono in contenido:
                quien = abono.get("user") or abono.get("to") or {}
                persona = personas.traducir(quien.get("name")) if isinstance(quien, dict) else None
                if persona and not personas.es_valido(persona):
                    sin_traducir.append(persona)
                    persona = None
                importe = abono.get("amount", 0) or 0
                # 🏦 El saldo de salida de la liga viaja por el tablón como un
                # abono de 50 millones el día que arrancó. El Excel ya lo tiene
                # metido en la propia fórmula del saldo ("50000000 + ventas -
                # compras + abonos"), así que apuntarlo otra vez le daría a todo
                # el mundo 50 millones de más.
                if importe == SALDO_INICIAL_LIGA:
                    continue
                if persona and importe:
                    movimientos.append([fecha, persona, "Abono", None, None,
                                        None, importe, None, None])

    movimientos.sort(key=lambda m: m[0])      # del más antiguo al más reciente
    aviso(f"Tablón leído: {len(movimientos)} movimiento/s encontrados.")
    if abonos_jornada:
        jornadas = sorted({a["nombre"] for a in abonos_jornada})
        aviso(f"   abonos de jornada encontrados: {', '.join(jornadas)}")
    if descartados_tablon:
        aviso(f"   ({len(descartados_tablon)} movimiento/s ignorados: el jugador no "
              "está en el mercado filtrado)")
    if sin_traducir:
        nombres = sorted(set(sin_traducir))
        aviso("   AVISO SERIO: no he sabido a qué mánager del Excel corresponden "
              f"estos nombres, así que sus movimientos NO se apuntan: {', '.join(nombres)}. "
              "Revisa la hoja Participantes.")
    return movimientos, abonos_jornada


def _numero_jornada(nombre):
    """El número de la jornada, para que «Round 6» y «Round 6 (postponed)» sean
    LA MISMA. Son dos entradas distintas en Biwenger (ids 4904 y 5125) pero un
    solo reparto: el segundo sustituye al primero, no se suma."""
    for trozo in str(nombre or "").replace("(", " ").split():
        if trozo.isdigit():
            return int(trozo)
    return None


def sincronizar_abonos(wb, abonos, personas):
    """Deja en Contabilidad UN abono por mánager y jornada, con el importe bueno.

    Un abono de jornada no es un apunte que llega y se queda: es el estado de
    esa jornada, y puede cambiar. Por eso no se añaden sin más (se duplicarían
    con cada rectificación) sino que se cuadran: cada jornada tiene una fila por
    mánager y, si Biwenger cambia la cifra, se corrige esa fila en vez de
    apuntar otra.

    La jornada se escribe en la columna Jugador ("Jornada 6"), que en un abono
    estaba vacía. Así se sabe a qué jornada pertenece cada fila, que era justo
    lo que faltaba para poder rectificarlas.
    """
    if not abonos or "Contabilidad" not in wb.sheetnames:
        return 0, 0, []

    hoja = wb["Contabilidad"]

    # Lo definitivo de cada jornada: el ÚLTIMO evento manda. Pero se guardan
    # TAMBIÉN los importes provisionales, porque son los que hay escritos en el
    # Excel de antes: la jornada 6 se apuntó con los 400.000 € del pago
    # provisional, y sin conocer esa cifra no habría manera de reconocer esa
    # fila para rectificarla.
    definitivo, historial = {}, {}
    for abono in sorted(abonos, key=lambda a: a["fecha"]):
        if abono["jornada"] is None:
            continue
        clave = (abono["persona"], abono["jornada"])
        definitivo[clave] = abono
        historial.setdefault(clave, []).append((abono["importe"], abono["fecha"]))

    # Lo que ya hay: primero las filas etiquetadas, luego las antiguas sin
    # etiqueta, que se emparejan por importe.
    etiquetadas, sueltas = {}, []
    ultima = 1
    for fila in range(2, hoja.max_row + 1):
        persona = hoja.cell(fila, 2).value
        if not persona or not hoja.cell(fila, 3).value:
            continue
        ultima = fila
        if str(hoja.cell(fila, 3).value).strip() != "Abono":
            continue
        etiqueta = str(hoja.cell(fila, 4).value or "").strip()
        persona = str(persona).strip()
        numero = _numero_jornada(etiqueta) if etiqueta.lower().startswith("jornada") else None
        if numero is not None:
            etiquetadas[(persona, numero)] = fila
        else:
            sueltas.append((fila, persona, float(hoja.cell(fila, 7).value or 0),
                            hoja.cell(fila, 1).value))

    nuevos = corregidos = 0
    detalle = []

    for clave, abono in sorted(definitivo.items(), key=lambda x: (x[0][1], x[0][0])):
        persona, numero = clave
        fila = etiquetadas.get(clave)

        if fila is None:
            # ¿Es uno de los abonos viejos sin etiquetar? Se empareja por
            # importe dentro del mismo mánager, contra CUALQUIER cifra que esa
            # jornada haya pagado, provisional incluida.
            # Emparejar un abono viejo con su jornada tiene dos pasos, y el
            # orden importa. Primero el importe Y la fecha, que es lo seguro.
            # Si eso no encuentra nada, el importe a secas, siempre que sea
            # único entre los abonos sin etiquetar de ese mánager.
            #
            # Hizo falta el segundo paso porque las fechas escritas a mano no
            # son las del pago: el abono de 3.100.000 € estaba apuntado el
            # 20/08 y Biwenger lo pagó el 28/08, ocho días después. Exigiendo
            # una semana no casaba, se daba por nuevo y se apuntaba OTRA VEZ.
            posibles = historial.get(clave, [(abono["importe"], abono["fecha"])])
            candidatas = []
            for f, p, imp, cuando in sueltas:
                if p != persona:
                    continue
                for importe_pago, fecha_pago in posibles:
                    if abs(imp - importe_pago) >= 1:
                        continue
                    if hasattr(cuando, "toordinal") and hasattr(fecha_pago, "toordinal"):
                        candidatas.append((abs(cuando.toordinal() - fecha_pago.toordinal()), f))
                    else:
                        candidatas.append((999, f))
            candidatas.sort()
            cercanas = [c for c in candidatas if c[0] <= 7]
            por_importe = {f for _, f in candidatas}
            if len(cercanas) == 1 or (len(cercanas) > 1 and cercanas[0][0] < cercanas[1][0]):
                fila = cercanas[0][1]
            elif len(por_importe) == 1:
                fila = candidatas[0][1]

            if fila is not None:
                sueltas = [s for s in sueltas if s[0] != fila]
                hoja.cell(fila, 4).value = f"Jornada {numero}"
                etiquetadas[clave] = fila
                # y si lo que había era el pago provisional, se rectifica ya.
                previo = float(hoja.cell(fila, 7).value or 0)
                if abs(previo - abono["importe"]) >= 1:
                    hoja.cell(fila, 7).value = abono["importe"]
                    hoja.cell(fila, 1).value = abono["fecha"]
                    corregidos += 1
                    detalle.append(f"Jornada {numero} · {persona}: {previo:,.0f} € → "
                                   f"{abono['importe']:,.0f} € (era el pago provisional "
                                   "de la jornada aplazada)".replace(",", "."))
                continue

        if fila is None:
            ultima += 1
            fila = ultima
            valores = [abono["fecha"], persona, "Abono", f"Jornada {numero}",
                       None, None, abono["importe"], None, None]
            for columna, valor in enumerate(valores, 1):
                celda = hoja.cell(fila, columna, valor)
                if columna == 1:
                    celda.number_format = "DD/MM/YYYY"
            etiquetadas[clave] = fila
            nuevos += 1
            detalle.append(f"Jornada {numero} · {persona}: {abono['importe']:,.0f} €"
                           .replace(",", "."))
            continue

        actual = float(hoja.cell(fila, 7).value or 0)
        if abs(actual - abono["importe"]) >= 1:
            hoja.cell(fila, 7).value = abono["importe"]
            corregidos += 1
            detalle.append(f"Jornada {numero} · {persona}: {actual:,.0f} € → "
                           f"{abono['importe']:,.0f} € (rectificado por Biwenger)"
                           .replace(",", "."))

    # 🧹 DUPLICADOS DE UNA EJECUCIÓN ANTERIOR.
    # Mientras el emparejado exigía que la fecha cuadrara en una semana, las
    # jornadas que no casaban se apuntaban como nuevas y quedaron DOS filas
    # para el mismo reparto: la de siempre, sin etiqueta, y la recién añadida
    # con «Jornada N». Si una fila etiquetada tiene una gemela sin etiquetar
    # del mismo mánager, con un importe que esa jornada pagó y una fecha
    # cercana, la gemela sobra.
    limpiadas = 0
    for (persona, numero), fila in list(etiquetadas.items()):
        importe_bueno = float(hoja.cell(fila, 7).value or 0)
        fecha_buena = hoja.cell(fila, 1).value
        pagos = [imp for imp, _ in historial.get((persona, numero), [])]
        # Tope de seguridad: una jornada paga una vez, o dos si se aplazó. Más
        # gemelas que pagos significa que estoy borrando algo que no es de esta
        # jornada, así que se para.
        quitadas_aqui, tope_gemelas = 0, max(1, len(set(pagos)))
        for f, p, imp, cuando in list(sueltas):
            if quitadas_aqui >= tope_gemelas:
                break
            if p != persona or not any(abs(imp - x) < 1 for x in pagos):
                continue
            cerca = (hasattr(cuando, "toordinal") and hasattr(fecha_buena, "toordinal")
                     and abs(cuando.toordinal() - fecha_buena.toordinal()) <= 20)
            if not cerca:
                continue
            for columna in range(1, 10):
                hoja.cell(f, columna).value = None
            sueltas = [s for s in sueltas if s[0] != f]
            limpiadas += 1
            quitadas_aqui += 1
            detalle.append(f"Jornada {numero} · {persona}: quitada una fila repetida "
                           f"de {imp:,.0f} € (fila {f})".replace(",", "."))
            # Sin break: una jornada pagada dos veces deja DOS gemelas, la del
            # pago provisional y la del definitivo. Cortando en la primera se
            # quedaba la otra, y eso era justo el abono de 2.300.000 € que
            # sobraba en el saldo.
    if limpiadas:
        corregidos += limpiadas

    # Los abonos viejos que no casan con ninguna jornada se dejan en paz: son
    # otra cosa (premios sueltos, penalizaciones) y borrarlos sería peor.
    if sueltas:
        detalle.append(f"{len(sueltas)} abono/s antiguos sin jornada reconocible, "
                       "se quedan como están")
    return nuevos, corregidos, detalle


# ----------------------------------------------------------------------------
# 3 bis. Nombres de mánager
# ----------------------------------------------------------------------------

PALABRAS_DE_RELLENO = {'fc', 'cf', 'cd', 'sad', 'club', 'de', 'del', 'la', 'el',
                       'los', 'las', 'ud', 'sd', 'rc', 'ac'}


def _palabras(texto):
    """El nombre reducido a sus palabras con significado.

    Quita acentos, mayúsculas, puntuación, EMOJIS y las palabrejas de club. El
    emoji importa: "NIKE FC (MUNDIAL 🏅)" se quedaba en "nike (mundial )" y no
    se parecía lo bastante a "Nike", así que no se traducía y sus movimientos
    entraban en Contabilidad bajo un mánager inventado con 52 millones de saldo.
    """
    limpio = unicodedata.normalize('NFKD', str(texto or ''))
    limpio = limpio.encode('ascii', 'ignore').decode().lower()
    limpio = ''.join(c if c.isalnum() else ' ' for c in limpio)
    return {p for p in limpio.split() if p and p not in PALABRAS_DE_RELLENO}


def _parecido(origen, candidato):
    """0 a 1. Mide dos cosas: cuánto del nombre de Biwenger explica el candidato
    y cuánto del candidato aparece en el nombre de Biwenger."""
    a, b = _palabras(origen), _palabras(candidato)
    if not a or not b:
        return 0.0
    comunes = len(a & b)
    if not comunes:
        return 0.0
    return (comunes / len(a | b) + comunes / len(b)) / 2


class Personas:
    """Traduce los nombres que da Biwenger a los que usa el Excel.

    Biwenger devuelve el nombre completo del equipo ("Algeciras FC", "NIKE FC
    (MUNDIAL 🏅)", "Competa c.f.", "El barreño") y el Excel trabaja con los
    cortos de la hoja Participantes. Al no coincidir, el antiduplicados no
    reconoce lo ya registrado y los movimientos entran dos veces, o peor: bajo
    un mánager que no existe, y entonces su saldo se parte en dos.

    Se exige un ganador CLARO, porque hay dos mánagers que se llaman casi igual
    ("Algeciras" y "Ciudad Algeciras") y adjudicar a la ligera le asignaría las
    compras al que no es. Si la duda no se despeja, NO se inventa una
    traducción: se devuelve el nombre tal cual y queda anotado como dudoso para
    que quien llame decida (el bot descarta ese movimiento en vez de escribirlo
    mal).
    """

    MINIMO = 0.50      # por debajo de esto no se parecen lo suficiente
    MARGEN = 0.15      # y el segundo tiene que quedarse claramente por detrás

    def __init__(self, nombres_excel):
        self.nombres = list(nombres_excel)
        self.cache = {}
        self.dudosos = []

    def traducir(self, nombre):
        if not nombre:
            return nombre
        if nombre in self.cache:
            return self.cache[nombre]

        puntuaciones = sorted(((_parecido(nombre, candidato), candidato)
                               for candidato in self.nombres), reverse=True)
        elegido = nombre
        if puntuaciones:
            mejor = puntuaciones[0]
            segundo = puntuaciones[1] if len(puntuaciones) > 1 else (0.0, None)
            if mejor[0] >= self.MINIMO and mejor[0] - segundo[0] >= self.MARGEN:
                elegido = mejor[1]
            else:
                self.dudosos.append(
                    f"{nombre} (el que más se parece es {mejor[1]}, {mejor[0]:.2f})")

        self.cache[nombre] = elegido
        return elegido

    def es_valido(self, nombre):
        """¿Este nombre es uno de los diez del Excel?"""
        return nombre in self.nombres

    def resumen(self):
        cambios = [f"{k} -> {v}" for k, v in sorted(self.cache.items()) if k != v]
        return cambios, self.dudosos


def leer_participantes():
    """Los diez mánagers tal y como están escritos en el Excel."""
    libro = almacen.abrir(RUTA_EXCEL)
    hoja = libro['Participantes']
    nombres = [str(hoja.cell(f, 1).value).strip()
               for f in range(2, 12) if hoja.cell(f, 1).value]
    libro.close()
    return nombres


def ultima_fecha_registrada():
    """Fecha del movimiento más reciente ya apuntado en Contabilidad.

    Todo lo anterior a ese día está metido a mano y volver a bajarlo solo puede
    duplicarlo. El corte se pone en ese mismo día, no en el siguiente: los
    movimientos de hoy que aún no estén registrados sí tienen que entrar, y de
    los repetidos ya se encarga la huella.
    """
    libro = almacen.abrir(RUTA_EXCEL)
    hoja = libro['Contabilidad']
    ultima = None
    for fila in hoja.iter_rows(min_row=2, max_col=3, values_only=True):
        fecha, persona, tipo = fila
        if not persona or not tipo or not hasattr(fecha, 'year'):
            continue
        if fecha.year < 2000:
            continue
        if ultima is None or fecha > ultima:
            ultima = fecha
    libro.close()
    return ultima



HOJA_CALENDARIO = "ClasificacionCalendario"
CAL_FILA_INICIO = 3        # la 1 es un rótulo suelto y la 2 las cabeceras
CAL_COL_JORNADA, CAL_COL_FECHA = 1, 2
CAL_COL_LOCAL, CAL_COL_VISITANTE = 3, 8
CAL_COL_GOL_LOCAL, CAL_COL_GOL_VISITANTE = 5, 6
# La hora va en la J, que estaba vacía entre el calendario (A-H) y la
# clasificación (K en adelante). Se escribe como texto "21:00".
CAL_COL_HORA = 10
CAL_FILA_CABECERA = 2
# Si tres o más partidos de una jornada caen en el mismo instante, es una hora
# de relleno de Biwenger (el día puede ser bueno, la hora no).
MIN_PARTIDOS_HORA_RELLENO = 3
JORNADAS_CALENDARIO_RAPIDO = 3

# Hasta dónde se considera que una fecha es de verdad. LaLiga publica los
# horarios con dos o tres semanas de antelación; lo que hay más allá es un hueco
# con algo escrito encima, y Biwenger lo enseña igual porque necesita colocar el
# partido en algún sitio. Escribirlo sería fingir que se sabe.
DIAS_HORIZONTE = 25


def hoja_tiene_hueco_hora(hoja):
    """La columna de la hora solo se usa si está libre o ya es la de la hora:
    si algún día se mete otra cosa en la J, el bot no la pisa."""
    return hoja.cell(CAL_FILA_CABECERA, CAL_COL_HORA).value in (None, "", "Hora")


def sincronizar_calendario(wb, partidos, aplicar=True, parcial=False):
    """Escribe fechas y resultados en ClasificacionCalendario desde Biwenger.

    Lo único que se toca son tres celdas por fila: la fecha y los dos goles.
    Los equipos y las fórmulas de los escudos se quedan como están, que es lo
    que hace que la hoja siga funcionando.

    SIN FECHA EN BIWENGER, CELDA VACÍA. Un partido sin día no es un partido el
    día que tocaría: la app enseña «Sin determinar», que es la verdad. Y como
    Biwenger a veces pone a toda una jornada la misma hora de relleno mientras
    no hay horarios, eso se detecta y también se deja en blanco.
    """
    if HOJA_CALENDARIO not in wb.sheetnames or not partidos:
        return 0, 0, []

    hoja = wb[HOJA_CALENDARIO]

    # Horas de relleno: si casi todos los partidos de una jornada caen en el
    # mismo instante exacto, no son horarios de verdad.
    por_jornada = {}
    for partido in partidos:
        if partido["fecha"]:
            por_jornada.setdefault(partido["jornada"], []).append(partido["fecha"])
    rellenos = set()
    horas_relleno = set()
    for jornada, fechas in por_jornada.items():
        for momento in set(fechas):
            if fechas.count(momento) >= 8:
                rellenos.add((jornada, momento))
            if fechas.count(momento) >= MIN_PARTIDOS_HORA_RELLENO:
                horas_relleno.add((jornada, momento))
    if aplicar and hoja_tiene_hueco_hora(wb[HOJA_CALENDARIO]):
        wb[HOJA_CALENDARIO].cell(CAL_FILA_CABECERA, CAL_COL_HORA).value = "Hora"

    indice = {}
    for partido in partidos:
        clave = (partido["jornada"], _sin_tildes_min(partido["local"]),
                 _sin_tildes_min(partido["visitante"]))
        indice[clave] = partido

    fechas_puestas = resultados_puestos = fechas_borradas = sin_encontrar = 0
    sin_confirmar = 0
    ahora = int(datetime.now().timestamp())
    detalle = []

    for fila in range(CAL_FILA_INICIO, hoja.max_row + 1):
        jornada = hoja.cell(fila, CAL_COL_JORNADA).value
        local = hoja.cell(fila, CAL_COL_LOCAL).value
        visitante = hoja.cell(fila, CAL_COL_VISITANTE).value
        if not jornada or not local or not visitante:
            continue
        try:
            jornada = int(jornada)
        except (TypeError, ValueError):
            continue

        partido = indice.get((jornada, _sin_tildes_min(local), _sin_tildes_min(visitante)))
        if partido is None:
            if parcial:
                continue        # modo rápido: solo vienen las jornadas próximas
            sin_encontrar += 1
            if sin_encontrar <= 5:
                detalle.append(f"J{jornada}: no encuentro {local} - {visitante} en Biwenger")
            continue

        # Fecha
        marca = partido["fecha"]
        de_relleno = (jornada, marca) in rellenos
        # Un partido jugado tiene fecha segura, pasara cuando pasara. Uno por
        # jugar, solo si cae dentro del horizonte de horarios confirmados.
        jugado = partido["estado"] == "finished"
        dentro = bool(marca) and (marca - ahora) <= DIAS_HORIZONTE * 86400
        confirmada = jugado or dentro
        if not confirmada:
            sin_confirmar += 1
        # Hora: solo con fecha confirmada y si no es una hora de relleno. Las
        # 00:00 tampoco valen: es lo que pone Biwenger cuando no la sabe.
        celda_hora = hoja.cell(fila, CAL_COL_HORA)
        hora = None
        if marca and not de_relleno and confirmada and (jornada, marca) not in horas_relleno:
            momento = datetime.fromtimestamp(marca)
            if (momento.hour, momento.minute) != (0, 0):
                hora = momento.strftime("%H:%M")
        if aplicar and hoja_tiene_hueco_hora(hoja) and celda_hora.value != hora:
            celda_hora.value = hora

        celda = hoja.cell(fila, CAL_COL_FECHA)
        if marca and not de_relleno and confirmada:
            nueva = datetime.fromtimestamp(marca).replace(hour=0, minute=0, second=0,
                                                          microsecond=0)
            cambia = celda.value != nueva
            if cambia:
                fechas_puestas += 1
                if aplicar:
                    celda.value = nueva
                    celda.number_format = "DD/MM/YYYY"
        elif celda.value is not None:
            if aplicar:
                celda.value = None
            fechas_borradas += 1

        # Resultado: solo el de los partidos jugados. Un partido por jugar no
        # tiene marcador, y poner un cero sería inventarse un 0-0.
        gl, gv = partido["goles_local"], partido["goles_visitante"]
        if partido["estado"] == "finished" and gl is not None and gv is not None:
            actual = (hoja.cell(fila, CAL_COL_GOL_LOCAL).value,
                      hoja.cell(fila, CAL_COL_GOL_VISITANTE).value)
            if actual != (gl, gv):
                if aplicar:
                    hoja.cell(fila, CAL_COL_GOL_LOCAL).value = gl
                    hoja.cell(fila, CAL_COL_GOL_VISITANTE).value = gv
                resultados_puestos += 1
                if len(detalle) < 12:
                    detalle.append(f"J{jornada} {local} {gl}-{gv} {visitante}"
                                   + (f" (estaba {actual[0]}-{actual[1]})"
                                      if actual[0] is not None else ""))

    if fechas_borradas:
        detalle.append(f"{fechas_borradas} fecha/s dejadas en blanco (la app dirá "
                       '"Sin determinar")')
    if sin_confirmar:
        detalle.append(f"{sin_confirmar} partido/s con fecha en Biwenger pero a más de "
                       f"{DIAS_HORIZONTE} días: son provisionales y no se escriben")
    if sin_encontrar > 5:
        detalle.append(f"…y {sin_encontrar - 5} partido/s más sin encontrar")
    return fechas_puestas, resultados_puestos, detalle


def _sin_tildes_min(texto):
    limpio = unicodedata.normalize("NFKD", str(texto or ""))
    return limpio.encode("ascii", "ignore").decode().strip().lower()



COL_PUNTOS_PARTICIPANTES = 13


def sincronizar_puntos(wb, abonos, personas, mis_puntos=None, yo=None):
    """Pone al día la columna Puntos de Participantes sumando las jornadas.

    Cada evento de fin de jornada trae, junto al abono, los puntos que hizo cada
    mánager esa semana. Sumándolos sale la clasificación, que es lo que hasta
    ahora se copiaba a mano de la web y se quedaba desfasada (el Excel andaba
    por 210 cuando la realidad eran 323).

    Se cuentan IGUAL que los abonos: de cada jornada manda el último pago, no la
    suma de los dos. Una jornada aplazada da puntos provisionales y luego los
    rectifica, y el propio Biwenger lo avisa —"al ser una jornada especial
    dividida, los puntos y abonos han sido rectificados"—. Sumar las dos
    tandas inflaría la clasificación.

    Y NO SE ESCRIBE A CIEGAS. La API dice cuántos puntos tienes TÚ en total, así
    que antes de tocar nada se comprueba que la suma coincide con esa cifra. Si
    no cuadra, no se escribe y se avisa: una clasificación mal es peor que una
    clasificación vieja, porque la vieja al menos se nota.
    """
    if not abonos or "Participantes" not in wb.sheetnames:
        return 0, []

    definitivo = {}
    for abono in sorted(abonos, key=lambda a: a["fecha"]):
        if abono["jornada"] is not None:
            definitivo[(abono["persona"], abono["jornada"])] = abono

    totales, jornadas = {}, set()
    for (persona, jornada), abono in definitivo.items():
        totales[persona] = totales.get(persona, 0) + int(abono.get("puntos") or 0)
        jornadas.add(jornada)

    detalle = []
    if yo and mis_puntos is not None:
        calculado = totales.get(yo)
        if calculado is None:
            detalle.append(f"No encuentro tus jornadas para comprobar la suma; no se "
                           "escribe nada.")
            return 0, detalle
        if calculado != mis_puntos:
            detalle.append(f"NO CUADRA: sumando las {len(jornadas)} jornadas te salen "
                           f"{calculado} puntos y Biwenger dice {mis_puntos}. No se "
                           "escribe nada (faltará alguna jornada en el tablón).")
            return 0, detalle
        detalle.append(f"comprobado: {len(jornadas)} jornadas suman tus {mis_puntos} "
                       "puntos exactos")

    hoja = wb["Participantes"]
    escritos = []
    for fila in range(2, 12):
        persona = hoja.cell(fila, 1).value
        if not persona:
            continue
        persona = str(persona).strip()
        if persona not in totales:
            continue
        celda = hoja.cell(fila, COL_PUNTOS_PARTICIPANTES)
        antes = celda.value
        if antes != totales[persona]:
            celda.value = totales[persona]
            escritos.append(f"{persona}: {antes} -> {totales[persona]}")
    detalle.extend(escritos)
    return len(escritos), detalle


# ----------------------------------------------------------------------------
# 4. Escritura en el Excel
# ----------------------------------------------------------------------------

def _huella(fila):
    """Identifica un movimiento para no duplicarlo: día + persona + operación +
    jugador + importe. Se compara contra TODA la hoja, no contra las últimas
    filas: un duplicado en Contabilidad ensucia el saldo y además envenena el
    entrenamiento del predictor de pujas."""
    fecha = fila[0]
    dia = fecha.strftime("%Y-%m-%d") if hasattr(fecha, "strftime") else str(fecha)[:10]
    try:
        importe = str(int(round(float(fila[6] or 0))))
    except (TypeError, ValueError):
        importe = str(fila[6])
    return "|".join([dia, str(fila[1] or "").strip(), str(fila[2] or "").strip(),
                     str(fila[3] or "").strip(), importe])


# ----------------------------------------------------------------------------
# Pujas perdidas
# ----------------------------------------------------------------------------
# Cada compra del tablón trae 'bids': las pujas de los que perdieron la subasta,
# de mayor a menor y sin la del ganador. Vienen SIEMPRE, se haya pagado o no la
# moneda de la web, que solo desbloquea enseñarlas en pantalla.

MAX_PUJAS_PERDIDAS = 9            # Manager 1..9 / Subasta perdida 1..9
FORMATO_EURO = '#,##0.00" €"'     # el de las pujas que se metían a mano


def _euros(cantidad):
    try:
        return f"{int(cantidad):,} €".replace(",", ".")
    except (TypeError, ValueError):
        return str(cantidad)


def _texto_pujas(pujas):
    return ", ".join(f"{persona} {_euros(cantidad)}" for persona, cantidad in pujas) or "nada"


def _pujas_de_subasta(fecha, comprador, jugador, importe, traspaso, personas):
    """Las pujas perdidas de una compra, con los nombres de mánager del Excel.

    Lo que no se pueda traducir se aparta en 'problemas' y esa subasta no se
    escribirá: unas pujas a medias le enseñarían al predictor que alguien NO
    pujó cuando sí lo hizo.
    """
    pujas, problemas = [], []
    for puja in traspaso.get("bids") or []:
        if not isinstance(puja, dict):
            continue
        usuario = puja.get("user")
        nombre = usuario.get("name") if isinstance(usuario, dict) else None
        persona = personas.traducir(nombre) if nombre else None
        if not persona or not personas.es_valido(persona):
            problemas.append(str(nombre))
            continue
        if persona == comprador:
            continue                      # el ganador no es una puja perdida
        try:
            cantidad = int(round(float(puja.get("amount"))))
        except (TypeError, ValueError):
            problemas.append(f"{persona} (importe ilegible)")
            continue
        pujas.append((persona, cantidad))
    pujas.sort(key=lambda p: -p[1])
    return {"fecha": fecha, "comprador": comprador, "jugador": jugador,
            "importe": importe, "pujas": pujas, "problemas": problemas}


def _columna_primer_manager(hoja):
    """Columna de 'Manager 1', comprobando que detrás van las 18 cabeceras en
    su orden. None si no: con otra forma de hoja no se escribe a ciegas."""
    cabecera = [str(hoja.cell(1, c).value or "").strip()
                for c in range(1, hoja.max_column + 1)]
    if "Manager 1" not in cabecera:
        return None
    inicio = cabecera.index("Manager 1") + 1
    for i in range(MAX_PUJAS_PERDIDAS):
        if (str(hoja.cell(1, inicio + 2 * i).value or "").strip() != f"Manager {i + 1}"
                or str(hoja.cell(1, inicio + 2 * i + 1).value or "").strip()
                != f"Subasta perdida {i + 1}"):
            return None
    return inicio


def _pujas_en_fila(hoja, fila, inicio):
    pujas = []
    for i in range(MAX_PUJAS_PERDIDAS):
        quien = hoja.cell(fila, inicio + 2 * i).value
        cuanto = hoja.cell(fila, inicio + 2 * i + 1).value
        if quien in (None, "") and cuanto in (None, ""):
            continue
        try:
            cuanto = int(round(float(cuanto)))
        except (TypeError, ValueError):
            pass
        pujas.append((str(quien or "").strip(), cuanto))
    return pujas


def sincronizar_pujas(hoja, subastas):
    """Rellena Manager/Subasta perdida de cada compra de Contabilidad.

    - Solo escribe en compras con esas columnas VACÍAS. Lo ya apuntado no se
      pisa nunca: si no coincide con Biwenger, se avisa y se deja como está.
    - La fila se busca por día + comprador + jugador. Si no aparece (un nombre
      que Biwenger cambió, un día bailado), por comprador + importe exacto con
      tres días de margen. Si hay más de una candidata, no se escribe.

    Devuelve un diccionario con las cuentas y las líneas para el log.
    """
    resumen = {"compras": len(subastas), "con_pujas": 0, "completadas": 0,
               "pujas_escritas": 0, "cuadran": 0, "diferencias": 0,
               "sin_fila": 0, "problemas": 0, "detalle": [], "avisos": []}
    inicio = _columna_primer_manager(hoja)
    if inicio is None:
        resumen["avisos"].append("No encuentro las columnas Manager 1 … Subasta perdida 9 "
                                 "en Contabilidad: no se escribe ninguna puja.")
        return resumen

    por_clave, por_importe = {}, {}
    for f in range(2, hoja.max_row + 1):
        if str(hoja.cell(f, 3).value or "").strip() != "Compra":
            continue
        fecha = hoja.cell(f, 1).value
        if not hasattr(fecha, "date"):
            continue
        persona = str(hoja.cell(f, 2).value or "").strip()
        por_clave.setdefault((fecha.date(), persona, _sin_tildes_min(hoja.cell(f, 4).value)),
                             []).append(f)
        try:
            importe = int(round(float(hoja.cell(f, 7).value)))
        except (TypeError, ValueError):
            continue
        por_importe.setdefault((persona, importe), []).append((f, fecha.date()))

    for subasta in subastas:
        if not subasta["pujas"] and not subasta["problemas"]:
            continue                      # nadie más pujó: no hay nada que apuntar
        resumen["con_pujas"] += 1
        dia = subasta["fecha"].date()
        etiqueta = f"{subasta['jugador']} ({subasta['comprador']}, {dia:%d/%m})"
        if subasta["problemas"]:
            resumen["problemas"] += 1
            resumen["avisos"].append(f"{etiqueta}: no sé qué mánager es "
                                     f"{', '.join(subasta['problemas'])}. No se toca.")
            continue

        filas = por_clave.get((dia, subasta["comprador"],
                               _sin_tildes_min(subasta["jugador"])), [])
        if len(filas) != 1:
            try:
                importe = int(round(float(subasta["importe"])))
            except (TypeError, ValueError):
                importe = None
            filas = [f for f, otro_dia in por_importe.get((subasta["comprador"], importe), [])
                     if abs((otro_dia - dia).days) <= 3]
        if len(filas) != 1:
            resumen["sin_fila"] += 1
            motivo = "no encuentro su compra" if not filas else f"hay {len(filas)} compras posibles"
            resumen["avisos"].append(f"{etiqueta}: {motivo} en Contabilidad. No se toca.")
            continue
        fila = filas[0]

        del_tablon = subasta["pujas"]
        if len(del_tablon) > MAX_PUJAS_PERDIDAS:
            resumen["avisos"].append(f"{etiqueta}: {len(del_tablon)} pujas y solo caben "
                                     f"{MAX_PUJAS_PERDIDAS}; se apuntan las más altas.")
            del_tablon = del_tablon[:MAX_PUJAS_PERDIDAS]

        del_excel = _pujas_en_fila(hoja, fila, inicio)
        if not del_excel:
            for i, (persona, cantidad) in enumerate(del_tablon):
                hoja.cell(fila, inicio + 2 * i, persona)
                hoja.cell(fila, inicio + 2 * i + 1, cantidad).number_format = FORMATO_EURO
            resumen["completadas"] += 1
            resumen["pujas_escritas"] += len(del_tablon)
            resumen["detalle"].append(f"{etiqueta}, fila {fila}: {_texto_pujas(del_tablon)}")
        elif (sorted((p, str(c)) for p, c in del_excel)
              == sorted((p, str(c)) for p, c in del_tablon)):
            resumen["cuadran"] += 1
        else:
            resumen["diferencias"] += 1
            resumen["avisos"].append(f"{etiqueta}, fila {fila}: el Excel tiene "
                                     f"{_texto_pujas(del_excel)} y Biwenger "
                                     f"{_texto_pujas(del_tablon)}. No se toca: revísala.")
    return resumen


def sanear_sobrepujas_de_ventas(hoja):
    """Pone a 0 la sobrepuja de las ventas que la tengan escrita como número.

    Devuelve los jugadores corregidos, para el log. Se busca la columna por su
    cabecera y no por posición: si algún día se inserta una columna, no se
    escribe a ciegas en la que no es."""
    cabecera = [str(hoja.cell(1, c).value or "").strip() for c in range(1, hoja.max_column + 1)]
    if "Sobrepuja (€)" not in cabecera or "Tipo de Operación" not in cabecera:
        return []
    col_sobrepuja = cabecera.index("Sobrepuja (€)") + 1
    col_tipo = cabecera.index("Tipo de Operación") + 1
    col_jugador = cabecera.index("Jugador") + 1 if "Jugador" in cabecera else None
    corregidas = []
    for f in range(2, hoja.max_row + 1):
        if str(hoja.cell(f, col_tipo).value or "").strip() != "Venta":
            continue
        celda = hoja.cell(f, col_sobrepuja)
        if isinstance(celda.value, (int, float)) and not isinstance(celda.value, bool) and celda.value != 0:
            celda.value = 0
            corregidas.append(str(hoja.cell(f, col_jugador).value or f"fila {f}") if col_jugador
                              else f"fila {f}")
    return corregidas


def _avisar_pujas(resumen):
    """Lo que cuenta el log sobre las pujas perdidas."""
    aviso(f"Pujas perdidas: {resumen['completadas']} subasta/s completada/s "
          f"({resumen['pujas_escritas']} puja/s), {resumen['cuadran']} ya estaban y "
          f"cuadran con Biwenger.")
    for linea in resumen["detalle"][:20]:
        aviso(f"   · {linea}")
    for linea in resumen["avisos"][:20]:
        aviso(f"   AVISO: {linea}")
    # Si un día Biwenger deja de mandarlas, las columnas se quedarían vacías sin
    # que nada lo delatara. En esta liga casi la mitad de las subastas tiene
    # pujas perdidas, así que ninguna en todo el tablón es señal de alarma.
    if resumen["compras"] >= 20 and resumen["con_pujas"] == 0:
        aviso(f"   AVISO SERIO: el tablón no trae ni una puja perdida en {resumen['compras']} "
              "compras. Puede que Biwenger haya dejado de enviarlas: habría que volver a "
              "meterlas a mano.")


def escribir_excel(app, jugadores, movimientos, abonos=None, personas=None,
                   calendario=None, mis_puntos=None, yo=None, subastas=None, calendario_parcial=False,
                   multiposiciones=None):
    """Vuelca todo en la base de datos usando guardar_excel() de la app, que
    hace copia de seguridad y guarda en una sola transacción. Un bot
    desatendido que sobrescribe el único archivo de datos sin red es una
    bomba de relojería."""

    wb = almacen.abrir(RUTA_EXCEL)

    # Las dos hojas del mercado las escribe api_biwenger, con tres columnas más
    # que antes: el ID numérico de Biwenger y los puntos EXACTOS en casa y
    # fuera. Con eso, actualizar_split_casa_fuera deja de deducir el reparto
    # comparando el export de hoy con el de ayer y simplemente lo copia: se
    # acabaron los repartos por proporción, las siembras de los recién
    # llegados, las reconciliaciones cuando Biwenger rectifica una jornada y el
    # emparejado a mano cuando renombra o traspasa a alguien.
    api_biwenger.escribir_export(wb, jugadores)
    api_biwenger.escribir_export(wb, jugadores, hoja="Biwenger_Ayer", de_ayer=True)
    aplicar_multiposiciones(wb, jugadores, multiposiciones)
    escribir_eventos_jornada(wb, jugadores)

    # Los abonos de jornada se cuadran ANTES de añadir los movimientos nuevos:
    # así, si una jornada aplazada se ha vuelto a pagar, la fila vieja se
    # corrige en vez de quedarse al lado de la nueva.
    if abonos:
        altas, rectificados, detalle = sincronizar_abonos(wb, abonos, personas)
        if altas or rectificados:
            aviso(f"Abonos de jornada: {altas} nuevo/s, {rectificados} rectificado/s.")
        for linea in detalle[:20]:
            aviso(f"   · {linea}")

        # 🏆 Y de paso los puntos de la clasificación, que vienen en el mismo
        # evento que los abonos.
        cambiados, detalle_puntos = sincronizar_puntos(wb, abonos, personas,
                                                       mis_puntos, yo)
        aviso(f"Puntos de la liga: {cambiados} mánager/s actualizados.")
        for linea in detalle_puntos[:12]:
            aviso(f"   · {linea}")

    # 📅 Calendario y resultados, de Biwenger a la hoja, sin teclear nada.
    if calendario:
        fechas, resultados, detalle = sincronizar_calendario(wb, calendario, parcial=calendario_parcial)
        if fechas or resultados:
            aviso(f"Calendario: {fechas} fecha/s y {resultados} resultado/s puestos.")
        for linea in detalle[:15]:
            aviso(f"   · {linea}")

    nuevos = 0
    if movimientos and "Contabilidad" in wb.sheetnames:
        hoja = wb["Contabilidad"]
        registradas = set()
        for f in range(2, hoja.max_row + 1):
            if hoja.cell(f, 2).value:
                registradas.add(_huella([hoja.cell(f, c).value for c in range(1, 10)]))

        ultima = max((f for f in range(2, hoja.max_row + 1) if hoja.cell(f, 2).value),
                     default=1)
        for movimiento in movimientos:
            if _huella(movimiento) in registradas:
                continue
            ultima += 1
            for col, valor in enumerate(movimiento, 1):
                celda = hoja.cell(ultima, col, valor)
                if col == 1 and hasattr(valor, "strftime"):
                    celda.number_format = 'DD/MM/YYYY'
            registradas.add(_huella(movimiento))
            nuevos += 1

        # La tabla estructurada se quedó corta hace tiempo (llegaba a la fila
        # 174 con datos hasta la 397). Se estira para que las filas nuevas
        # queden dentro de ella.
        for nombre_tabla, tabla in list(hoja.tables.items()):
            ref = tabla.ref if hasattr(tabla, "ref") else hoja.tables[nombre_tabla].ref
            try:
                inicio, fin = ref.split(":")
                col_fin = ''.join(c for c in fin if c.isalpha())
                tabla_obj = hoja.tables[nombre_tabla]
                tabla_obj.ref = f"{inicio}:{col_fin}{max(ultima, 2)}"
            except Exception:
                pass

    # 💶 Las ventas que el bot apuntó antes con "sobrepuja" se dejan a 0. Solo
    # las que tienen un NÚMERO distinto de 0: las fórmulas de las filas metidas
    # a mano ya dan vacío en las ventas y no se tocan.
    if "Contabilidad" in wb.sheetnames:
        corregidas = sanear_sobrepujas_de_ventas(wb["Contabilidad"])
        if corregidas:
            aviso(f"Sobrepujas de venta puestas a 0: {len(corregidas)} "
                  f"({', '.join(corregidas[:8])}{'…' if len(corregidas) > 8 else ''}).")

    # 🎯 Pujas perdidas: DESPUÉS de añadir los movimientos, para que las compras
    # de hoy ya tengan su fila, y ANTES de guardar. Va fuera del bloque de arriba
    # porque también completa compras antiguas aunque hoy no haya nada nuevo.
    if subastas is not None and "Contabilidad" in wb.sheetnames:
        _avisar_pujas(sincronizar_pujas(wb["Contabilidad"], subastas))

    app["guardar_excel"](wb, RUTA_EXCEL)
    aviso(f"Base de datos actualizada. Movimientos nuevos en Contabilidad: {nuevos}.")
    return nuevos


# ----------------------------------------------------------------------------
# 5. Procesos de la app
# ----------------------------------------------------------------------------

def cargar_app():
    """Carga app.py con Streamlit simulado para poder reutilizar sus funciones.

    Se reutilizan en vez de reescribirlas porque llevan meses de correcciones
    dentro: detección de renombrados, reparto casa/fuera, recálculo de fórmulas,
    copia de seguridad... Duplicar esa lógica en el bot sería condenarse
    a arreglar cada fallo dos veces.
    """
    WIDGETS = ("selectbox", "radio", "multiselect", "text_input", "number_input",
               "checkbox", "button", "toggle", "metric", "markdown", "info",
               "warning", "error", "success", "caption", "write", "dataframe")

    class Nada:
        def __init__(self, *a, **k): pass
        def __call__(self, *a, **k): return Nada()
        def __getattr__(self, n):
            # Las columnas y contenedores tienen los mismos métodos que st: si
            # no se delega, col.selectbox() devuelve un objeto tonto en lugar de
            # un valor y todo lo que venga después revienta al compararlo.
            if n in WIDGETS:
                return getattr(sys.modules["streamlit"], n)
            return Nada()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __iter__(self): return iter([Nada() for _ in range(12)])
        def __bool__(self): return False
        __pandas_priority__ = 0
        __array_struct__ = None
        __array_interface__ = None
        def __array__(self, *a, **k):
            import numpy as np
            return np.array(None, dtype=object)
        def __gt__(self, o): return False
        def __lt__(self, o): return False
        def __ge__(self, o): return False
        def __le__(self, o): return False

    class StreamlitFalso:
        _estado = {}
        def __getattr__(self, nombre):
            if nombre == "session_state":
                return StreamlitFalso._estado
            if nombre == "columns":
                return lambda n, **k: [Nada() for _ in (range(n) if isinstance(n, int) else n)]
            if nombre == "tabs":
                return lambda etiquetas, **k: [Nada() for _ in etiquetas]
            if nombre in ("selectbox", "radio"):
                def elegir(label, opciones, index=0, **k):
                    ops = list(opciones)
                    if not ops:
                        return ""
                    return ops[index] if index and index < len(ops) else ops[0]
                return elegir
            if nombre == "multiselect":
                return lambda label, opciones, default=None, **k: (default or [])
            if nombre == "text_input":
                return lambda label, value="", **k: value
            if nombre == "number_input":
                return lambda label, min_value=0.0, value=0.0, **k: value
            if nombre in ("checkbox", "button", "toggle"):
                return lambda label, value=False, **k: (bool(value)
                                                        if nombre == "checkbox" else False)
            if nombre in ("cache_data", "cache_resource"):
                def deco(func=None, **k):
                    def envolver(f):
                        memoria = {}
                        def dentro(*a, **kk):
                            clave = str(a) + str(sorted(kk.items()))
                            if clave not in memoria:
                                memoria[clave] = f(*a, **kk)
                            return memoria[clave]
                        dentro.__wrapped__ = f
                        dentro.clear = memoria.clear
                        return dentro
                    return envolver(func) if callable(func) else envolver
                return deco
            if nombre == "fragment":
                return lambda f=None, **k: (f if callable(f) else (lambda g: g))
            return Nada()

    sys.modules["streamlit"] = StreamlitFalso()
    for modulo, atributos in [("plotly", []),
                              ("plotly.graph_objects", ["Figure", "Scatterpolar", "Scatter", "Bar"]),
                              ("plotly.express", ["bar", "pie", "line"]),
                              ("plotly.io", []),
                              ("plotly.subplots", ["make_subplots"])]:
        m = types.ModuleType(modulo)
        for atributo in atributos:
            setattr(m, atributo, Nada())
        if modulo == "plotly.io":
            m.templates = types.SimpleNamespace(default="plotly")
        sys.modules[modulo] = m
    sys.modules["plotly"].graph_objects = sys.modules["plotly.graph_objects"]
    sys.modules["plotly"].express = sys.modules["plotly.express"]
    sys.modules["plotly"].io = sys.modules["plotly.io"]

    os.chdir(CARPETA)
    return runpy.run_path(RUTA_APP, run_name="bot_diario")


def ejecutar_procesos(app, rapido=False):
    """Lo mismo que pulsaba «Importar hoy» y el reparto casa/fuera de la app.

    En el modo rápido no se importa el día al histórico (la foto de los precios
    es de las 7:00 y ya la hizo la ejecución de las 8:30), así que tampoco hace
    falta el primer recálculo, que solo servía para leer el mercado al día."""
    if not rapido:
        _procesos_del_dia(app)

    resultado = app["actualizar_split_casa_fuera"]()
    ok, mensaje, avisos = resultado if len(resultado) == 3 else (resultado[0], resultado[1], [])
    aviso(f"Casa/fuera: {mensaje}")
    for linea in avisos[:15]:
        aviso(f"   · {linea}")

    # 👥 Plantillas al día desde Contabilidad: las altas de los fichajes, las
    # bajas de las ventas, el cambio de mánager en los traspasos, y el estado,
    # los goles y las asistencias de cada ficha. Era lo último que quedaba de
    # escribir a mano jugador por jugador.
    if "sincronizar_plantillas" in app:
        ok, mensaje, detalle = app["sincronizar_plantillas"]()
        aviso(f"Plantillas: {mensaje}")
        for linea in detalle[:15]:
            aviso(f"   · {linea}")
    else:
        aviso("AVISO: tu app.py no tiene sincronizar_plantillas(); Plantillas sigue "
              "a mano.")

    app["actualizar_registro_fichajes"]()



def _procesos_del_dia(app):
    """Calcular el mercado del día e importarlo al histórico."""
    # El mercado se calcula en Python (calculos.py) a partir de las hojas en
    # bruto. Antes se leía la hoja Mercado_Global, y para eso había que
    # recalcular el libro con Excel primero: sin Excel o sin pywin32 el
    # histórico se llenaba de ceros.
    import calculos
    mercado = calculos.calcular_desde_almacen(RUTA_EXCEL)["mercado"].dropna(subset=["Jugador"])

    # A qué día pertenecen los datos que hay ahora en el servidor. Biwenger
    # cambia el mercado a las 7:00, así que una ejecución de madrugada trae
    # todavía los datos de ayer y NO debe abrir un bloque nuevo.
    dia = app.get("fecha_de_mercado")
    if dia is None:
        aviso("AVISO: tu app.py no tiene fecha_de_mercado(). Si el bot corre antes "
              "de las 7:00 creará un bloque del día nuevo con los datos de ayer.")
    else:
        aviso(f"Día de mercado: {dia():%d/%m/%Y} (ahora son las {datetime.now():%H:%M}).")

    ok, mensaje = app["importar_dia_a_historico"](mercado)
    aviso(f"Histórico: {mensaje}")


# ----------------------------------------------------------------------------

def candado():
    """Evita que dos ejecuciones se pisen.

    Con la tarea programada y un arranque a mano pueden solaparse, y dos
    procesos escribiendo el mismo Excel a la vez es la mejor manera de
    perderlo. Devuelve None si ya hay otra en marcha.
    """
    ruta = os.path.join(CARPETA, "bot_diario.lock")
    if os.path.exists(ruta):
        edad = time.time() - os.path.getmtime(ruta)
        if edad < 3600:      # una hora: si es más viejo, es de una que murió
            return None
    with open(ruta, "w", encoding="utf-8") as fichero:
        fichero.write(f"{os.getpid()} {datetime.now():%d/%m/%Y %H:%M:%S}")
    return ruta


# Banderas de SetThreadExecutionState (API de Windows).
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def mantener_despierto(activar=True):
    """Pide a Windows que no suspenda el equipo mientras dure la ejecución.

    Cuando la tarea despierta el portátil a las 8:30 sin que nadie lo toque,
    Windows lo vuelve a dormir a los 2 minutos salvo que algún programa avise
    de que está trabajando. El bot tarda 4-5 minutos: sin este aviso se
    quedaría dormido a mitad, con las peticiones a la API cortadas y el
    guardado sin hacer.

    Con activar=False se devuelve el control a Windows. Si el proceso muere
    antes de llegar ahí, Windows libera el aviso solo al cerrarse el proceso.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        estado = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if activar else 0)
        correcto = ctypes.windll.kernel32.SetThreadExecutionState(estado)
    except Exception as error:
        correcto, detalle = 0, f" ({error})"
    else:
        detalle = ""
    # Solo importa al activar: al liberar, si falla, lo libera el cierre del proceso.
    if activar:
        if correcto:
            aviso("Windows avisado: no se suspenderá hasta que termine el bot.")
        else:
            aviso(f"No he podido pedir a Windows que no se suspenda{detalle}. Se continúa.")


# Códigos de salida: la app los lee para decirte qué ha pasado al pulsar el
# botón de actualizar, sin tener que rebuscar en el log.
SALIDA_BIEN, SALIDA_ERROR, SALIDA_EXCEL_ABIERTO, SALIDA_YA_EN_MARCHA = 0, 1, 2, 3


def main(rapido=False):
    """La actualización entera (la de las 8:30) o, con rapido=True, la del botón
    de la app: compras, ventas, pujas, abonos, lesiones y sanciones, puntos y
    plantillas, y el calendario de la jornada en curso y las dos siguientes
    (horarios y resultados). Se salta el calendario entero (41 peticiones, casi
    un minuto) y la foto del día del histórico (los precios solo se mueven a las
    7:00, y esa ya la hizo la de las 8:30)."""
    aviso("=" * 60)
    if rapido:
        aviso("Modo rápido: compras, ventas, pujas, lesiones y puntos.")
    if not os.path.exists(RUTA_EXCEL):
        raise SystemExit(f"No encuentro {RUTA_EXCEL}. Si vienes del Excel, ejecuta "
                         "una vez migrar_a_sqlite.py.")
    if not os.path.exists(RUTA_APP):
        raise SystemExit(f"No encuentro {RUTA_APP}.")

    # El candado existía desde hace tiempo pero nadie lo llamaba. Con el botón de
    # la app es imprescindible: si coincide con la tarea de las 8:30, las dos
    # escribirían el mismo Excel a la vez.
    ruta_candado = candado()
    if ruta_candado is None:
        aviso("Ya hay otra actualización en marcha. No se hace nada para no pisarla.")
        return SALIDA_YA_EN_MARCHA
    try:
        _actualizar(rapido)
    finally:
        try:
            os.remove(ruta_candado)
        except OSError:
            pass
    return SALIDA_BIEN


def _actualizar(rapido):
    cabeceras = abrir_sesion()
    jugadores, equipos, por_id = descargar_mercado()
    multiposiciones = descargar_multiposiciones(jugadores)

    # Goles y asistencias: se acumulan recorriendo las jornadas jugadas (6-7
    # peticiones), no preguntando jugador por jugador (550). Si falla, el bot
    # sigue: se quedan en None y la app conserva lo escrito a mano.
    try:
        api_biwenger.rellenar_estadisticas(jugadores, registro=aviso)
    except Exception as error:
        aviso(f"Goles y asistencias: no se han podido leer ({error}). Se continúa.")

    personas = Personas(leer_participantes())
    subastas = []      # las pujas perdidas de cada compra, sin corte por fecha
    movimientos, abonos_jornada = descargar_movimientos(cabeceras, por_id, personas,
                                                        pujas=subastas)
    cambios, dudosos = personas.resumen()
    for cambio in cambios:
        aviso(f"   nombre traducido: {cambio}")
    for duda in dudosos:
        aviso(f"   AVISO, nombre sin traducir por ambiguo: {duda}")

    # Lo anterior al último movimiento registrado está metido a mano; volver a
    # bajarlo solo puede duplicarlo.
    corte = ultima_fecha_registrada()
    if corte:
        antes = len(movimientos)
        movimientos = [m for m in movimientos if m[0] >= corte]
        if antes != len(movimientos):
            aviso(f"Corte por fecha ({corte:%d/%m/%Y}): "
                  f"{antes - len(movimientos)} movimiento/s anteriores descartados, "
                  f"quedan {len(movimientos)}.")

    aviso("Cargando app.py para reutilizar sus procesos (tarda unos segundos)…")
    app = cargar_app()
    aviso("app.py cargada.")

    # Calendario: entero a las 8:30; con el botón, solo la jornada en curso y
    # las dos siguientes (3 peticiones en vez de 41), que es donde cambian los
    # horarios y los resultados.
    calendario = None
    try:
        calendario = api_biwenger.descargar_calendario(
            registro=aviso, solo_proximas=JORNADAS_CALENDARIO_RAPIDO if rapido else None)
    except Exception as error:
        aviso(f"Calendario: no se ha podido leer ({error}). Se continúa.")

    # Mis puntos y mi nombre de equipo, para comprobar la suma antes de escribir
    # la clasificación. Si falla, se sigue: simplemente no se escriben los puntos.
    mis_puntos, yo = None, None
    try:
        inicio = requests.get("https://biwenger.as.com/api/v2/home?limit=1",
                              headers=cabeceras, timeout=30).json().get("data", {})
        usuario = inicio.get("user") or {}
        mis_puntos, yo = usuario.get("points"), personas.traducir(usuario.get("name"))
        aviso(f"Tus puntos según Biwenger: {mis_puntos} (puesto {usuario.get('position')}).")
    except Exception as error:
        aviso(f"No he podido leer tus puntos ({error}); la clasificación no se toca.")

    escribir_excel(app, jugadores, movimientos, abonos_jornada, personas, calendario,
                   mis_puntos, yo, subastas=subastas, multiposiciones=multiposiciones,
                   calendario_parcial=rapido)
    ejecutar_procesos(app, rapido=rapido)

    aviso("Listo.")


if __name__ == "__main__":
    import traceback
    # Lo primero de todo: si la tarea ha despertado el equipo, Windows da solo
    # 2 minutos antes de volver a dormirlo.
    mantener_despierto(True)
    codigo = SALIDA_BIEN
    try:
        codigo = main(rapido="--rapido" in sys.argv[1:]) or SALIDA_BIEN
    except BaseException as error:
        # BaseException y no Exception: así también quedan registrados los
        # SystemExit y los cortes con Ctrl+C, que antes se iban sin dejar rastro
        # y dejaban el log cortado sin explicar nada.
        aviso(f"ERROR ({type(error).__name__}): {error}")
        for linea in traceback.format_exc().splitlines():
            aviso(f"    {linea}")
        codigo = SALIDA_ERROR
    finally:
        mantener_despierto(False)
    sys.exit(codigo)
