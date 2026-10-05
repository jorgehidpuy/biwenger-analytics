# -*- coding: utf-8 -*-
"""Almacén de datos de la app: una base SQLite (biwenger.db) en lugar del Excel.

CÓMO ESTÁ GUARDADO
Cada hoja de datos del antiguo Excel es una tabla con sus columnas de verdad
(Contabilidad, Plantillas, Biwenger_Export...). La tabla `_hojas` recuerda, de
cada una, en qué fila iba la cabecera y los rótulos originales, para poder
seguir viéndola como una hoja.

El Histórico NO va como hoja: en el Excel era un bloque de 8 columnas por día
(más de 400 columnas a final de temporada, por encima del límite de SQLite).
Aquí es una tabla larga normal, `historico`, con una fila por jugador y día.

POR QUÉ HAY UNA "HOJA" DE MENTIRA
Mucho código del bot y de la app escribe celda a celda con la interfaz de
openpyxl (hoja.cell(fila, col).value = ...). Reescribirlo todo de golpe era el
mayor riesgo de la migración, así que `abrir()` devuelve un libro que imita
esa interfaz sobre las tablas: el código de siempre funciona sin cambios, y
lo que se guarda son tablas normales. Las funciones se pueden ir pasando a
SQL directo poco a poco.

Uso:
    libro = almacen.abrir()            # como openpyxl.load_workbook()
    hoja = libro["Contabilidad"]
    hoja.cell(5, 2).value = "Nike"
    libro.guardar()                    # una sola transacción

    df = almacen.leer_hoja("Plantillas")   # como pd.read_excel(sheet_name=...)
"""
import json
import os
import re
import shutil
import sqlite3
from datetime import date, datetime, time

import numpy as np
import pandas as pd

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_DB = os.path.join(CARPETA, "biwenger.db")
COPIAS_A_GUARDAR = 7

HIST_COLS = ["Jugador", "Equipo", "Posición", "Puntos", "Media Puntos",
             "Valor Actual (€)", "Variación Diaria (€)"]


# ------------------------------------------------------------------ conexión
def _a_texto_fecha(valor):
    if isinstance(valor, datetime):
        return valor.isoformat(sep=" ")
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, time):
        return valor.isoformat()
    return valor


sqlite3.register_adapter(datetime, _a_texto_fecha)
sqlite3.register_adapter(date, _a_texto_fecha)
sqlite3.register_adapter(time, _a_texto_fecha)


def _leer_fecha(bruto):
    """Columnas FECHA: vuelven como datetime; si no parece fecha, como texto."""
    texto = bruto.decode("utf-8")
    for formato in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            pass
    return texto


def _leer_hora(bruto):
    texto = bruto.decode("utf-8")
    try:
        return time.fromisoformat(texto)
    except ValueError:
        return texto


sqlite3.register_converter("FECHA", _leer_fecha)
sqlite3.register_converter("HORA", _leer_hora)


def conectar(ruta=None):
    con = sqlite3.connect(ruta or RUTA_DB, timeout=60, detect_types=sqlite3.PARSE_DECLTYPES)
    # Diario clásico (no WAL): cada escritura cambia la fecha del archivo, que
    # es lo que usa la app para saber que hay datos nuevos y refrescar cachés.
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("""CREATE TABLE IF NOT EXISTS _hojas (
                       nombre TEXT PRIMARY KEY, fila_cabecera INTEGER NOT NULL,
                       rotulos TEXT NOT NULL, columnas TEXT NOT NULL)""")
    return con


def existe(ruta=None):
    return os.path.exists(ruta or RUTA_DB)


def _q(nombre):
    return '"' + str(nombre).replace('"', '""') + '"'


# ------------------------------------------------------------ valores limpios
def _limpio(valor):
    """Lo que se guarda: tipos de Python normales, sin NaN ni tipos de numpy."""
    if valor is None:
        return None
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.floating, float)):
        return None if np.isnan(valor) else float(valor)
    if isinstance(valor, np.bool_):
        return bool(valor)
    if isinstance(valor, pd.Timestamp):
        return None if pd.isna(valor) else valor.to_pydatetime()
    if valor is pd.NaT:
        return None
    if isinstance(valor, str) and valor == "":
        return None
    return valor


def _nombres_columna(rotulos):
    """Nombres únicos como los pone pandas al leer un Excel: los vacíos son
    'Unnamed: N' y los repetidos llevan '.1', '.2'..."""
    nombres, vistos = [], {}
    for i, r in enumerate(rotulos):
        base = f"Unnamed: {i}" if r is None or str(r).strip() == "" else str(r)
        nombre = base
        if base in vistos:
            vistos[base] += 1
            nombre = f"{base}.{vistos[base]}"
        else:
            vistos[base] = 0
        nombres.append(nombre)
    return nombres


# --------------------------------------------------------------- hoja falsa
class _Estilo:
    """Fuente, alineación, formato de número...: en una base de datos no
    significan nada, así que se aceptan y se ignoran."""

    def __getattr__(self, nombre):
        return None


class Celda:
    __slots__ = ("_hoja", "row", "column")

    def __init__(self, hoja, row, column):
        self._hoja, self.row, self.column = hoja, row, column

    @property
    def value(self):
        return self._hoja._valor(self.row, self.column)

    @value.setter
    def value(self, valor):
        self._hoja._poner(self.row, self.column, valor)

    # Estilos de Excel: se aceptan y no hacen nada
    number_format = font = alignment = fill = border = property(
        lambda self: _Estilo(), lambda self, valor: None)


class _Celdas:
    ranges = ()


class Hoja:
    """Una tabla vista como hoja de openpyxl: filas y columnas desde 1."""

    def __init__(self, libro, nombre, filas=None, fila_cabecera=1):
        self.libro, self.title = libro, nombre
        self.fila_cabecera = fila_cabecera
        self._filas = filas or []          # lista de listas; _filas[0] = fila 1
        self.sheet_state = "visible"
        self.tables = {}
        self.merged_cells = _Celdas()
        self.cambiada = False

    # -- lectura
    def _valor(self, fila, col):
        if 1 <= fila <= len(self._filas):
            f = self._filas[fila - 1]
            if 1 <= col <= len(f):
                return f[col - 1]
        return None

    @property
    def max_row(self):
        return max(len(self._filas), 1)

    @property
    def max_column(self):
        return max((len(f) for f in self._filas), default=1) or 1

    def cell(self, row, column, value=None):
        celda = Celda(self, row, column)
        if value is not None:
            celda.value = value
        return celda

    def __getitem__(self, fila):
        if not isinstance(fila, int):
            raise TypeError("Solo se admite hoja[número de fila]")
        return tuple(Celda(self, fila, c) for c in range(1, self.max_column + 1))

    def iter_rows(self, min_row=1, max_row=None, min_col=1, max_col=None, values_only=False):
        max_row = max_row or self.max_row
        max_col = max_col or self.max_column
        for r in range(min_row, max_row + 1):
            if values_only:
                yield tuple(self._valor(r, c) for c in range(min_col, max_col + 1))
            else:
                yield tuple(Celda(self, r, c) for c in range(min_col, max_col + 1))

    # -- escritura
    def _poner(self, fila, col, valor):
        while len(self._filas) < fila:
            self._filas.append([])
        f = self._filas[fila - 1]
        while len(f) < col:
            f.append(None)
        f[col - 1] = _limpio(valor)
        self.cambiada = True

    def append(self, valores):
        vacia = all(all(v is None for v in f) for f in self._filas)
        destino = 1 if vacia else len(self._filas) + 1
        for c, v in enumerate(valores, 1):
            self._poner(destino, c, v)

    def delete_rows(self, idx, amount=1):
        del self._filas[idx - 1: idx - 1 + amount]
        self.cambiada = True

    def merge_cells(self, *a, **k):
        pass

    def unmerge_cells(self, *a, **k):
        pass

    # -- conversión
    def _recortar(self):
        while self._filas and all(v is None for v in self._filas[-1]):
            self._filas.pop()

    def a_tabla(self):
        """(rótulos, filas de datos) para guardar."""
        self._recortar()
        h = self.fila_cabecera
        rotulos = list(self._filas[h - 1]) if len(self._filas) >= h else []
        ancho = max([len(rotulos)] + [len(f) for f in self._filas[h:]] or [0])
        rotulos += [None] * (ancho - len(rotulos))
        datos = [list(f) + [None] * (ancho - len(f)) for f in self._filas[h:]]
        # Columnas sobrantes a la derecha, sin rótulo ni datos: fuera
        while ancho and (ancho > len(rotulos) or rotulos[ancho - 1] is None) and \
                all(len(f) < ancho or f[ancho - 1] is None for f in self._filas[h:]):
            ancho -= 1
        rotulos = rotulos[:ancho]
        datos = [f[:ancho] for f in datos]
        return rotulos, datos


class Libro:
    """Imita lo justo de un Workbook de openpyxl."""

    def __init__(self, ruta=None):
        self.ruta = ruta or RUTA_DB
        self._hojas = {}
        con = conectar(self.ruta)
        try:
            self._nombres = [n for (n,) in con.execute("SELECT nombre FROM _hojas ORDER BY rowid")]
        finally:
            con.close()

    @property
    def sheetnames(self):
        return list(self._nombres)

    @property
    def worksheets(self):
        return [self[n] for n in self._nombres]

    def __contains__(self, nombre):
        return nombre in self._nombres

    def __getitem__(self, nombre):
        if nombre not in self._nombres:
            raise KeyError(f"No existe la hoja {nombre!r}")
        if nombre not in self._hojas:
            self._hojas[nombre] = _cargar_hoja(self, nombre)
        return self._hojas[nombre]

    def create_sheet(self, nombre):
        hoja = Hoja(self, nombre)
        hoja.cambiada = True
        self._hojas[nombre] = hoja
        if nombre not in self._nombres:
            self._nombres.append(nombre)
        return hoja

    def guardar(self):
        """Guarda las hojas que han cambiado, todas en una misma transacción:
        o entran todas o no entra ninguna."""
        cambiadas = [h for h in self._hojas.values() if h.cambiada]
        if not cambiadas:
            return 0
        con = conectar(self.ruta)
        try:
            with con:
                for hoja in cambiadas:
                    rotulos, datos = hoja.a_tabla()
                    _escribir_tabla(con, hoja.title, rotulos, datos, hoja.fila_cabecera)
                    hoja.cambiada = False
        finally:
            con.close()
        return len(cambiadas)

    # Compatibilidad con openpyxl
    def save(self, _ruta=None):
        self.guardar()

    def close(self):
        pass


def abrir(ruta=None, **_ignorado):
    """Como openpyxl.load_workbook(): data_only, read_only... no aplican."""
    return Libro(ruta)


# ------------------------------------------------------------ tablas en disco
def _tipo_columna(valores):
    if any(isinstance(v, (datetime, date)) for v in valores):
        return "FECHA"
    if any(isinstance(v, time) for v in valores):
        return "HORA"
    return ""          # sin tipo: SQLite guarda cada valor tal cual (número o texto)


def _escribir_tabla(con, nombre, rotulos, datos, fila_cabecera=1):
    columnas = _nombres_columna(rotulos)
    tipos = [_tipo_columna([f[i] for f in datos]) for i in range(len(columnas))]
    con.execute(f"DROP TABLE IF EXISTS {_q(nombre)}")
    if columnas:
        definicion = ", ".join(f"{_q(c)} {t}".strip() for c, t in zip(columnas, tipos))
        con.execute(f"CREATE TABLE {_q(nombre)} ({definicion})")
        if datos:
            marcas = ", ".join("?" * len(columnas))
            con.executemany(f"INSERT INTO {_q(nombre)} VALUES ({marcas})",
                            [[_limpio(v) for v in f] for f in datos])
    else:
        con.execute(f"CREATE TABLE {_q(nombre)} (_vacia)")
    con.execute("INSERT OR REPLACE INTO _hojas VALUES (?, ?, ?, ?)",
                (nombre, fila_cabecera, json.dumps(rotulos, ensure_ascii=False, default=str),
                 json.dumps(columnas, ensure_ascii=False)))


def _leer_tabla(con, nombre):
    """(fila_cabecera, rótulos, columnas, filas) o None si no existe."""
    meta = con.execute("SELECT fila_cabecera, rotulos, columnas FROM _hojas WHERE nombre = ?",
                       (nombre,)).fetchone()
    if meta is None:
        return None
    fila_cabecera, rotulos, columnas = meta[0], json.loads(meta[1]), json.loads(meta[2])
    filas = [list(f) for f in con.execute(f"SELECT * FROM {_q(nombre)}")] if columnas else []
    return fila_cabecera, rotulos, columnas, filas


def _cargar_hoja(libro, nombre):
    con = conectar(libro.ruta)
    try:
        fila_cabecera, rotulos, _cols, filas = _leer_tabla(con, nombre)
    finally:
        con.close()
    rejilla = [[] for _ in range(fila_cabecera - 1)] + [list(rotulos)] + filas
    return Hoja(libro, nombre, rejilla, fila_cabecera)


def hojas(ruta=None):
    con = conectar(ruta)
    try:
        return [n for (n,) in con.execute("SELECT nombre FROM _hojas ORDER BY rowid")]
    finally:
        con.close()


def leer_hoja(nombre, ruta=None):
    """Como pd.read_excel(ruta, sheet_name=nombre): un DataFrame con la fila de
    cabecera como nombres de columna. Hoja inexistente: ValueError."""
    con = conectar(ruta)
    try:
        leida = _leer_tabla(con, nombre)
    finally:
        con.close()
    if leida is None:
        raise ValueError(f"Worksheet named '{nombre}' not found")
    _h, _rotulos, columnas, filas = leida
    df = pd.DataFrame(filas, columns=columnas)
    for col in df.columns:
        # Columnas que en SQLite son números guardados como enteros y vacíos:
        # pandas las deja como object; al leer el Excel salían numéricas.
        if df[col].dtype == object:
            no_nulos = df[col].dropna()
            if len(no_nulos) and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                     for v in no_nulos):
                df[col] = pd.to_numeric(df[col])
            elif len(no_nulos) and all(isinstance(v, datetime) for v in no_nulos):
                df[col] = pd.to_datetime(df[col])
    return df


# ----------------------------------------------------------------- histórico
def _crear_historico(con):
    con.execute("""CREATE TABLE IF NOT EXISTS historico (
                       fecha FECHA NOT NULL,
                       orden INTEGER NOT NULL,
                       "Jugador" TEXT, "Equipo" TEXT, "Posición" TEXT, "Puntos",
                       "Media Puntos", "Valor Actual (€)", "Variación Diaria (€)",
                       PRIMARY KEY (fecha, orden))""")


def historico_fechas(ruta=None):
    con = conectar(ruta)
    try:
        _crear_historico(con)
        return [f for (f,) in con.execute("SELECT DISTINCT fecha FROM historico ORDER BY fecha")]
    finally:
        con.close()


def historico_leer(ruta=None):
    """Todo el histórico: columnas Fecha, Fecha_Texto y las de HIST_COLS."""
    con = conectar(ruta)
    try:
        _crear_historico(con)
        filas = con.execute(f"""SELECT fecha, {", ".join(_q(c) for c in HIST_COLS)}
                                FROM historico ORDER BY fecha, orden""").fetchall()
    finally:
        con.close()
    df = pd.DataFrame(filas, columns=["Fecha"] + HIST_COLS)
    if not df.empty:
        df["Fecha"] = pd.to_datetime(df["Fecha"])
        df.insert(1, "Fecha_Texto", df["Fecha"].dt.strftime("%d/%m/%Y"))
    else:
        df.insert(1, "Fecha_Texto", pd.Series(dtype=str))
    return df


def historico_anadir_dia(fecha, filas, con=None, ruta=None):
    """Añade el bloque de un día. `filas`: lista de dicts con HIST_COLS.
    Devuelve False si ese día ya estaba."""
    propia = con is None
    con = con or conectar(ruta)
    try:
        _crear_historico(con)
        dia = datetime(fecha.year, fecha.month, fecha.day)
        if con.execute("SELECT 1 FROM historico WHERE fecha = ? LIMIT 1", (dia,)).fetchone():
            return False
        with con:
            con.executemany(
                f"""INSERT INTO historico (fecha, orden, {", ".join(_q(c) for c in HIST_COLS)})
                    VALUES ({", ".join("?" * (len(HIST_COLS) + 2))})""",
                [[dia, i] + [_limpio(f.get(c)) for c in HIST_COLS] for i, f in enumerate(filas)])
        return True
    finally:
        if propia:
            con.close()


def historico_borrar_ultimo(ruta=None):
    """Borra el último día. Devuelve su fecha o None si no había ninguno."""
    con = conectar(ruta)
    try:
        _crear_historico(con)
        ultima = con.execute("SELECT MAX(fecha) FROM historico").fetchone()[0]
        if ultima is None:
            return None
        with con:
            con.execute("DELETE FROM historico WHERE fecha = ?", (ultima,))
        return ultima
    finally:
        con.close()


# ------------------------------------------------------------------ copias
def copia_de_seguridad(ruta=None):
    """Copia de la base en la carpeta 'copias' (se guardan las últimas siete).
    Usa la copia en caliente de SQLite: vale aunque la app la esté leyendo."""
    ruta = ruta or RUTA_DB
    if not os.path.exists(ruta):
        return None
    carpeta = os.path.join(os.path.dirname(ruta) or ".", "copias")
    os.makedirs(carpeta, exist_ok=True)
    base = os.path.basename(ruta)
    destino = os.path.join(carpeta, f"{datetime.now():%Y%m%d_%H%M%S}_{base}")
    origen = sqlite3.connect(ruta, timeout=60)
    try:
        copia = sqlite3.connect(destino)
        with copia:
            origen.backup(copia)
        copia.close()
    finally:
        origen.close()
    copias = sorted(f for f in os.listdir(carpeta) if f.endswith("_" + base))
    for vieja in copias[:-COPIAS_A_GUARDAR]:
        try:
            os.remove(os.path.join(carpeta, vieja))
        except OSError:
            pass
    return destino


# ---------------------------------------------------------- exportar a Excel
def exportar_a_excel(destino, ruta=None, calculadas=None):
    """Un Excel de consulta con todas las tablas (no es de donde lee la app).

    `calculadas`: {nombre de hoja: DataFrame} que sustituyen a la tabla en bruto
    o se añaden (p. ej. el mercado y los saldos ya calculados)."""
    calculadas = dict(calculadas or {})
    with pd.ExcelWriter(destino) as escritor:
        for nombre, df in calculadas.items():
            df.to_excel(escritor, sheet_name=nombre[:31], index=False)
        for nombre in hojas(ruta):
            if nombre not in calculadas:
                leer_hoja(nombre, ruta).to_excel(escritor, sheet_name=nombre[:31], index=False)
        historico_leer(ruta).drop(columns=["Fecha_Texto"]).to_excel(
            escritor, sheet_name="Historico", index=False)
    return destino
