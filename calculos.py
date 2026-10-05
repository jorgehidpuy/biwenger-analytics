# -*- coding: utf-8 -*-
"""Los cálculos que hacían las fórmulas del Excel, en Python.

Fase 1 de la migración para quitar el Excel: la app ya no lee los valores que
calculaban las fórmulas (que exigían recalcular el libro con Excel o
LibreOffice cada vez que se guardaba), sino que los calcula aquí a partir de
las hojas en bruto que rellenan el bot y la app:

    Biwenger_Export   precios, puntos y partidos de hoy (bot)
    Biwenger_Ayer     lo mismo, de ayer (bot)
    PJ_Split          puntos en casa y fuera (app)
    Multiposicion     posiciones dobles (bot)
    Plantillas        A-C: jugador, equipo y dueño (app)
    Contabilidad      movimientos (bot)
    Participantes     A: mánager, M: puntos de la liga

Cada función reproduce UNA hoja calculada con las mismas columnas que tenía en
el Excel, para que el resto de la app no note el cambio. Donde la fórmula
tenía un fallo, se corrige y se dice en el comentario.

Detalles de Excel que hay que imitar para dar lo mismo:
  - Las comparaciones de texto no distinguen mayúsculas ("algeciras" =
    "Algeciras"): las claves se comparan en minúsculas.
  - SUMIFS/SUMIF suman solo celdas numéricas y dan 0 si no hay ninguna.
  - AVERAGEIFS ignora las celdas vacías o de texto; sin ninguna numérica es un
    error (#¡DIV/0!), que aquí se devuelve como vacío (NaN).
  - LOOKUP(2, 1/(...)) devuelve la ÚLTIMA fila que coincide.
  - Una fórmula que da "" la lee pandas como NaN.
"""
import numpy as np
import pandas as pd

SALDO_INICIAL = 50_000_000


# --------------------------------------------------------------- utilidades
def _texto(serie):
    """Texto limpio, con '' en lugar de vacíos."""
    return serie.map(lambda v: "" if v is None or (isinstance(v, float) and np.isnan(v))
                     else str(v).strip()).astype(object).astype(str)


def _clave(*series):
    """Clave de cruce como la de Excel: sin distinguir mayúsculas."""
    partes = [_texto(s).str.casefold() for s in series]
    clave = partes[0]
    for p in partes[1:]:
        clave = clave + "||" + p
    return clave


def _num(serie):
    """Solo los números cuentan (como en SUMIFS); el resto, NaN."""
    return pd.to_numeric(serie, errors="coerce")


def _suma_por(clave_origen, valores, clave_destino):
    """SUMIFS: suma de `valores` agrupada por clave, llevada a `clave_destino`
    (0 si no hay ninguna coincidencia)."""
    sumas = pd.Series(_num(valores).values, index=clave_origen.values).groupby(level=0).sum(min_count=1)
    return clave_destino.map(sumas).fillna(0.0)


def _ultimo_por(clave_origen, valores, clave_destino):
    """LOOKUP(2,1/(...)): el valor de la última fila que coincide."""
    ultimo = pd.Series(valores.values, index=clave_origen.values)
    ultimo = ultimo[~ultimo.index.duplicated(keep="last")]
    return clave_destino.map(ultimo)


def _filas_con(df, columna):
    return df[_texto(df[columna]).ne("")] if columna in df.columns else df.iloc[0:0]


# ------------------------------------------------------------ Mercado_Global
COLUMNAS_MERCADO = ["Jugador", "Equipo", "Posición", "Puntos", "Media Puntos",
                    "Media Puntos Casa", "Media Puntos Fuera", "Valor Ayer (€)",
                    "Valor Actual (€)", "Variación Diaria (€)", "Estado"]


def mercado_global(export, ayer, plantillas, pj_split=None, multiposicion=None,
                   mi_equipo=None):
    """La hoja Mercado_Global: un jugador por fila con sus puntos y valores.

    CORREGIDO respecto a la fórmula: la fila 2 del mercado leía la fila 3 de
    Biwenger_Ayer, así que el primer jugador de esa hoja no salía nunca en el
    mercado. Aquí entran todos.
    """
    base = _filas_con(ayer, "Jugador")
    m = pd.DataFrame({"Jugador": _texto(base["Jugador"]).values,
                      "Equipo": _texto(base["Equipo"]).values})
    k = _clave(m["Jugador"], m["Equipo"])
    k_exp = _clave(export["Jugador"], export["Equipo"])
    k_ayer = _clave(ayer["Jugador"], ayer["Equipo"])

    # Posición: la de Multiposicion si el jugador está ahí con algo escrito
    pos = pd.Series(_texto(base["Posición"]).values, index=m.index).replace("", np.nan)
    if multiposicion is not None and not multiposicion.empty:
        mp = multiposicion.copy()
        col_pos = mp.columns[1]
        mp = mp[_texto(mp["Jugador"]).ne("") & _texto(mp[col_pos]).ne("")]
        # VLOOKUP sin orden: la PRIMERA coincidencia
        mapa = pd.Series(_texto(mp[col_pos]).values, index=_texto(mp["Jugador"]).str.casefold().values)
        mapa = mapa[~mapa.index.duplicated(keep="first")]
        multi = m["Jugador"].str.casefold().map(mapa)
        pos = multi.where(multi.notna(), pos)
    m["Posición"] = pos

    puntos = _suma_por(k_exp, export["Puntos"], k)
    pj = _suma_por(k_exp, export["PJ"], k)
    m["Puntos"] = puntos
    m["Media Puntos"] = (puntos / pj.replace(0, np.nan)).fillna(0.0)

    # Medias casa/fuera (la app las rehace igualmente en load_data)
    pj_c = _suma_por(k_exp, export["Casa"], k) if "Casa" in export else pd.Series(0.0, index=m.index)
    pj_f = _suma_por(k_exp, export["Fuera"], k) if "Fuera" in export else pd.Series(0.0, index=m.index)
    if pj_split is not None and not pj_split.empty:
        k_sp = _clave(pj_split["Jugador"], pj_split["Equipo"])
        pts_c = _suma_por(k_sp, pj_split["Pts C"], k)
        pts_f = _suma_por(k_sp, pj_split["Pts F"], k)
    else:
        pts_c = pts_f = pd.Series(0.0, index=m.index)
    m["Media Puntos Casa"] = (pts_c / pj_c.replace(0, np.nan)).fillna(0.0)
    m["Media Puntos Fuera"] = (pts_f / pj_f.replace(0, np.nan)).fillna(0.0)

    m["Valor Ayer (€)"] = _suma_por(k_ayer, ayer["Precio"], k)
    m["Valor Actual (€)"] = _suma_por(k_exp, export["Precio"], k)
    m["Variación Diaria (€)"] = np.where(m["Valor Ayer (€)"] == 0, 0.0,
                                         m["Valor Actual (€)"] - m["Valor Ayer (€)"])

    # Estado: dueño según Plantillas ("Libre" si de nadie). Con mi_equipo, los
    # de ese equipo salen como "Tuyo"; la app lo hace por sesión (cada usuario
    # elige su equipo), así que calcular_todo no lo pasa.
    pl = _filas_con(plantillas, "Jugador")
    dueno = _ultimo_por(_clave(pl["Jugador"], pl["Equipo"]), _texto(pl["Participante"]), k)
    mio = (dueno.fillna("").astype(str).map(str.casefold) == mi_equipo.casefold()
           if mi_equipo else pd.Series(False, index=m.index))
    m["Estado"] = np.where(dueno.isna(), "Libre", np.where(mio, "Tuyo", dueno))
    return m[COLUMNAS_MERCADO]


# ----------------------------------------------------------------- Plantillas
def completar_plantillas(plantillas, mercado):
    """Columnas calculadas de Plantillas (D-H) a partir del mercado."""
    pl = plantillas.copy()
    valido = _texto(pl["Jugador"]).ne("") & _texto(pl["Equipo"]).ne("")
    k = _clave(pl["Jugador"], pl["Equipo"])
    k_m = _clave(mercado["Jugador"], mercado["Equipo"])
    for col in ("Valor Ayer (€)", "Valor Actual (€)", "Variación Diaria (€)"):
        pl[col] = _suma_por(k_m, mercado[col], k).where(valido)
    for col in ("Posición", "Media Puntos"):
        pl[col] = _ultimo_por(k_m, mercado[col], k).where(valido)
    return pl


# --------------------------------------------------------------- Contabilidad
def completar_contabilidad(contabilidad, mercado):
    """Columnas calculadas de Contabilidad: Posición, Sobrepuja y % Sobrepuja."""
    c = contabilidad.copy()
    valido = _texto(c["Jugador"]).ne("") & _texto(c["Equipo"]).ne("")
    c["Posición"] = _ultimo_por(_clave(mercado["Jugador"], mercado["Equipo"]),
                                mercado["Posición"],
                                _clave(c["Jugador"], c["Equipo"])).where(valido)
    compra = _texto(c["Tipo de Operación"]).eq("Compra")
    importe, valor = _num(c["Importe (€)"]), _num(c["Valor Mercado (€)"])
    hay = compra & importe.notna() & valor.notna()
    c["Sobrepuja (€)"] = (importe - valor).where(hay)
    c["% Sobrepuja (uso interno)"] = ((importe - valor) / valor).where(hay & (valor > 0))
    return c


# -------------------------------------------------------------- Participantes
def _texto_millones(x):
    """ROUND(x/1e6,1) metido en un texto, como lo escribe Excel en español."""
    v = round(x / 1_000_000, 1)
    texto = f"{v:.1f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return texto.replace(".", ",")


def _perfil(indice):
    if indice is None or (isinstance(indice, float) and np.isnan(indice)):
        return "ℹ️ Perfil Financiero: Faltan datos de valores en sus compras."
    m = _texto_millones(indice)
    if indice > 3_000_000:
        return f"🔴 Perfil Derrochador: Sobrepuja excesivamente (Media: +{m}M€ por jugador)."
    if indice >= 1_000_000:
        return f"🟡 Perfil Normal: Ficha a precios habituales (Media: +{m}M€ por jugador)."
    return f"🟢 Perfil Conservador: Ficha muy barato (Media: +{m}M€ por jugador)."


def participantes(participantes_base, contabilidad, plantillas):
    """La hoja Participantes con todas sus columnas calculadas.

    `contabilidad` y `plantillas` deben venir ya completadas (con Sobrepuja y
    valores), es decir, pasadas por completar_contabilidad/completar_plantillas.
    """
    p = _filas_con(participantes_base, "Persona").copy().reset_index(drop=True)
    persona = _texto(p["Persona"]).str.casefold()

    c = contabilidad
    c_persona = _texto(c["Persona"]).str.casefold()
    c_tipo = _texto(c["Tipo de Operación"])
    importe = _num(c["Importe (€)"])
    sobre = _num(c["Sobrepuja (€)"])
    pct = _num(c["% Sobrepuja (uso interno)"])

    def suma(tipo):
        return persona.map(importe[c_tipo.eq(tipo)].groupby(c_persona[c_tipo.eq(tipo)]).sum()).fillna(0.0)

    compras, ventas, abonos = suma("Compra"), suma("Venta"), suma("Abono")
    p["Total Compras (€)"] = compras
    p["Total Ventas (€)"] = ventas
    p["Balance Total (€)"] = SALDO_INICIAL + ventas - compras + abonos

    pl_dueno = _texto(plantillas["Participante"]).str.casefold()
    p["Valor de Equipo (€)"] = persona.map(_num(plantillas["Valor Actual (€)"]).groupby(pl_dueno).sum()).fillna(0.0)
    p["Patrimonio Total (€)"] = p["Balance Total (€)"] + p["Valor de Equipo (€)"]
    p["Variación Diaria (€)"] = persona.map(_num(plantillas["Variación Diaria (€)"]).groupby(pl_dueno).sum()).fillna(0.0)

    es_compra = c_tipo.eq("Compra")
    n_compras = persona.map(es_compra.groupby(c_persona).sum()).fillna(0).astype(int)
    p["Compras Registradas"] = n_compras

    media_sobre = persona.map(sobre[es_compra].groupby(c_persona[es_compra]).mean())   # NaN si no hay
    p["Sobrepuja Media Personal (€)"] = media_sobre.where(n_compras > 0)
    media_global = sobre[es_compra].mean()
    p["Índice Fichajes (usado en predicción) (€)"] = np.where(n_compras >= 2, media_sobre, media_global)
    p["Perfil de Fichajes"] = p["Índice Fichajes (usado en predicción) (€)"].map(_perfil)

    pct_personal = persona.map(pct[es_compra].groupby(c_persona[es_compra]).mean()).fillna(0.0)
    pct_global = pct[es_compra].mean()
    p["Tasa Sobrepuja % (shrinkage, uso interno predicción)"] = (
        (n_compras * pct_personal + 3 * pct_global) / (n_compras + 3))

    orden = ["Persona", "Total Compras (€)", "Total Ventas (€)", "Balance Total (€)",
             "Valor de Equipo (€)", "Patrimonio Total (€)", "Variación Diaria (€)",
             "Compras Registradas", "Sobrepuja Media Personal (€)",
             "Índice Fichajes (usado en predicción) (€)", "Perfil de Fichajes",
             "Tasa Sobrepuja % (shrinkage, uso interno predicción)"]
    resto = [col for col in p.columns if col not in orden]
    return p[orden + resto]


# ------------------------------------------------------------------- todo junto
COLUMNAS_NECESARIAS = {
    "Biwenger_Export": ["Equipo", "Jugador", "Posición", "Puntos", "Precio", "PJ", "Casa", "Fuera"],
    "Biwenger_Ayer": ["Equipo", "Jugador", "Posición", "Precio"],
    "PJ_Split": ["Jugador", "Equipo", "Pts C", "Pts F"],
    "Multiposicion": ["Jugador", "Posición (Opcional/Multi)"],
    "Plantillas": ["Jugador", "Equipo", "Participante"],
    "Contabilidad": ["Persona", "Tipo de Operación", "Jugador", "Equipo",
                     "Importe (€)", "Valor Mercado (€)"],
    "Participantes": ["Persona"],
}


def _con_columnas(df, columnas):
    """La hoja con al menos esas columnas (vacías si faltan): una hoja ausente
    o recién creada no debe tumbar la app, solo dejar ese dato sin calcular."""
    df = pd.DataFrame() if df is None else df.copy()
    for col in columnas:
        if col not in df.columns:
            df[col] = np.nan
    return df


def calcular_todo(hojas):
    """Recibe un dict {nombre de hoja: DataFrame en bruto} y devuelve las cuatro
    hojas calculadas: mercado, plantillas, contabilidad y participantes."""
    hojas = {n: _con_columnas(hojas.get(n), cols) for n, cols in COLUMNAS_NECESARIAS.items()}
    vacia = pd.DataFrame()
    mercado = mercado_global(hojas["Biwenger_Export"], hojas["Biwenger_Ayer"],
                             hojas["Plantillas"], hojas.get("PJ_Split", vacia),
                             hojas.get("Multiposicion", vacia))
    plantillas = completar_plantillas(hojas["Plantillas"], mercado)
    contabilidad = completar_contabilidad(hojas["Contabilidad"], mercado)
    part = participantes(hojas["Participantes"], contabilidad, plantillas)
    return {"mercado": mercado, "plantillas": plantillas,
            "contabilidad": contabilidad, "participantes": part}


HOJAS_BRUTAS = ("Biwenger_Export", "Biwenger_Ayer", "PJ_Split", "Multiposicion",
                "Plantillas", "Contabilidad", "Participantes")


def calcular_desde_excel(ruta):
    """Lee del Excel solo las hojas en bruto y devuelve las cuatro calculadas."""
    libro = pd.ExcelFile(ruta)
    try:
        hojas = {}
        for nombre in HOJAS_BRUTAS:
            try:
                hojas[nombre] = pd.read_excel(libro, sheet_name=nombre)
            except ValueError:            # hoja que no existe
                hojas[nombre] = pd.DataFrame()
        return calcular_todo(hojas)
    finally:
        libro.close()


def calcular_desde_almacen(ruta=None):
    """Lo mismo, leyendo las hojas en bruto de biwenger.db."""
    import almacen
    hojas = {}
    for nombre in HOJAS_BRUTAS:
        try:
            hojas[nombre] = almacen.leer_hoja(nombre, ruta)
        except ValueError:
            hojas[nombre] = pd.DataFrame()
    return calcular_todo(hojas)
