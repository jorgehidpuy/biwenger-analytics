import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from sklearn.ensemble import RandomForestRegressor, GradientBoostingClassifier, GradientBoostingRegressor
import numpy as np
import os
import hashlib
import itertools
import bisect
from collections import Counter
import urllib.parse
import base64
import uuid
import time
from datetime import datetime, timedelta
import subprocess
import shutil
import re
import unicodedata
import calculos
import almacen

# 1. Configuración de la App
# 🌑 Tema oscuro por defecto en todos los gráficos. Plotly viene con el tema
# claro, y aunque a los gráficos se les ponía el papel transparente, hay zonas
# con fondo propio que no se heredan: el área circular de los radares salía
# BLANCA sobre el fondo oscuro de la app, con las etiquetas ilegibles. Lo mismo
# pasaba con el ranking de patrimonio y la tarta del Puesto de Mando, que no
# llevaban ningún ajuste de color.
pio.templates.default = "plotly_dark"

st.set_page_config(
    page_title="Biwenger 26/27",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ⚽ PANTALLA DE CARGA.
# Arrancar cuesta unos segundos: hay que leer catorce hojas del Excel, recorrer
# el histórico entero y recalibrar el motor. Sin nada en pantalla, esos segundos
# parecen que la app se ha colgado. Se pinta ya —antes de tocar el Excel— y se
# borra sola al final del todo, cuando ya hay algo que mirar.
#
# SOLO LA PRIMERA VEZ, eso sí. Streamlit vuelve a ejecutar el script entero cada
# vez que tocas un filtro o añades un jugador a un gráfico, y taparle la
# pantalla a alguien que acaba de pulsar un desplegable es peor que no poner
# nada: lo pesado ya está en caché y esa vuelta dura décimas. Cuando algo vacía
# las cachés (importar un día, asignar jornada) se marca aquí para que la
# siguiente vuelta sí la enseñe.
_es_carga_pesada = not st.session_state.get('app_ya_cargada')
# 🧭 Y al CAMBIAR DE SECCIÓN, una transición discreta. Streamlit vuelve a
# ejecutar la app entera y, mientras, deja a la vista los elementos de la
# pantalla anterior medio transparentes y los va sustituyendo uno a uno: lo
# primero de la sección nueva caía en el hueco del panel del menú y durante un
# par de segundos se mezclaban botones fantasma con lo nuevo. Esta pantalla lo
# tapa y se quita en la última línea, como la del balón.
_cambio_de_seccion = st.session_state.pop('cambio_de_seccion', None)
_pantalla_carga = st.empty()
if not _es_carga_pesada and _cambio_de_seccion:
    _pantalla_carga.markdown(
        f"""
        <div class="transicion-seccion" style="position:fixed; inset:0; z-index:9999;
                    background:linear-gradient(180deg,#0b0e14 0%,#10131b 100%);
                    display:flex; flex-direction:column; align-items:center; justify-content:center;
                    gap:16px;">
            <div class="transicion-aro"></div>
            <div style="color:#8b93a7; font-family:system-ui,sans-serif; font-size:0.8rem;
                        letter-spacing:0.16em; text-transform:uppercase;">{_cambio_de_seccion}</div>
        </div>
        <style>
            /* Lo viejo, invisible mientras dura la transición: aunque algo
               asomara por detrás, no se vería la mezcla. */
            [data-stale="true"] {{ opacity:0 !important; }}
            /* Entra en un suspiro y, por si una sección fallara, se aparta sola
               a los diez segundos para no tapar el error. */
            .transicion-seccion {{ animation: tr-entra 0.12s ease both, tr-sale 0.3s ease 10s forwards; }}
            .transicion-aro {{ width:34px; height:34px; border-radius:50%;
                               border:3px solid rgba(231,197,101,0.18); border-top-color:#e7c565;
                               animation: tr-gira 0.8s linear infinite; }}
            @keyframes tr-gira {{ to {{ transform:rotate(360deg); }} }}
            @keyframes tr-entra {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
            @keyframes tr-sale {{ to {{ opacity:0; visibility:hidden; }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )
if _es_carga_pesada:
    _pantalla_carga.markdown(
        """
        <div style="position:fixed; inset:0; z-index:9999;
                    background:linear-gradient(180deg,#0b0e14 0%,#10131b 100%);
                    display:flex; flex-direction:column; align-items:center; justify-content:center;
                    gap:18px;">
            <div style="font-size:4.5rem; line-height:1; animation:girar 1.1s linear infinite;">⚽</div>
            <div style="color:#8b93a7; font-family:system-ui,sans-serif; font-size:0.95rem;
                        letter-spacing:0.08em; text-transform:uppercase;">Cargando la liga</div>
        </div>
        <style>
            @keyframes girar { from { transform:rotate(0deg); } to { transform:rotate(360deg); } }
        </style>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <style>
        /* 🧭 EL BOTÓN PARA DESPLEGAR EL MENÚ SE VE SIEMPRE.
           Esta regla lo ocultaba (de cuando no había barra lateral), así que al
           plegar el menú no quedaba manera de volver a abrirlo. Van los dos
           nombres porque Streamlit lo renombró por el camino. */
        [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] {
            visibility: visible !important; opacity: 1 !important; z-index: 1000 !important;
        }

        /* Sin la cabecera propia, el contenido empezaba pegado al borde y el
           botón del menú se le montaba encima. */
        [data-testid="stAppViewContainer"] > .main .block-container,
        [data-testid="stMainBlockContainer"] { padding-top: 3.2rem !important; }

        /* --- 🏟️ FONDO (versión sobria, menos "gaming") --- */
        body, .stApp, [data-testid="stAppViewContainer"] {
            background: linear-gradient(180deg, #0b0e14 0%, #10131b 100%) !important;
        }

        [data-testid="stHeader"] {
            background: transparent !important;
        }

        /* 🙈 Fuera la barra de Streamlit (botón Deploy y menú ⋮): esto es una
           aplicación, no un cuaderno. El indicador de "corriendo" se conserva,
           que sí informa. */
        [data-testid="stToolbar"], [data-testid="stDecoration"],
        [data-testid="stAppDeployButton"], #MainMenu, footer { display: none !important; }

        /* --- 🌓 TEXTO CLARO SOBRE EL FONDO OSCURO ---
           El fondo se pinta a mano aquí arriba, pero el COLOR DEL TEXTO lo pone
           el tema de Streamlit, y sin un .streamlit/config.toml ese tema lo
           decide el navegador o el sistema. En modo claro, Streamlit escribe sus
           textos casi en negro y quedan negro sobre negro: títulos como
           "#### Resumen · ...", las etiquetas de las métricas, los captions y
           los rótulos de los filtros se volvían ilegibles.

           Ojo: SIN !important a propósito. Así, cualquier elemento que la app
           pinte con su propio color en línea (el "🪑 Banquillo" oscuro sobre
           fondo claro, por ejemplo) sigue mandando sobre esta regla. */
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3,
        [data-testid="stMarkdownContainer"] h4,
        [data-testid="stMarkdownContainer"] h5,
        [data-testid="stMarkdownContainer"] h6,
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li,
        [data-testid="stMarkdownContainer"] strong,
        [data-testid="stHeadingWithActionElements"],
        [data-testid="stWidgetLabel"] p,
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] p,
        [data-testid="stMetricValue"],
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary p {
            color: #e9edf5;
        }

        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p,
        [data-testid="stMetricDelta"] ~ div {
            color: #9aa3b2;
        }

        /* Opciones de radios y casillas, que también heredan del tema. */
        .stRadio label p, .stCheckbox label p, .stMultiSelect label p {
            color: #e9edf5;
        }

        /* --- TIPOGRAFÍA ---
           Dos familias en vez de una, que es como se hace en cualquier sitio
           cuidado: una serif con carácter para los titulares y una sans neutra
           para el resto. Todo en la misma fuente y del mismo grosor es lo que
           hace que una interfaz parezca salida de una plantilla. */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,500;9..144,600&display=swap');
        html, body, [class*="css"], p, span, div {
            font-family: 'Inter', sans-serif !important;
        }
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3,
        [data-testid="stMarkdownContainer"] h4 {
            font-family: 'Fraunces', Georgia, serif !important;
            font-weight: 600 !important;
            letter-spacing: -0.01em;
        }
        /* Los rótulos de los filtros y las métricas, discretos: en minúscula,
           pequeños y sin negrita. Antes competían con los datos. */
        [data-testid="stWidgetLabel"] p, [data-testid="stMetricLabel"] p {
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            color: #98a1b3 !important;
            letter-spacing: 0.01em;
        }

        /* --- FIX PARA ICONOS DE STREAMLIT ROTOS (_arrow_right) --- */
        .material-symbols-rounded, .material-icons, [data-testid="stIconMaterial"] {
            font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
        }

        /* --- 🎯 PESTAÑAS: barra sobria estilo panel de analítica deportiva --- */
        div[data-baseweb="tab-list"] {
            border-bottom: 1px solid rgba(255,255,255,0.08) !important;
            gap: 4px !important;
        }
        button[data-baseweb="tab"] {
            padding: 10px 16px !important;
        }
        button[data-baseweb="tab"] p {
            font-size: 14.5px !important;
            font-weight: 600 !important;
            letter-spacing: 0.2px !important;
            color: rgba(255,255,255,0.55) !important;
            transition: color 0.2s ease !important;
        }
        button[data-baseweb="tab"]:hover p { color: rgba(255,255,255,0.9) !important; }
        button[data-baseweb="tab"][aria-selected="true"] p {
            color: #e7c565 !important;
            text-shadow: none !important;
        }
        div[data-baseweb="tab-highlight"] {
            background-color: #e7c565 !important;
            box-shadow: none !important;
            height: 2px !important;
        }

        /* --- 📊 ESTILO PANEL MÉTRICAS (más plano, menos "cristal futurista") --- */
        [data-testid="stMetric"] {
            background: #151922;
            border: 1px solid rgba(255,255,255,0.08);
            padding: 14px 18px;
            border-radius: 6px;
            box-shadow: none;
            border-left: 3px solid #3a4a63;
        }

        /* --- 🃏 HOVER CARTAS --- */
        .fut-card { transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important; }
        .fut-card:hover { transform: translateY(-8px) scale(1.03) !important; box-shadow: 0 15px 25px rgba(0,0,0,0.9), 0 0 15px rgba(255,217,102,0.4) !important; z-index: 10 !important; border-color: #ffd966 !important; }

        /* --- 🖱️ SCROLLBAR --- */
        ::-webkit-scrollbar { width: 9px; height: 9px; }
        ::-webkit-scrollbar-track { background: rgba(20, 22, 30, 0.6); border-radius: 5px; }
        ::-webkit-scrollbar-thumb { background: #3a3f4b; border-radius: 5px; border: 2px solid #14161d; }
        ::-webkit-scrollbar-thumb:hover { background: #5a6270; }

        /* --- ⭐ JUGADOR ESTRELLA --- */
        @keyframes pulse-gold { 0% { box-shadow: 0 0 8px rgba(255, 215, 0, 0.4), 0 0 15px rgba(255, 215, 0, 0.2); } 50% { box-shadow: 0 0 15px rgba(255, 215, 0, 0.8), 0 0 25px rgba(255, 140, 0, 0.6); } 100% { box-shadow: 0 0 8px rgba(255, 215, 0, 0.4), 0 0 15px rgba(255, 215, 0, 0.2); } }
        .star-card { animation: pulse-gold 2s infinite !important; border: 2px solid #ffd700 !important; }
        .star-card:hover { animation: none !important; box-shadow: 0 15px 30px rgba(255, 215, 0, 0.9), 0 0 20px rgba(255, 140, 0, 0.8) !important; }

        /* --- ⚽ INDICADOR DE CARGA (discreto) --- */
        [data-testid="stStatusWidget"] svg { display: none !important; }
        [data-testid="stStatusWidget"]::before { content: ""; width: 14px; height: 14px; margin-right: 8px; display: inline-block; border: 2px solid rgba(231,197,101,0.35); border-top-color: #e7c565; border-radius: 50%; animation: girar-suave 0.8s linear infinite; }
        @keyframes girar-suave { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        /* --- 🎬 ANIMACIÓN FADE IN (más discreta) --- */
        @keyframes fadeInSlideUp { 0% { opacity: 0; transform: translateY(10px); } 100% { opacity: 1; transform: translateY(0); } }
        .animate-fade-in { animation: fadeInSlideUp 0.4s ease forwards; }

        /* --- 🏷️ CABECERA PRINCIPAL --- */
        .app-header-title { font-weight: 800 !important; letter-spacing: -0.5px !important; color: #f2f2f2 !important; }
        .app-header-rule { border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 14px 0 6px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

# 2. Motor de Carga de Datos y Autosanado
COPIAS_A_GUARDAR = 7


def guardar_excel(wb, ruta=None):
    """Guarda los cambios en la base de datos, con copia de seguridad previa.

    Se sigue llamando así porque la usan seis funciones de la app y el bot,
    pero ya no escribe un Excel: `wb` es un libro de almacen.py y se guarda en
    biwenger.db en una sola transacción (o entra todo o no entra nada). La
    copia va a la carpeta 'copias', donde se guardan las últimas siete.
    """
    try:
        almacen.copia_de_seguridad(getattr(wb, 'ruta', None))
    except Exception:
        pass          # que no poder copiar nunca impida guardar
    wb.guardar()


@st.cache_data(show_spinner=False, max_entries=1)
def excel_exportado(huella=None):
    """Todas las tablas de la base en un Excel (bytes), para descargarlo."""
    import io
    import tempfile
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, 'biwenger.xlsx')
        # Con los valores ya calculados (saldos, valores, mercado), no las
        # tablas en bruto, que tienen esas columnas vacías.
        calc = calculos.calcular_desde_almacen()
        almacen.exportar_a_excel(ruta, calculadas={
            'Participantes': calc['participantes'], 'Mercado': calc['mercado'],
            'Plantillas': calc['plantillas'], 'Contabilidad': calc['contabilidad']})
        with open(ruta, 'rb') as archivo:
            return io.BytesIO(archivo.read()).getvalue()


def resolver_excel_path():
    """Ruta de la base de datos (biwenger.db), o None si no existe.

    Conserva el nombre de cuando los datos estaban en un Excel porque lo
    llaman decenas de sitios para sacar la huella de las cachés."""
    return almacen.RUTA_DB if almacen.existe() else None


def _huella_pujas(contabilidad):
    """Huella de lo ÚNICO que entrena al modelo de pujas: las compras y las
    subastas perdidas registradas en Contabilidad.

    Va aparte de la huella del archivo a propósito. El backtest del modelo tarda
    unos 45 segundos (seis combinaciones de hiperparámetros validadas una a una,
    dejando fuera cada puja), y con la huella del archivo se rehacía cada vez que
    guardabas el Excel: pegar el export diario, meter un resultado, cualquier
    cosa. Pero los precios del día no cambian nada de lo que el modelo aprende.
    Con esta huella el modelo se reentrena cuando aparece una puja nueva, que es
    cuando de verdad tiene algo que aprender, y las lecturas del día son
    instantáneas."""
    try:
        compras = contabilidad[contabilidad['Tipo de Operación'] == 'Compra']
        importes = pd.to_numeric(compras['Importe (€)'], errors='coerce').fillna(0).sum()
        perdidas = 0.0
        for i in range(1, 10):
            col = f'Subasta perdida {i}'
            if col in compras.columns:
                perdidas += pd.to_numeric(compras[col], errors='coerce').fillna(0).sum()
        return (len(compras), float(importes), float(perdidas))
    except Exception:
        return None


def _huella_excel(file_path):
    try:
        stat = os.stat(file_path)
        return (stat.st_mtime, stat.st_size)
    except Exception:
        return None


# 🩹 EL ESTADO DE CADA JUGADOR, TAL Y COMO LO DA BIWENGER
# La API distingue cinco estados y el bot los guarda en Biwenger_Export, pero
# la app los aplanaba en un sí/no: cualquier cosa que no fuera «ok» salía como
# lesionado, con la ambulancia, y fuera del once. Un sancionado parecía roto y
# una duda se quedaba en el banquillo aunque muchas veces juega. Y en los
# agentes libres ni se miraba: la lista de libres del tramo proponía a Iago
# Aspas, Stassin y Joan García, lesionados los tres.
#
# Ahora 'Lesion' significa "no puede jugar el próximo partido" (lesionado,
# sancionado o descartado) y 'Estado Biwenger' guarda el estado exacto, que es
# lo que decide el icono de la carta. Las dudas cuentan como disponibles: se
# marcan con una exclamación y decides tú.
ESTADOS_BIWENGER = {'ok': 'ok', 'injured': 'lesionado', 'doubt': 'duda',
                    'sanctioned': 'sancionado', 'discarded': 'descartado'}
NO_DISPONIBLE = ('lesionado', 'sancionado', 'descartado')
ETIQUETA_ESTADO = {'lesionado': 'lesionado', 'sancionado': 'sancionado',
                   'descartado': 'descartado por su club', 'duda': 'en duda'}


def posicion_real(guardada, de_biwenger):
    """La posición que vale: la de Biwenger, salvo multiposición que la incluya.

    Tu hoja Multiposicion y la columna Posición de Plantillas se escribieron a
    mano y no se enteran cuando Biwenger cambia a alguien de posición. Si lo
    guardado incluye la posición que da Biwenger hoy ("Centrocampista/
    Delantero" con Biwenger diciendo "Delantero"), se respeta: es una
    multiposición. Si no la incluye, lo guardado está desfasado y manda Biwenger."""
    api = str(de_biwenger or '').strip()
    actual = str(guardada or '').strip()
    if not api or api.lower() in ('nan', 'none'):
        return actual
    if api in [p.strip() for p in actual.split('/')]:
        return actual
    return api


def _aplicar_posicion_biwenger(guardadas, claves, mapa, completa):
    """Las posiciones con lo que dice Biwenger: tal cual si trae la posición
    completa (multiposición incluida), o con posicion_real si solo trae la
    principal."""
    nuevas = claves.map(mapa)
    if completa:
        return [str(n).strip() if isinstance(n, str) and n.strip() else g for g, n in zip(guardadas, nuevas)]
    return [posicion_real(g, n) for g, n in zip(guardadas, nuevas)]


def estado_jugador(player):
    """'ok', 'lesionado', 'duda', 'sancionado' o 'descartado'."""
    estado = str(player.get('Estado Biwenger') or '').strip().lower()
    if estado in ETIQUETA_ESTADO or estado == 'ok':
        return estado
    return 'lesionado' if str(player.get('Lesion', 'no')).strip().lower() == 'si' else 'ok'


# ⚠️ El parámetro se llama 'huella' y NO '_huella' a propósito. Streamlit ignora
# a efectos de caché cualquier argumento que empiece por guion bajo (es su
# escotilla para cosas no hasheables, como una conexión a base de datos). Con el
# guion bajo, la huella del Excel (fecha de modificación + tamaño) no entraba en
# la clave: se editaba el Excel, se refrescaba el navegador y la app seguía
# sirviendo los datos viejos hasta reiniciar el proceso. Sin él, cualquier cambio
# en el archivo invalida la caché y los datos se releen solos.
@st.cache_data
def load_data(huella=None):
    file_path = resolver_excel_path()
    if file_path is None:
        raise FileNotFoundError('No se encuentra la base de datos biwenger.db.')

    # 🗄️ Cada hoja es una tabla de biwenger.db (ver almacen.py). La fila de
    # cabecera de cada una ya va guardada, así que el header= de cuando se
    # leía el Excel no hace falta.
    def _hoja(nombre, **_kwargs):
        try:
            return almacen.leer_hoja(nombre, file_path)
        except Exception:
            return pd.DataFrame()

    # 🧮 SIN FÓRMULAS DEL EXCEL.
    # Mercado_Global y las columnas calculadas de Participantes, Plantillas y
    # Contabilidad se calculan en Python (calculos.py) a partir de las hojas en
    # bruto. Antes se leían los resultados de ~51.000 fórmulas, que exigían
    # recalcular el libro con Excel o LibreOffice tras cada guardado: si el
    # recálculo fallaba, la app enseñaba saldos a 0 € y plantillas vacías.
    # Comprobado el 02/10/2026: dan exactamente lo mismo que el Excel en
    # mercado, plantillas y saldos.
    _calculadas = calculos.calcular_todo({nombre: _hoja(nombre) for nombre in calculos.HOJAS_BRUTAS})
    df_participantes = _calculadas['participantes']
    df_contabilidad = _calculadas['contabilidad']
    df_plantillas = _calculadas['plantillas']

    # 👻 FILAS FANTASMA DE CONTABILIDAD.
    # La hoja arrastra fórmulas por debajo del último movimiento real (la columna
    # de Posición llega a la fila 1016 y la del % de sobrepuja a la 1000). Basta
    # con que UNA de esas celdas tenga un valor en caché para que pandas lea el
    # rango entero: 449 movimientos reales se convertían en 491 filas, y las 42
    # de relleno salían en la pestaña Movimientos como cartas de ABONO vacías
    # (sin importe, sin mánager y con un guion debajo), inflaban el recuento y
    # metían páginas en blanco al final del paginador.
    #
    # Un movimiento de verdad tiene SIEMPRE mánager y tipo de operación. Lo que
    # no los tenga no es un movimiento:
    #   - si además está vacío del todo, es relleno y se descarta en silencio;
    #   - si tiene algo escrito (un jugador, un importe), es una fila a medio
    #     rellenar y se avisa, porque ahí sí hay algo que corregir a mano.
    filas_fantasma_contabilidad = 0
    filas_incompletas_contabilidad = []
    if not df_contabilidad.empty and 'Persona' in df_contabilidad.columns:
        _cols_clave = [c for c in ('Fecha Fichaje', 'Persona', 'Tipo de Operación',
                                   'Jugador', 'Importe (€)') if c in df_contabilidad.columns]
        _con_algo = df_contabilidad[_cols_clave].notna().any(axis=1)
        _valida = (df_contabilidad['Persona'].notna()
                   & df_contabilidad.get('Tipo de Operación', pd.Series(dtype=object)).notna())
        filas_fantasma_contabilidad = int((~_valida & ~_con_algo).sum())
        # +2: la fila 0 del DataFrame es la 2 del Excel (debajo de la cabecera).
        filas_incompletas_contabilidad = [int(i) + 2 for i in
                                          df_contabilidad.index[~_valida & _con_algo]]
        df_contabilidad = df_contabilidad[_valida].reset_index(drop=True)

    # 💶 LAS VENTAS NO TIENEN SOBREPUJA.
    # La sobrepuja es lo que un comprador paga por encima del valor de mercado
    # para ganar una subasta. En una venta no hay nada de eso: se cobra el valor
    # de mercado y ya. Las ventas escritas a mano lo cumplían (la fórmula de la
    # columna solo calcula en las compras), pero las que apunta el bot traían
    # la diferencia entre el importe y el precio del día en que se ejecutó, que
    # no es beneficio de nadie: es cuánto se movió el precio entre la venta y
    # la lectura. En la pestaña Movimientos salían como "⬇ 66.000 €" en verde
    # debajo de una venta de Nike, como si hubiera ganado algo.
    if {'Tipo de Operación', 'Sobrepuja (€)'} <= set(df_contabilidad.columns):
        _es_venta = df_contabilidad['Tipo de Operación'].astype(str).str.strip() == 'Venta'
        df_contabilidad.loc[_es_venta, 'Sobrepuja (€)'] = 0.0
    df_mercado = _calculadas['mercado'].copy()
    df_calendario = _hoja('ClasificacionCalendario', header=1)

    df_plantillas['Jugador_Limpio'] = df_plantillas['Jugador'].astype(str).str.strip()
    df_mercado['Jugador_Limpio'] = df_mercado['Jugador'].astype(str).str.strip()

    # 🧹 Un jugador solo puede pertenecer una vez a un mánager, pero la hoja de
    # Plantillas puede acabar con la fila repetida (una fila pegada dos veces,
    # por ejemplo). Sin esta limpieza, el duplicado se propaga a todas partes: el
    # once ideal llegó a alinear a Mikel Rodriguez DOS VECES en el campito, la
    # plantilla contaba un jugador de más y su valor se sumaba por duplicado.
    # Solo se miran las filas con jugador Y mánager de verdad: la hoja arrastra
    # cientos de filas en blanco al final y, contándolas, el recuento salía en
    # 889 en vez de en 1.
    _validas = (df_plantillas['Jugador_Limpio'].str.lower().ne('nan')
                & df_plantillas['Jugador_Limpio'].str.strip().ne('')
                & df_plantillas['Participante'].notna())
    _repes = df_plantillas[_validas].duplicated(subset=['Jugador_Limpio', 'Participante'], keep='first')
    filas_duplicadas_plantillas = int(_repes.sum())
    if filas_duplicadas_plantillas:
        df_plantillas = df_plantillas.drop(index=df_plantillas[_validas].index[_repes]).reset_index(drop=True)
    
    # 🧹 Lo mismo en el mercado: al pegar el export a veces se cuela una fila
    # repetida (el 10/08 pasó con Moussa Diarra y Wanjala, y quedó registrado en
    # el histórico de ese día). Un jugador duplicado sale dos veces en la tabla
    # de Mercado y cuenta doble en los totales por equipo.
    _val_mk = (df_mercado['Jugador_Limpio'].str.lower().ne('nan')
               & df_mercado['Jugador_Limpio'].str.strip().ne('')
               & df_mercado['Equipo'].notna())
    _repes_mk = df_mercado[_val_mk].duplicated(subset=['Jugador_Limpio', 'Equipo'], keep='first')
    filas_duplicadas_mercado = int(_repes_mk.sum())
    if filas_duplicadas_mercado:
        df_mercado = df_mercado.drop(index=df_mercado[_val_mk].index[_repes_mk]).reset_index(drop=True)

    mapa_pos = df_mercado.drop_duplicates('Jugador_Limpio').set_index('Jugador_Limpio')['Posición']
    mapa_eq = df_mercado.drop_duplicates('Jugador_Limpio').set_index('Jugador_Limpio')['Equipo']

    pos_raw = df_plantillas['Posición'].astype(str).str.strip().replace(['nan', 'NaN', 'None', ''], np.nan)
    df_plantillas['Posición'] = df_plantillas['Jugador_Limpio'].map(mapa_pos).fillna(pos_raw)
    df_plantillas['Posición'] = df_plantillas['Posición'].fillna('Desconocido')

    eq_raw = df_plantillas['Equipo'].astype(str).str.strip().replace(['nan', 'NaN', 'None', ''], np.nan)
    df_plantillas['Equipo'] = df_plantillas['Jugador_Limpio'].map(mapa_eq).fillna(eq_raw)
    df_plantillas['Equipo'] = df_plantillas['Equipo'].fillna('Desconocido')

    # 🎮 PARTIDOS JUGADOS POR JUGADOR
    # Mercado_Global no trae PJ, pero el export crudo sí (columna 'PJ'). Es el dato
    # que dice cuánta confianza merece una media: 12,00 con un partido no vale lo
    # mismo que 12,00 con veinte. Lo usa el cálculo de puntos esperados del once
    # rival. Si la hoja no estuviera, se deduce como Puntos / Media Puntos, que es
    # literalmente la definición de la media.
    #
    # La clave es jugador + equipo, no solo el nombre: hay homónimos en la liga
    # (dos Moussa Diarra, uno en el Alavés y otro en el Málaga) y cruzarlos por
    # nombre les intercambia las estadísticas.
    df_mercado['_clave'] = df_mercado['Jugador_Limpio'] + '||' + df_mercado['Equipo'].astype(str).str.strip()
    _posicion_biwenger = None
    try:
        df_export = _hoja('Biwenger_Export')
        df_export['_clave'] = (df_export['Jugador'].astype(str).str.strip() + '||'
                               + df_export['Equipo'].astype(str).str.strip())
        mapa_pj = df_export.drop_duplicates('_clave').set_index('_clave')['PJ']
        df_mercado['PJ'] = pd.to_numeric(df_mercado['_clave'].map(mapa_pj), errors='coerce')
        # ⚽🅰️ Goles y asistencias, si el bot las ha traído de la API. Eran dos
        # columnas manuales de Plantillas que nadie rellenaba (todo a 0) y que
        # además solo existían para los 18 jugadores propios. Viniendo del
        # export las tiene TODO el mercado, así que las cartas de cualquier
        # pestaña pueden enseñarlas.
        for _col in ('Goles', 'Asistencias'):
            if _col in df_export.columns:
                _mapa = df_export.drop_duplicates('_clave').set_index('_clave')[_col]
                df_mercado[_col] = pd.to_numeric(df_mercado['_clave'].map(_mapa),
                                                 errors='coerce')
        # 🧭 La posición, la que diga Biwenger. Si el bot ha traído la columna
        # «Posiciones» (con la multiposición incluida), se usa TAL CUAL: si
        # Biwenger tiene a Eric García de DEF/MED sale DEF/MED, y si se lo deja
        # en DEF, sale DEF. La hoja manual Multiposicion ya no cuenta. Sin esa
        # columna (datos de antes, o si Biwenger no la diera), la de siempre:
        # la posición principal manda salvo que la multiposición guardada la
        # incluya (ver posicion_real).
        if 'Posiciones' in df_export.columns and df_export['Posiciones'].notna().any():
            _posicion_biwenger = (df_export.drop_duplicates('_clave').set_index('_clave')['Posiciones'], True)
        elif 'Posición' in df_export.columns:
            _posicion_biwenger = (df_export.drop_duplicates('_clave').set_index('_clave')['Posición'], False)
        if _posicion_biwenger is not None:
            df_mercado['Posición'] = _aplicar_posicion_biwenger(
                df_mercado['Posición'], df_mercado['_clave'], *_posicion_biwenger)
    except Exception:
        df_mercado['PJ'] = np.nan

    _pts_num = pd.to_numeric(df_mercado['Puntos'], errors='coerce')
    _med_num = pd.to_numeric(df_mercado['Media Puntos'], errors='coerce').replace(0, np.nan)
    df_mercado['PJ'] = df_mercado['PJ'].fillna((_pts_num / _med_num).round()).fillna(0).clip(lower=0)

    # 🏠✈️ Partidos y PUNTOS en casa y fuera.
    # Los PARTIDOS vienen exactos del propio export (columnas 'Casa' y 'Fuera',
    # que son recuentos de partidos, no de puntos). Los PUNTOS los acumula la app
    # en la hoja PJ_Split por diferencias entre importaciones.
    #
    # Las medias se calculan AQUÍ y no se leen de Mercado_Global: las fórmulas F
    # y G del Excel siguen partiendo de que 'Casa' y 'Fuera' eran puntos, así que
    # lo que hay en esas celdas no vale (dividían partidos entre partidos).
    for col in ('PJ Casa', 'PJ Fuera'):
        df_mercado[col] = np.nan
    try:
        df_export_split = df_export if not df_export.empty else _hoja('Biwenger_Export')
        df_export_split['_clave'] = (df_export_split['Jugador'].astype(str).str.strip() + '||'
                                     + df_export_split['Equipo'].astype(str).str.strip())
        export_unico = df_export_split.drop_duplicates('_clave').set_index('_clave')
        df_mercado['PJ Casa'] = pd.to_numeric(df_mercado['_clave'].map(export_unico['Casa']), errors='coerce')
        df_mercado['PJ Fuera'] = pd.to_numeric(df_mercado['_clave'].map(export_unico['Fuera']), errors='coerce')
    except Exception:
        pass

    try:
        df_split = _hoja('PJ_Split')
        df_split['_clave'] = (df_split['Jugador'].astype(str).str.strip() + '||'
                              + df_split['Equipo'].astype(str).str.strip())
        split_unico = df_split.drop_duplicates('_clave').set_index('_clave')
        pts_casa = pd.to_numeric(df_mercado['_clave'].map(split_unico['Pts C']), errors='coerce')
        pts_fuera = pd.to_numeric(df_mercado['_clave'].map(split_unico['Pts F']), errors='coerce')
        df_mercado['Media Puntos Casa'] = (pts_casa / df_mercado['PJ Casa'].replace(0, np.nan)).fillna(0)
        df_mercado['Media Puntos Fuera'] = (pts_fuera / df_mercado['PJ Fuera'].replace(0, np.nan)).fillna(0)
    except Exception:
        # Sin acumulado todavía (hoja vieja o recién creada), mejor cero que un
        # número inventado: un 0 se trata como "sin dato" en todo el cálculo.
        df_mercado['Media Puntos Casa'] = 0.0
        df_mercado['Media Puntos Fuera'] = 0.0

    df_plantillas['_clave'] = df_plantillas['Jugador_Limpio'] + '||' + df_plantillas['Equipo'].astype(str).str.strip()
    # La posición de Biwenger también en Plantillas. Iba arriba, antes de que
    # existiera esta clave, y por eso a tus fichas no les llegaba nunca.
    if _posicion_biwenger is not None:
        df_plantillas['Posición'] = _aplicar_posicion_biwenger(
            df_plantillas['Posición'], df_plantillas['_clave'], *_posicion_biwenger)
    _mercado_por_clave = df_mercado.drop_duplicates('_clave').set_index('_clave')
    mercado_unico = df_mercado.drop_duplicates('Jugador_Limpio').set_index('Jugador_Limpio')
    # Por jugador Y equipo, igual que el PJ de debajo: cruzarlo solo por nombre
    # mezclaba los datos de los homónimos (los dos Moussa Diarra), y una fila con
    # los partidos de uno y las medias del otro alimenta directamente el cálculo
    # del once. Si el jugador no aparece con ese equipo (por ejemplo si el Excel
    # de plantillas va un día por detrás de un traspaso), se recurre al nombre.
    for columna in ('Puntos', 'Media Puntos', 'Media Puntos Casa', 'Media Puntos Fuera'):
        df_plantillas[columna] = (df_plantillas['_clave'].map(_mercado_por_clave[columna])
                                  .fillna(df_plantillas['Jugador_Limpio'].map(mercado_unico[columna])))
    # Mismo criterio para los partidos jugados. El desglose casa/fuera además se
    # revisa después: si PJ Casa + PJ Fuera no cuadra con el PJ, se descarta.
    for columna in ('PJ', 'PJ Casa', 'PJ Fuera'):
        df_plantillas[columna] = (df_plantillas['_clave'].map(_mercado_por_clave[columna])
                                  .fillna(df_plantillas['Jugador_Limpio'].map(mercado_unico[columna])))
    df_plantillas['PJ'] = df_plantillas['PJ'].fillna(0)

    # ⚽🅰️ Goles y asistencias. Manda lo que traiga el mercado (viene de la API
    # por el export y está al día); la columna escrita a mano en Plantillas se
    # queda como respaldo para quien no aparezca en el mercado. Antes era al
    # revés y, como nadie las rellenaba, todas las cartas enseñaban 0.
    for col_manual in ['Goles', 'Asistencias']:
        _manual = (pd.to_numeric(df_plantillas[col_manual], errors='coerce')
                   if col_manual in df_plantillas.columns else pd.Series(np.nan, index=df_plantillas.index))
        if col_manual in df_mercado.columns:
            _api = df_plantillas['_clave'].map(_mercado_por_clave[col_manual]).fillna(
                df_plantillas['Jugador_Limpio'].map(mercado_unico[col_manual]))
            _manual = pd.to_numeric(_api, errors='coerce').fillna(_manual)
        df_plantillas[col_manual] = _manual.fillna(0).astype(int)
        if col_manual not in df_mercado.columns:
            df_mercado[col_manual] = 0

    # Lógica de Lesión
    if 'Lesion' in df_plantillas.columns:
        df_plantillas['Lesion'] = df_plantillas['Lesion'].astype(str).str.strip().str.lower()
        df_plantillas['Lesion'] = df_plantillas['Lesion'].replace({'sí': 'si', 'nan': 'no', '': 'no', 'none': 'no'})
    else:
        df_plantillas['Lesion'] = 'no'

    # 🔥 Mapeamos la lesión al mercado para que salga en TODAS las pestañas de la app
    mapa_lesion = df_plantillas.drop_duplicates('Jugador_Limpio').set_index('Jugador_Limpio')['Lesion']
    df_mercado['Lesion'] = df_mercado['Jugador_Limpio'].map(mapa_lesion).fillna('no')

    # 🩹 El estado exacto de Biwenger para TODOS (ver ESTADOS_BIWENGER). Si un
    # jugador no está en el export, se tira de la marca de siempre.
    try:
        _export_estados = df_export
    except NameError:
        _export_estados = pd.DataFrame()
    if not _export_estados.empty and {'Estado', '_clave'} <= set(_export_estados.columns):
        _mapa_estado = (_export_estados.drop_duplicates('_clave').set_index('_clave')['Estado']
                        .map(lambda v: ESTADOS_BIWENGER.get(str(v or 'ok').strip().lower(), 'ok')))
        df_mercado['Estado Biwenger'] = df_mercado['_clave'].map(_mapa_estado)
        df_plantillas['Estado Biwenger'] = df_plantillas['_clave'].map(_mapa_estado)
    else:
        df_mercado['Estado Biwenger'] = np.nan
        df_plantillas['Estado Biwenger'] = np.nan
    for _df in (df_mercado, df_plantillas):
        _df['Estado Biwenger'] = (_df['Estado Biwenger']
                                  .fillna(_df['Lesion'].map({'si': 'lesionado'})).fillna('ok'))
        _df['Lesion'] = np.where(_df['Estado Biwenger'].isin(NO_DISPONIBLE), 'si', 'no')

    df_plantillas = df_plantillas.drop(columns=['Jugador_Limpio', '_clave'])
    df_mercado = df_mercado.drop(columns=['Jugador_Limpio', '_clave'])
    
    timestamp = datetime.now().strftime("%d/%m/%Y a las %H:%M:%S")

    return {
        'participantes': df_participantes,
        'contabilidad': df_contabilidad,
        'plantillas': df_plantillas,
        'mercado': df_mercado,
        'calendario': df_calendario,
        # ⚽🅰️ Goles y asistencias de cada jugador en cada jornada. La escribe el
        # bot; mientras no exista, la hoja sale vacía y no se pinta nada.
        'eventos': _hoja('Eventos_Jornada'),
        'filas_duplicadas_plantillas': filas_duplicadas_plantillas,
        'filas_duplicadas_mercado': filas_duplicadas_mercado,
        'filas_fantasma_contabilidad': filas_fantasma_contabilidad,
        'filas_incompletas_contabilidad': filas_incompletas_contabilidad,
        'timestamp': timestamp
    }

try:
    db = load_data(_huella_excel(resolver_excel_path()))
except Exception as e:
    st.error("🚨 Error al leer los datos. Comprueba que biwenger.db está en la misma carpeta que la app "
             "(si vienes del Excel, ejecuta una vez migrar_a_sqlite.py).")
    st.caption(f"Detalle técnico: {e}")
    st.stop()


# 👤 ¿QUIÉN ERES?
# La app se ve desde el equipo que elijas al entrar: tu resumen, tus rivales,
# tu presupuesto para pujar, quién mejora tu once... Antes era siempre
# Algeciras. El equipo va en la dirección de la página (?equipo=Nike), así que
# cada uno puede guardarse su enlace en favoritos y entrar directo; sin él, se
# pregunta. Se cambia desde el menú.
EQUIPO_POR_DEFECTO = 'Algeciras'   # solo para el bot, que no tiene pantalla


def _participantes_de_la_liga():
    try:
        return [str(p).strip() for p in db['participantes']['Persona'].dropna()
                if str(p).strip()]
    except Exception:
        return []


def _equipo_valido(nombre, nombres):
    """El nombre tal y como está en la liga, sin distinguir mayúsculas."""
    texto = str(nombre or '').strip().casefold()
    return next((n for n in nombres if n.casefold() == texto), None)


def _elegir_equipo(nombre):
    st.session_state['mi_equipo'] = nombre
    try:
        st.query_params['equipo'] = nombre
    except Exception:
        pass


def elegir_mi_equipo():
    nombres = _participantes_de_la_liga()
    if __name__ == 'bot_diario' or not nombres:
        return _equipo_valido(EQUIPO_POR_DEFECTO, nombres) or (nombres[0] if nombres else EQUIPO_POR_DEFECTO)

    try:
        en_enlace = st.query_params.get('equipo')
    except Exception:
        en_enlace = None
    elegido = (_equipo_valido(en_enlace, nombres)
               or _equipo_valido(st.session_state.get('mi_equipo'), nombres))
    if elegido:
        _elegir_equipo(elegido)
        return elegido

    # Pantalla de bienvenida: no se calcula nada más hasta que elijas. Antes se
    # quita la pantalla de «Cargando la liga»: normalmente desaparece al final
    # de la página, y aquí la ejecución se para antes de llegar.
    _pantalla_carga.empty()
    st.markdown("<div style='text-align:center; margin:8vh 0 2.2rem;'>"
                "<div style='font-family:Fraunces,serif; font-size:2.4rem; font-weight:600;'>"
                "¿Qué equipo eres?</div>"
                "<div style='color:#8b93a7; margin-top:0.4rem;'>La app se verá desde tu equipo: "
                "tu resumen, tus rivales y tus opciones de fichaje.</div></div>",
                unsafe_allow_html=True)
    _, centro, _ = st.columns([1, 3, 1])
    with centro:
        columnas = st.columns(2)
        for i, nombre in enumerate(sorted(nombres, key=str.casefold)):
            columnas[i % 2].button(nombre, key=f"elegir_{i}", use_container_width=True,
                                   on_click=_elegir_equipo, args=(nombre,))
    st.stop()


MI_EQUIPO = elegir_mi_equipo()

# En el mercado, los jugadores de tu equipo salen como «Tuyo» y los demás con
# el nombre de su dueño. Se marca aquí, por sesión: los datos cargados son
# comunes a todos y no saben quién eres.
try:
    db['mercado']['Estado'] = db['mercado']['Estado'].where(
        db['mercado']['Estado'].astype(str).str.strip().str.casefold() != MI_EQUIPO.casefold(),
        'Tuyo')
except Exception:
    pass


# --- 📚 HISTÓRICO MULTI-DÍA ---
HIST_COLS = ['Jugador', 'Equipo', 'Posición', 'Puntos', 'Media Puntos', 'Valor Actual (€)', 'Variación Diaria (€)']
@st.cache_data(show_spinner=False, persist="disk")
def cargar_historico_completo(huella=None):
    """Una fila por jugador y día: Fecha, Fecha_Texto y HIST_COLS.

    En el Excel era un bloque de columnas por día; en la base es la tabla
    `historico`, ya en formato largo."""
    if not resolver_excel_path():
        return pd.DataFrame()
    try:
        df = almacen.historico_leer()
    except Exception:
        return pd.DataFrame()
    if not df.empty:
        df['Valor Actual (€)'] = pd.to_numeric(df['Valor Actual (€)'], errors='coerce')
        df['Puntos'] = pd.to_numeric(df['Puntos'], errors='coerce')
        df['Media Puntos'] = pd.to_numeric(df['Media Puntos'], errors='coerce')
        df = df.sort_values('Fecha', kind='stable')
    return df


# ⏰ EL DÍA DE MERCADO NO EMPIEZA A MEDIANOCHE.
# Biwenger actualiza precios, puntos y valores a las 7:00. Hasta esa hora, lo
# que devuelve el servidor sigue siendo el mercado del día anterior. Importar a
# las 2 de la madrugada creaba un bloque del día nuevo con los datos del día
# viejo: dos bloques idénticos con fechas distintas, variación diaria en cero y
# el Histórico contando un día de más.
HORA_CAMBIO_MERCADO = 7


def fecha_de_mercado(ahora=None):
    """A qué día pertenecen los datos que hay ahora mismo en el servidor."""
    ahora = ahora or datetime.now()
    if ahora.hour < HORA_CAMBIO_MERCADO:
        return ahora - timedelta(days=1)
    return ahora


HOJA_ESTADOS = 'Estados'


def _anotar_estados_del_dia(wb, fecha_txt):
    """Apunta en la hoja Estados a los jugadores que ese día no están «ok».

    Es lo que permitirá medir, dentro de unas jornadas, cuántas veces juega de
    verdad un jugador en duda, y ajustar su probabilidad con ese dato en vez
    de ponerla a ojo. Solo se guardan los que no están bien (unos setenta al
    día), y no se repite si ese día ya está apuntado."""
    if 'Biwenger_Export' not in wb.sheetnames:
        return 0
    ws_exp = wb['Biwenger_Export']
    cabecera = [str(c.value or '').strip() for c in ws_exp[1]]
    if not {'Jugador', 'Equipo', 'Estado'} <= set(cabecera):
        return 0
    i_jug, i_equ, i_est = (cabecera.index('Jugador'), cabecera.index('Equipo'), cabecera.index('Estado'))
    ws = wb[HOJA_ESTADOS] if HOJA_ESTADOS in wb.sheetnames else wb.create_sheet(HOJA_ESTADOS)
    if ws.cell(1, 1).value != 'Fecha':
        for col, rotulo in enumerate(('Fecha', 'Jugador', 'Equipo', 'Estado'), start=1):
            ws.cell(1, col, rotulo)

    # La fecha va como FECHA de Excel, no como texto: para cruzar luego esta hoja
    # con el Histórico y el calendario hace falta poder compararla. Las filas
    # que se escribieron como texto ("22/09/2026") se convierten aquí mismo.
    dia = datetime.strptime(fecha_txt, '%d/%m/%Y')
    ya_esta = False
    for f in range(2, ws.max_row + 1):
        celda = ws.cell(f, 1)
        valor = celda.value
        if isinstance(valor, str):
            try:
                valor = datetime.strptime(valor.strip(), '%d/%m/%Y')
            except ValueError:
                continue
            celda.value = valor
            celda.number_format = 'DD/MM/YYYY'
        if isinstance(valor, datetime) and valor.date() == dia.date():
            ya_esta = True
    if ya_esta:
        return 0
    apuntados = 0
    for fila in ws_exp.iter_rows(min_row=2, values_only=True):
        estado = str(fila[i_est] or 'ok').strip().lower()
        if fila[i_jug] and estado not in ('ok', '', 'none'):
            ws.append([dia, fila[i_jug], fila[i_equ], ESTADOS_BIWENGER.get(estado, estado)])
            ws.cell(ws.max_row, 1).number_format = 'DD/MM/YYYY'
            apuntados += 1
    return apuntados


def importar_dia_a_historico(df_mercado_actual, fecha=None):
    file_path = resolver_excel_path()
    if not file_path:
        return False, "No se encuentra la base de datos."

    fecha = fecha or fecha_de_mercado()
    fecha_txt = fecha.strftime('%d/%m/%Y')

    df_ok = df_mercado_actual.dropna(subset=['Jugador'])
    filas = [{campo: fila.get(campo) for campo in HIST_COLS} for _, fila in df_ok.iterrows()]
    if not almacen.historico_anadir_dia(fecha, filas, ruta=file_path):
        return False, (f"Ya existe un bloque para el {fecha_txt} en Histórico. "
                       f"(Biwenger cambia el mercado a las {HORA_CAMBIO_MERCADO}:00; "
                       "antes de esa hora los datos siguen siendo los del día anterior.)")

    try:
        wb = almacen.abrir(file_path)
        if _anotar_estados_del_dia(wb, fecha_txt):
            guardar_excel(wb, file_path)
    except Exception:
        pass      # apuntar estados nunca debe impedir guardar el día
    return True, f"✅ Bloque del {fecha_txt} añadido."


# --- 🔒 CANDADO DE LOS 10 DÍAS ---
# En esta liga no se puede vender a un jugador hasta que pasan 10 días desde que
# lo fichas. El contador arranca el día en que aparece en tu plantilla: fichado
# el 1, vendible el 11.
#
# El Excel no guardaba la fecha de fichaje en ninguna parte (Contabilidad no
# tenía fechas, y el Histórico guarda datos de mercado pero no de quién es cada
# jugador), así que hay dos fuentes y manda la primera:
#   1. Columna 'Fecha Fichaje' de Contabilidad — exacta, la rellenas al registrar
#      la compra, y sirve también para las compras ya hechas.
#   2. Hoja 'Fichajes' — la mantiene la app sola al importar: apunta el día en que
#      ve por primera vez a un jugador en una plantilla. No sabe nada de antes de
#      instalarse (por eso los jugadores de partida van marcados como
#      'preexistente', sin fecha y sin candado) y su precisión depende de que
#      importes a diario.
DIAS_BLOQUEO_VENTA = 10
HOJA_FICHAJES = 'Fichajes'


def _a_fecha(valor):
    """Convierte a fecha lo que venga del Excel, o None si no hay nada usable."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    try:
        fecha = pd.to_datetime(valor, dayfirst=True, errors='coerce')
    except (TypeError, ValueError):
        return None
    return None if pd.isna(fecha) else fecha.date()


def construir_fechas_fichaje():
    """{(jugador, participante): fecha de alta} con las dos fuentes combinadas."""
    fechas = {}

    # 2) Respaldo automático primero, para que la fuente exacta lo pise después.
    try:
        registro = almacen.leer_hoja(HOJA_FICHAJES)
        for _, fila in registro.iterrows():
            jugador, participante = fila.get('Jugador'), fila.get('Participante')
            fecha = _a_fecha(fila.get('Fecha Alta'))
            if pd.notna(jugador) and pd.notna(participante) and fecha:
                fechas[(str(jugador).strip(), str(participante).strip())] = fecha
    except Exception:
        pass

    # 1) Fecha escrita a mano en Contabilidad: la que manda.
    contabilidad = db.get('contabilidad')
    if contabilidad is not None and 'Fecha Fichaje' in contabilidad.columns:
        compras = contabilidad[contabilidad['Tipo de Operación'] == 'Compra']
        for _, fila in compras.iterrows():
            jugador, participante = fila.get('Jugador'), fila.get('Persona')
            fecha = _a_fecha(fila.get('Fecha Fichaje'))
            if pd.notna(jugador) and pd.notna(participante) and fecha:
                clave = (str(jugador).strip(), str(participante).strip())
                # Si lo fichó, vendió y volvió a fichar, vale la compra más reciente.
                if clave not in fechas or fechas[clave] < fecha or fechas.get(clave) is None:
                    fechas[clave] = fecha
    return fechas


@st.cache_data(show_spinner=False)
def _fechas_fichaje_de(huella=None):
    # ⚡ Leía la hoja del registro de fichajes DEL DISCO en cada clic (abrir el
    # Excel entero para una hoja: 0,2 s aquí, más de un segundo en un portátil
    # normal). Solo cambia cuando cambia el Excel.
    return construir_fechas_fichaje()


FECHAS_FICHAJE = _fechas_fichaje_de(_huella_excel(resolver_excel_path()))


def dias_para_desbloquear(jugador, participante, hoy=None):
    """Días que faltan para poder vender, o None si ya es vendible o no se sabe."""
    fecha = FECHAS_FICHAJE.get((str(jugador).strip(), str(participante).strip()))
    if not fecha:
        return None
    hoy = hoy or datetime.now().date()
    restantes = DIAS_BLOQUEO_VENTA - (hoy - fecha).days
    return restantes if restantes > 0 else None


# ⏱️ EL PLAZO REAL PARA VENDER ES EL INICIO DE LA JORNADA, NO HOY.
# En Biwenger se puede estar en negativo; lo que no se puede es EMPEZAR la
# jornada así (no puntúas). Un jugador con candado que se libera antes de que
# empiece la jornada sí cuenta para cubrir la deuda: basta con venderlo ese día.
# El candado se libera a la hora del mercado (las 7:00) del día 10.


def fecha_desbloqueo(jugador, participante):
    """Cuándo se le quita el candado (datetime), o None si ya no lo tiene."""
    dias = dias_para_desbloquear(jugador, participante)
    if not dias:
        return None
    dia = datetime.now().date() + timedelta(days=int(dias))
    return datetime(dia.year, dia.month, dia.day, HORA_CAMBIO_MERCADO)


@st.cache_data(show_spinner=False)
def inicio_proxima_jornada(huella=None):
    """(datetime, número de jornada) del primer partido de la jornada que viene,
    con su hora si Biwenger ya la ha dado. Sin hora se toma el principio del
    día, que es lo prudente. (None, None) si no hay partidos con fecha."""
    cal = df_cal_global
    if cal is None or cal.empty:
        return None, None
    ahora = datetime.now()
    pendientes = cal[(cal['Estado'] == 'Pendiente') & cal['Fecha'].notna()].copy()
    if pendientes.empty:
        return None, None

    def momento(fila):
        dia = pd.Timestamp(fila['Fecha']).to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)
        hora = fila.get('Hora')
        if isinstance(hora, str) and re.fullmatch(r'\d{1,2}:\d{2}', hora):
            h, m = hora.split(':')
            dia = dia.replace(hour=int(h), minute=int(m))
        return dia

    pendientes['_momento'] = [momento(f) for _, f in pendientes.iterrows()]
    futuros = pendientes[pendientes['_momento'] >= ahora.replace(hour=0, minute=0, second=0, microsecond=0)]
    if futuros.empty:
        return None, None
    jornada = int(futuros.sort_values('_momento').iloc[0]['Jornada'])
    return futuros[futuros['Jornada'] == jornada]['_momento'].min(), jornada


def vendible_antes_de_jornada(jugador, participante):
    """¿Se le puede vender antes de que empiece la próxima jornada?"""
    libre = fecha_desbloqueo(jugador, participante)
    if libre is None:
        return True
    inicio, _ = inicio_proxima_jornada(_huella_excel(resolver_excel_path()))
    return inicio is not None and libre <= inicio


def sincronizar_plantillas(aplicar=True):
    """Pone la hoja Plantillas al día a partir de Contabilidad y del export.

    Hasta ahora, cada fichaje había que escribirlo a mano: el jugador, su club,
    el mánager que lo compra, si está lesionado, sus goles y sus asistencias. Y
    cada venta, borrarla. Contabilidad ya sabe todo eso.

    DE QUIÉN ES CADA JUGADOR: manda su ÚLTIMO movimiento. Si es una compra, es
    del comprador; si es una venta, de nadie. Se recalcula entero cada vez en
    vez de ir aplicando lo del día, así el resultado no depende de que no se
    haya perdido ninguna ejecución.

    SE BUSCA POR NOMBRE, NO POR NOMBRE+EQUIPO. El club que guarda Contabilidad
    es el del día de la compra, y los jugadores se traspasan: Pablo García se
    fichó siendo del Real Madrid y hoy juega en el Racing. Cruzando por
    jugador+equipo, su ficha no casaba y se daba de alta otra vez, duplicado.
    El club se saca del export, que es el de hoy. Solo se exige que coincida el
    equipo cuando hay homónimos de verdad (dos Moussa Diarra, dos Héctor Fort).

    QUIEN NUNCA APARECE EN CONTABILIDAD no se toca: son los del sorteo inicial.

    Las filas no se insertan ni se borran, solo se limpia o se rellena su
    contenido: las fórmulas de valor, posición y media ya están puestas en las
    1.060 filas de la tabla, y moverlas es justo lo que en su día descolocó las
    de Posición y Media Puntos.
    """
    ruta = resolver_excel_path()
    if not ruta:
        return False, "No se encuentra la base de datos.", []
    wb = almacen.abrir(ruta)
    if 'Plantillas' not in wb.sheetnames or 'Contabilidad' not in wb.sheetnames:
        return False, "Faltan las hojas Plantillas o Contabilidad.", []

    ws_plant, ws_conta = wb['Plantillas'], wb['Contabilidad']

    # 1) El export manda en club, estado y estadísticas, y dice qué nombres se
    #    repiten en jugadores distintos.
    ficha, club_hoy, ambiguos = {}, {}, set()
    if 'Biwenger_Export' in wb.sheetnames:
        ws_exp = wb['Biwenger_Export']
        cols = _columnas_hoja(ws_exp)
        for fila in range(2, ws_exp.max_row + 1):
            nombre = ws_exp.cell(fila, 2).value
            if not nombre:
                continue
            nombre = str(nombre).strip()
            equipo = str(ws_exp.cell(fila, 1).value or '').strip()
            if nombre in club_hoy and club_hoy[nombre] != equipo:
                ambiguos.add(nombre)
            club_hoy[nombre] = equipo

            def _dato(titulo):
                col = cols.get(titulo)
                return ws_exp.cell(fila, col).value if col else None

            estado = str(_dato('Estado') or 'ok').strip().lower()
            ficha[(nombre, equipo)] = {
                'equipo': equipo,
                # Solo lo que impide jugar: una duda no es una baja.
                'lesion': 'si' if estado in ('injured', 'sanctioned', 'discarded') else 'no',
                'goles': _dato('Goles'),
                'asistencias': _dato('Asistencias'),
                'posicion': _dato('Posición'),
            }

    def _clave(nombre, equipo):
        """Con qué se identifica a este jugador: el nombre basta salvo homónimos."""
        nombre = str(nombre).strip()
        return (nombre, str(equipo or '').strip()) if nombre in ambiguos else (nombre, '')

    # 2) El último movimiento de cada jugador.
    ultimo = {}
    for fila in range(2, ws_conta.max_row + 1):
        persona = ws_conta.cell(fila, 2).value
        tipo = str(ws_conta.cell(fila, 3).value or '').strip()
        jugador = ws_conta.cell(fila, 4).value
        if not persona or not jugador or tipo not in ('Compra', 'Venta'):
            continue
        clave = _clave(jugador, ws_conta.cell(fila, 5).value)
        fecha = ws_conta.cell(fila, 1).value
        orden = (fecha if hasattr(fecha, 'year') else datetime(1900, 1, 1), fila)
        previo = ultimo.get(clave)
        # A igualdad de fecha manda la compra: en un traspaso entre mánagers se
        # apuntan la venta y la compra el mismo día, y el dueño es quien compra.
        if previo is None or orden > previo[0] or (orden == previo[0] and tipo == 'Compra'):
            ultimo[clave] = (orden, tipo, str(persona).strip())

    duenos = {c: p for c, (_, t, p) in ultimo.items() if t == 'Compra'}
    vendidos = {c for c, (_, t, _) in ultimo.items() if t == 'Venta'}

    # 3) Lo que hay hoy en Plantillas, indexado igual.
    filas_de, libres = {}, []
    for fila in range(2, ws_plant.max_row + 1):
        jugador = ws_plant.cell(fila, 1).value
        if not jugador:
            libres.append(fila)
            continue
        filas_de[_clave(jugador, ws_plant.cell(fila, 2).value)] = fila

    altas, bajas, cambios, avisos = [], [], [], []

    # 4) Vendidos: fuera.
    for clave in vendidos:
        fila = filas_de.pop(clave, None)
        if fila is None:
            continue
        for col in (1, 2, 3, 9, 10, 11):
            ws_plant.cell(fila, col).value = None
        bajas.append(clave[0])
        libres.append(fila)

    # 5) Comprados: dentro, o cambio de mánager.
    for clave, persona in sorted(duenos.items()):
        fila = filas_de.get(clave)
        if fila is None:
            if not libres:
                avisos.append(f"No caben más fichas en Plantillas: {clave[0]} se queda fuera")
                continue
            fila = min(libres)
            libres.remove(fila)
            ws_plant.cell(fila, 1).value = clave[0]
            ws_plant.cell(fila, 2).value = club_hoy.get(clave[0], clave[1])
            filas_de[clave] = fila
            altas.append(f"{clave[0]} → {persona}")
        elif str(ws_plant.cell(fila, 3).value or '').strip() != persona:
            cambios.append(f"{clave[0]}: {ws_plant.cell(fila, 3).value} → {persona}")
        ws_plant.cell(fila, 3).value = persona

    # 6) Club, estado, goles y asistencias de TODAS las fichas.
    al_dia, traspasos = 0, []
    for clave, fila in filas_de.items():
        nombre = str(ws_plant.cell(fila, 1).value or '').strip()
        equipo = str(ws_plant.cell(fila, 2).value or '').strip()
        datos = ficha.get((nombre, equipo)) or ficha.get((nombre, club_hoy.get(nombre, '')))
        if not datos:
            continue
        if datos['equipo'] and datos['equipo'] != equipo:
            # Si el club no se corrige, las fórmulas de valor buscan un par
            # jugador+equipo que ya no existe y la ficha se queda a 0 €.
            ws_plant.cell(fila, 2).value = datos['equipo']
            traspasos.append(f"{nombre}: ahora juega en {datos['equipo']}")
        for col, valor in ((9, datos['goles']), (10, datos['asistencias'])):
            if valor is not None:
                ws_plant.cell(fila, col).value = valor
        ws_plant.cell(fila, 11).value = datos['lesion']
        # ⚠️ La posición NO se escribe aquí: en Plantillas es una FÓRMULA que la
        # busca en Mercado_Global, y ese ya la toma de Biwenger. Escribirla
        # machacaría la fórmula. Lo único que se desfasa es la hoja manual
        # Multiposicion, y de eso se avisa abajo.
        al_dia += 1

    # 🧭 Filas de Multiposicion que Biwenger ha dejado desfasadas: la posición
    # que da hoy no está entre las que tienes apuntadas. La app ya enseña la
    # buena; esto es para que corrijas la hoja cuando quieras.
    if 'Multiposicion' in wb.sheetnames:
        pos_hoy = {n: d.get('posicion') for (n, _), d in ficha.items() if d.get('posicion')}
        for nombre_mp, manual in wb['Multiposicion'].iter_rows(min_row=2, max_col=2, values_only=True):
            if not nombre_mp or not manual:
                continue
            api = pos_hoy.get(str(nombre_mp).strip())
            if api and posicion_real(manual, api) != str(manual).strip():
                avisos.append(f"Multiposicion desfasada: {nombre_mp} figura como «{manual}» "
                              f"y Biwenger lo tiene de {api}")

    # aplicar=False deja el Excel intacto y solo cuenta lo que haría.
    if aplicar:
        guardar_excel(wb, ruta)

    if not (altas or bajas or cambios):
        return True, (f"Plantillas ya estaba al día ({len(filas_de)} fichas; club, "
                      f"estado y estadísticas refrescados en {al_dia})."), traspasos + avisos

    partes = []
    if altas:
        partes.append(f"{len(altas)} alta/s")
    if bajas:
        partes.append(f"{len(bajas)} baja/s")
    if cambios:
        partes.append(f"{len(cambios)} cambio/s de mánager")
    encabezado = "Plantillas al día: " if aplicar else "Plantillas, lo que haría: "
    detalle = altas[:8] + [f"baja: {n}" for n in bajas[:8]] + cambios[:8]
    return True, (encabezado + ", ".join(partes) +
                  f" ({len(filas_de)} fichas en total)."), detalle + traspasos + avisos




def actualizar_registro_fichajes():
    """Apunta en la hoja 'Fichajes' a los jugadores que aparecen hoy por primera
    vez en una plantilla, y borra los que ya no están (si vuelven, cuentan como
    fichaje nuevo). Se llama al importar el día."""
    ruta = resolver_excel_path()
    if not ruta:
        return 0
    try:
        wb = almacen.abrir(ruta)
    except Exception:
        return 0

    nueva = HOJA_FICHAJES not in wb.sheetnames
    ws = wb.create_sheet(HOJA_FICHAJES) if nueva else wb[HOJA_FICHAJES]
    if nueva:
        for i, titulo in enumerate(['Jugador', 'Participante', 'Fecha Alta', 'Origen'], start=1):
            ws.cell(1, i, titulo)
        ws.sheet_state = 'hidden'

    guardados = {}
    for fila in range(2, ws.max_row + 1):
        jugador, participante = ws.cell(fila, 1).value, ws.cell(fila, 2).value
        if jugador and participante:
            guardados[(str(jugador).strip(), str(participante).strip())] = (
                ws.cell(fila, 3).value, ws.cell(fila, 4).value
            )

    actuales = set()
    plantillas = db.get('plantillas')
    if plantillas is not None:
        for _, fila in plantillas.dropna(subset=['Jugador', 'Participante']).iterrows():
            actuales.add((str(fila['Jugador']).strip(), str(fila['Participante']).strip()))

    hoy = datetime.now().date()
    nuevos = 0
    # La hoja se reescribe entera: es corta (una fila por jugador con dueño) y así
    # desaparecen solos los que se han vendido.
    ws.delete_rows(2, max(ws.max_row, 2))
    destino = 2
    for clave in sorted(actuales):
        if clave in guardados:
            fecha_alta, origen = guardados[clave]
        else:
            fecha_alta, origen = hoy, 'detectado'
            nuevos += 1
        ws.cell(destino, 1, clave[0])
        ws.cell(destino, 2, clave[1])
        ws.cell(destino, 3, fecha_alta)
        ws.cell(destino, 3).number_format = 'DD/MM/YYYY'
        ws.cell(destino, 4, origen)
        destino += 1

    guardar_excel(wb, ruta)
    return nuevos


def diagnostico_localia(jugadores, es_casa, min_muestra=2, min_jugadores=4):
    """¿Se desenvuelve bien este once jugando en casa (o fuera)?

    Compara, jugador a jugador, su media en esa condición contra su media
    general, y promedia esas proporciones ponderando por los partidos que cada
    uno ha disputado ahí (para que uno con un solo partido no marque el tono).
    Devuelve (etiqueta, desviación en %, jugadores con muestra) o None si
    todavía no hay datos suficientes.

    No mira el próximo rival: es el carácter del once, no la previsión de la
    jornada."""
    peso_total, suma, con_muestra = 0.0, 0.0, 0
    for p in jugadores:
        media_general = _a_float(p.get('Media Puntos'), None)
        media_split = _a_float(p.get('Media Puntos Casa' if es_casa else 'Media Puntos Fuera'), None)
        if not media_general or not media_split:
            continue
        pj_split = _a_float(p.get('PJ Casa' if es_casa else 'PJ Fuera'), None)
        if pj_split is None:
            pj = _a_float(p.get('PJ'), 0.0) or 0.0
            ratio_eq = get_ratio_casa_equipo(p.get('Equipo'))
            pj_split = pj * (ratio_eq if es_casa else (1 - ratio_eq))
        if pj_split < min_muestra:
            continue
        con_muestra += 1
        peso_total += pj_split
        suma += pj_split * (media_split / media_general)

    if con_muestra < min_jugadores or peso_total <= 0:
        return None

    ratio = suma / peso_total
    desviacion = (ratio - 1) * 100
    if abs(desviacion) < 0.5:
        desviacion = 0.0        # evita que salga un feo "-0%"
    if ratio >= 1.08:
        etiqueta = 'bien'
    elif ratio <= 0.93:
        etiqueta = 'mal'
    else:
        etiqueta = 'normal'
    return etiqueta, desviacion, con_muestra


# --- 🏠✈️ PUNTOS EN CASA Y FUERA, COPIADOS DE BIWENGER ---
# Las columnas 'Casa' y 'Fuera' del export son el NÚMERO DE PARTIDOS en cada
# condición; los puntos de cada una vienen aparte, en 'Pts Casa' y 'Pts Fuera',
# que el bot baja de la API (pointsHome/pointsAway) junto con el id numérico.
#
# Hasta septiembre esos puntos se deducían por diferencias entre importaciones
# (si subía el contador de casa y no el de fuera, lo ganado era en casa), con
# parches para los repartos ambiguos, las rectificaciones de Biwenger, los
# traspasos y los renombrados. Retirado el 24/09/2026: con la vía exacta, las 525
# fichas vivas cuadraban al 100% con la API y ninguna usaba ya el método viejo.
# Los acumulados siguen viviendo en PJ_Split porque las fórmulas del libro
# (Mercado_Global F/G) leen de ahí.

PJ_SPLIT_HOJA = 'PJ_Split'
# La columna 'ID' (la 11) es el identificador numérico de Biwenger. Va la última
# a propósito: las diez primeras son las de siempre y todas las fórmulas del
# libro que apuntan a PJ_Split!$E:$E o $F:$F siguen valiendo.
PJ_SPLIT_COLS = ['Jugador', 'Equipo', 'PJ C', 'PJ F', 'Pts C', 'Pts F',
                 'Puntos registrados', 'Casa registrada', 'Fuera registrada', 'Nota', 'ID']
COL_ID_SPLIT = 11

# Columnas que el bot añade al export cuando baja los datos de la API. Sin ellas
# no hay reparto que copiar.
COLS_API_EXPORT = ('ID', 'Pts Casa', 'Pts Fuera')


def _columnas_hoja(ws):
    """Diccionario 'nombre de cabecera' -> número de columna."""
    return {str(ws.cell(1, c).value).strip(): c
            for c in range(1, ws.max_column + 1) if ws.cell(1, c).value}


def _entero(valor, defecto=0):
    try:
        return int(float(str(valor).replace(',', '.')))
    except (TypeError, ValueError):
        return defecto


def _sin_tildes(texto):
    limpio = unicodedata.normalize('NFKD', str(texto))
    return ''.join(c for c in limpio if not unicodedata.combining(c)).lower().strip()


def detectar_renombrados(wb):
    """{nombre viejo: nombre nuevo} cuando Biwenger rebautiza a un jugador.

    Biwenger reajusta nombres cada pocas semanas, en las dos direcciones
    ("Yassir Zabiri" → "Zabiri", "Canales" → "Sergio Canales"). Como los cruces
    del Excel van por nombre, sin detectarlo el jugador se partía en dos.

    Antes se adivinaba por parecido del nombre dentro del mismo equipo. Ahora se
    sabe: PJ_Split guarda el id de Biwenger de cada ficha, y si el export trae
    ese mismo id con otro nombre, es un renombrado. Sin falsos positivos por
    homónimos ni fichajes.

    Una salvaguarda: si el nombre viejo lo sigue usando OTRO jugador en el
    export, no se cambia en todo el libro (se llevaría por delante las filas del
    otro). Ese caso sale en `conflictos` para avisar.
    """
    if 'Biwenger_Export' not in wb.sheetnames or PJ_SPLIT_HOJA not in wb.sheetnames:
        return {}
    ws_exp, ws_split = wb['Biwenger_Export'], wb[PJ_SPLIT_HOJA]
    col_id = _columnas_hoja(ws_exp).get('ID')
    if not col_id:
        return {}

    nombre_por_id, nombres_export = {}, set()
    for fila in range(2, ws_exp.max_row + 1):
        nombre = ws_exp.cell(fila, 2).value
        if not nombre:
            continue
        nombre = str(nombre).strip()
        nombres_export.add(nombre)
        id_jug = _entero(ws_exp.cell(fila, col_id).value, 0)
        if id_jug:
            nombre_por_id[id_jug] = nombre

    renombrados = {}
    detectar_renombrados.conflictos = []
    for fila in range(2, ws_split.max_row + 1):
        viejo = ws_split.cell(fila, 1).value
        id_jug = _entero(ws_split.cell(fila, COL_ID_SPLIT).value, 0)
        if not viejo or not id_jug or id_jug not in nombre_por_id:
            continue
        viejo, nuevo = str(viejo).strip(), nombre_por_id[id_jug]
        if viejo == nuevo:
            continue
        if viejo in nombres_export:
            detectar_renombrados.conflictos.append((viejo, nuevo))
            continue
        renombrados[viejo] = nuevo
    return renombrados


detectar_renombrados.conflictos = []


def aplicar_renombrados(wb, renombrados):
    """Cambia el nombre viejo por el nuevo en TODO el libro.

    Todo el libro y no solo la hoja de reparto: la primera vez que se arregló a
    mano se olvidaron el Histórico (que partía las gráficas en dos) y
    Biwenger_Ayer (que dejaba la variación diaria a cero)."""
    if not renombrados:
        return 0
    tocadas = 0
    for hoja in wb.worksheets:
        if hoja.title == 'Biwenger_Export':
            continue          # el export es la fuente: ya viene con el nombre nuevo
        for fila in hoja.iter_rows():
            for celda in fila:
                if isinstance(celda.value, str) and celda.value.strip() in renombrados:
                    celda.value = renombrados[celda.value.strip()]
                    tocadas += 1
    return tocadas


def actualizar_split_casa_fuera():
    """Copia a PJ_Split el reparto exacto de casa y fuera que da Biwenger.
    Devuelve (ok, mensaje, lista_de_avisos)."""
    file_path = resolver_excel_path()
    if not file_path:
        return False, "No se encuentra la base de datos.", []

    wb = almacen.abrir(file_path)
    if 'Biwenger_Export' not in wb.sheetnames:
        return False, "No existe la hoja 'Biwenger_Export'.", []
    ws_exp = wb['Biwenger_Export']
    cols_exp = _columnas_hoja(ws_exp)
    if not all(c in cols_exp for c in COLS_API_EXPORT):
        return False, ("El export no trae el reparto de Biwenger (columnas ID, Pts Casa y "
                       "Pts Fuera). Pulsa el botón de actualizar para que lo baje el bot."), []
    col_id = cols_exp['ID']
    col_pc, col_pf = cols_exp['Pts Casa'], cols_exp['Pts Fuera']

    # 🔤 Primero, los renombrados, para que el resto del libro (Plantillas,
    # Contabilidad, Histórico...) siga cruzando por nombre con el export.
    renombrados = detectar_renombrados(wb)
    avisos = []
    if renombrados:
        celdas = aplicar_renombrados(wb, renombrados)
        for viejo, nuevo in sorted(renombrados.items()):
            avisos.append(f"Biwenger ha renombrado a {viejo}: ahora es {nuevo}; "
                          "se conserva todo su historial")
        avisos.append(f"({celdas} celdas actualizadas en la base de datos)")
    for viejo, nuevo in detectar_renombrados.conflictos:
        avisos.append(f"Biwenger ha renombrado a {viejo} como {nuevo}, pero otro jugador se "
                      f"sigue llamando {viejo}: revisa a mano sus filas")

    ws = wb[PJ_SPLIT_HOJA] if PJ_SPLIT_HOJA in wb.sheetnames else wb.create_sheet(PJ_SPLIT_HOJA)
    if ws.cell(1, 5).value != 'Pts C':
        # Hoja vacía o de un formato muy antiguo: se rehace la cabecera.
        ws.delete_rows(1, max(ws.max_row, 1))
        for i, titulo in enumerate(PJ_SPLIT_COLS, start=1):
            ws.cell(1, i, titulo)
        ws.sheet_state = 'hidden'
    if ws.cell(1, COL_ID_SPLIT).value != 'ID':
        ws.cell(1, COL_ID_SPLIT, 'ID')

    registro, por_id = {}, {}
    for fila in range(2, ws.max_row + 1):
        jugador = ws.cell(fila, 1).value
        if not jugador:
            continue
        equipo = str(ws.cell(fila, 2).value or '').strip()
        ficha = {'fila': fila, 'equipo': equipo,
                 'pts_casa': _entero(ws.cell(fila, 5).value),
                 'pts_fuera': _entero(ws.cell(fila, 6).value)}
        registro[(str(jugador).strip(), equipo)] = ficha
        id_ficha = _entero(ws.cell(fila, COL_ID_SPLIT).value, 0)
        if id_ficha:
            por_id[id_ficha] = ficha

    actualizados, nuevos, copiados, sin_datos = 0, 0, 0, []
    siguiente_fila = max([r['fila'] for r in registro.values()], default=1) + 1

    for fila in range(2, ws_exp.max_row + 1):
        jugador = ws_exp.cell(fila, 2).value
        if not jugador:
            continue
        jugador = str(jugador).strip()
        equipo = str(ws_exp.cell(fila, 1).value or '').strip()
        puntos = _entero(ws_exp.cell(fila, 4).value)
        pj_casa = _entero(ws_exp.cell(fila, 7).value)     # columna 'Casa' = partidos
        pj_fuera = _entero(ws_exp.cell(fila, 8).value)    # columna 'Fuera' = partidos
        id_jug = _entero(ws_exp.cell(fila, col_id).value, 0)
        celda_pc, celda_pf = ws_exp.cell(fila, col_pc).value, ws_exp.cell(fila, col_pf).value
        # ⚠️ Vacío y cero no son lo mismo, y un negativo es válido (Aarón Martín
        # lleva -6): solo se descarta la fila si falta el dato.
        if not id_jug or celda_pc is None or celda_pf is None:
            sin_datos.append(jugador)
            continue
        pts_casa, pts_fuera = _entero(celda_pc, 0), _entero(celda_pf, 0)

        ficha = por_id.get(id_jug) or registro.get((jugador, equipo))
        if ficha is None:
            f = siguiente_fila
            siguiente_fila += 1
            ficha = {'fila': f, 'equipo': equipo, 'pts_casa': 0, 'pts_fuera': 0}
            nuevos += 1
        else:
            f = ficha['fila']
            if ficha['equipo'] and ficha['equipo'] != equipo:
                avisos.append(f"{jugador}: ha cambiado de {ficha['equipo']} a {equipo}")
            if (ficha['pts_casa'], ficha['pts_fuera']) != (pts_casa, pts_fuera):
                actualizados += 1
        for i, v in enumerate([jugador, equipo, pj_casa, pj_fuera, pts_casa, pts_fuera,
                               puntos, pj_casa, pj_fuera, "exacto (API)", id_jug], start=1):
            ws.cell(f, i, v)
        ficha.update({'equipo': equipo, 'pts_casa': pts_casa, 'pts_fuera': pts_fuera})
        registro[(jugador, equipo)] = ficha
        por_id[id_jug] = ficha
        copiados += 1

    if sin_datos:
        muestra = ", ".join(sin_datos[:5]) + ("…" if len(sin_datos) > 5 else "")
        avisos.append(f"{len(sin_datos)} jugador/es sin id o sin reparto en el export, no se "
                      f"tocan: {muestra}")

    guardar_excel(wb, file_path)

    partes = [f"{copiados} jugador/es copiados exactos de Biwenger"]
    if actualizados:
        partes.append(f"{actualizados} con puntos nuevos")
    if nuevos:
        partes.append(f"{nuevos} ficha/s nuevas")
    if renombrados:
        partes.append(f"{len(renombrados)} renombrado/s, historial conservado")
    return True, "Desglose casa/fuera al día: " + ", ".join(partes) + ".", avisos


def _clave_alfabetica(texto):
    """Ordena como ordenaría una persona: la Á junto a la A.

    Ordenar por el código del carácter manda todos los acentuados detrás de la
    Z, así que en un desplegable de 521 nombres "Álvaro García" acababa
    enterrado al final en vez de entre "Alvarito" y "Amath". Lo mismo le pasaba
    a Rüdiger, Ñíguez y a cualquiera con tilde o diéresis."""
    limpio = unicodedata.normalize('NFKD', str(texto))
    return ''.join(c for c in limpio if not unicodedata.combining(c)).lower()


def revertir_registro_fichajes(fecha=None):
    """Borra de la hoja 'Fichajes' las altas detectadas automáticamente en una
    fecha. Va de la mano de "Deshacer último": sin esto, importar y deshacer
    dejaba puesta la fecha de alta de los jugadores nuevos, con su candado de
    10 días corriendo desde ese día."""
    ruta = resolver_excel_path()
    if not ruta:
        return 0
    fecha = fecha or datetime.now().date()
    try:
        wb = almacen.abrir(ruta)
        if HOJA_FICHAJES not in wb.sheetnames:
            return 0
        ws = wb[HOJA_FICHAJES]
        a_borrar = []
        for fila in range(2, ws.max_row + 1):
            alta = _a_fecha(ws.cell(fila, 3).value)
            origen = str(ws.cell(fila, 4).value or '').strip().lower()
            if origen == 'detectado' and alta == fecha:
                a_borrar.append(fila)
        for fila in reversed(a_borrar):
            ws.delete_rows(fila, 1)
        if a_borrar:
            guardar_excel(wb, ruta)
        return len(a_borrar)
    except Exception:
        return 0


def deshacer_ultima_importacion():
    file_path = resolver_excel_path()
    if not file_path:
        return False, "No se encuentra la base de datos."
    try:
        almacen.copia_de_seguridad(file_path)
    except Exception:
        pass
    ultima = almacen.historico_borrar_ultimo(file_path)
    if ultima is None:
        return False, "No hay ningún bloque que deshacer."
    return True, f"↩️ Bloque del {pd.Timestamp(ultima):%d/%m/%Y} eliminado."


# --- 📅 CALENDARIO Y CLASIFICACIÓN ---
def _hora_calendario(valor):
    """'21:00' o None. Acepta texto, hora de Excel o fecha con hora."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    if hasattr(valor, 'strftime'):
        texto = valor.strftime('%H:%M')
    else:
        texto = str(valor).strip()[:5]
    return texto if re.fullmatch(r'\d{1,2}:\d{2}', texto) and texto not in ('0:00', '00:00') else None


def preparar_calendario(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=['Jornada', 'Fecha', 'Local', 'Gol Local', 'Gol Visitante', 'Visitante'])

    out = df.copy()
    if 'J' in out.columns:
        out['Jornada'] = pd.to_numeric(out['J'], errors='coerce').ffill()
    else:
        out['Jornada'] = np.nan
    if 'Fecha' in out.columns:
        # dayfirst=True: si las celdas de Fecha son TEXTO en vez de fechas de
        # Excel, "05/09/26" se leería como 9 de mayo en lugar de 5 de septiembre.
        # Con días mayores de 12 no se nota, así que el fallo aparecería solo a
        # partir de septiembre y en silencio. Con fechas de Excel de verdad este
        # parámetro no cambia nada, así que sale gratis.
        # Sin ffill: arrastraba la última fecha conocida a todos los partidos
        # que aún no la tienen, y como 339 de los 380 están sin asignar, la app
        # mostraba el 3/9 en casi todo el calendario como si fuera real. Un
        # partido sin fecha se queda sin fecha y se dice.
        out['Fecha'] = pd.to_datetime(out['Fecha'], errors='coerce', dayfirst=True)
    else:
        out['Fecha'] = pd.NaT

    out['Gol Local'] = pd.to_numeric(out.get('Gol'), errors='coerce')
    out['Gol Visitante'] = pd.to_numeric(out.get('Gol.1'), errors='coerce')
    out['Local'] = out.get('Local', pd.Series(index=out.index, dtype=object)).astype(str).str.strip()
    out['Visitante'] = out.get('Fuera', pd.Series(index=out.index, dtype=object)).astype(str).str.strip()
    out = out[(out['Jornada'].notna()) & (out['Local'].notna()) & (out['Visitante'].notna())]
    out = out[~out['Local'].isin(['', 'nan', 'None']) & ~out['Visitante'].isin(['', 'nan', 'None'])]

    out['Jornada'] = out['Jornada'].astype(int)
    out['Estado'] = np.where(out['Gol Local'].notna() & out['Gol Visitante'].notna(), 'Finalizado', 'Pendiente')
    out['Resultado'] = np.where(
        out['Estado'].eq('Finalizado'),
        out['Gol Local'].astype('Int64').astype(str) + ' - ' + out['Gol Visitante'].astype('Int64').astype(str),
        '—'
    )
    # Hora del partido (columna J, la escribe el bot desde Biwenger). Texto
    # "21:00" o vacío si todavía no se sabe.
    if 'Hora' in out.columns:
        out['Hora'] = out['Hora'].map(_hora_calendario)
    else:
        out['Hora'] = None
    return out[['Jornada', 'Fecha', 'Hora', 'Local', 'Gol Local', 'Gol Visitante', 'Resultado', 'Visitante',
                'Estado']].reset_index(drop=True)


def calcular_clasificacion(df_cal):
    equipos = sorted(set(df_cal['Local'].dropna().tolist()) | set(df_cal['Visitante'].dropna().tolist())) if not df_cal.empty else []
    tabla = {
        e: {
            'Equipo': e, 'Pts': 0, 'PJ': 0, 'PG': 0, 'PE': 0, 'PP': 0, 'GF': 0, 'GC': 0, 'DG': 0,
            # 🏠 Splits como local: se usan para saber si un rival es fuerte/flojo
            # específicamente JUGANDO EN CASA (no solo en general).
            'Pts_Casa': 0, 'PJ_Casa': 0, 'PG_Casa': 0, 'PE_Casa': 0, 'PP_Casa': 0, 'GF_Casa': 0, 'GC_Casa': 0,
            # ✈️ Splits como visitante: para saber si es fuerte/flojo JUGANDO FUERA.
            'Pts_Fuera': 0, 'PJ_Fuera': 0, 'PG_Fuera': 0, 'PE_Fuera': 0, 'PP_Fuera': 0, 'GF_Fuera': 0, 'GC_Fuera': 0,
        }
        for e in equipos
    }

    for _, partido in df_cal.iterrows():
        gl, gv = partido['Gol Local'], partido['Gol Visitante']
        if pd.isna(gl) or pd.isna(gv):
            continue
        gl, gv = int(gl), int(gv)
        local, visitante = partido['Local'], partido['Visitante']
        if local not in tabla or visitante not in tabla:
            continue

        tabla[local]['PJ'] += 1
        tabla[visitante]['PJ'] += 1
        tabla[local]['GF'] += gl
        tabla[local]['GC'] += gv
        tabla[visitante]['GF'] += gv
        tabla[visitante]['GC'] += gl

        tabla[local]['PJ_Casa'] += 1
        tabla[local]['GF_Casa'] += gl
        tabla[local]['GC_Casa'] += gv
        tabla[visitante]['PJ_Fuera'] += 1
        tabla[visitante]['GF_Fuera'] += gv
        tabla[visitante]['GC_Fuera'] += gl

        if gl > gv:
            tabla[local]['PG'] += 1
            tabla[local]['Pts'] += 3
            tabla[visitante]['PP'] += 1
            tabla[local]['PG_Casa'] += 1
            tabla[local]['Pts_Casa'] += 3
            tabla[visitante]['PP_Fuera'] += 1
        elif gl < gv:
            tabla[visitante]['PG'] += 1
            tabla[visitante]['Pts'] += 3
            tabla[local]['PP'] += 1
            tabla[visitante]['PG_Fuera'] += 1
            tabla[visitante]['Pts_Fuera'] += 3
            tabla[local]['PP_Casa'] += 1
        else:
            tabla[local]['PE'] += 1
            tabla[visitante]['PE'] += 1
            tabla[local]['Pts'] += 1
            tabla[visitante]['Pts'] += 1
            tabla[local]['PE_Casa'] += 1
            tabla[visitante]['PE_Fuera'] += 1
            tabla[local]['Pts_Casa'] += 1
            tabla[visitante]['Pts_Fuera'] += 1

    result = pd.DataFrame(tabla.values())
    if result.empty:
        return result
    result['DG'] = result['GF'] - result['GC']
    result = result.sort_values(['Pts', 'DG', 'GF', 'Equipo'], ascending=[False, False, False, True]).reset_index(drop=True)
    result.insert(0, 'Pos', range(1, len(result) + 1))
    return result


def jornada_actual(df_cal):
    if df_cal.empty:
        return 0
    jugadas = df_cal.loc[df_cal['Estado'].eq('Finalizado'), 'Jornada']
    return int(jugadas.max()) if not jugadas.empty else 0


def calcular_valor_equipos(df_mercado):
    if df_mercado is None or df_mercado.empty or 'Equipo' not in df_mercado.columns:
        return {}
    return df_mercado.dropna(subset=['Equipo']).groupby('Equipo')['Valor Actual (€)'].sum().to_dict()


def calcular_puntos_equipos(df_mercado):
    """Puntos fantasy acumulados por TODOS los jugadores de cada equipo.

    Es la mejor vara de medir lo temible que es un rival en Biwenger, mejor que
    lo que cuesta su plantilla: el precio dice lo que el mercado cree que vale un
    equipo, y esto dice lo que de verdad está produciendo. Un equipo caro que no
    puntúa deja de dar miedo, y uno barato en racha empieza a darlo."""
    if df_mercado is None or df_mercado.empty:
        return {}
    if 'Equipo' not in df_mercado.columns or 'Puntos' not in df_mercado.columns:
        return {}
    aux = df_mercado.dropna(subset=['Equipo']).copy()
    aux['_pts'] = pd.to_numeric(aux['Puntos'], errors='coerce').fillna(0)
    return aux.groupby('Equipo')['_pts'].sum().to_dict()




def calcular_partidos_por_equipo(df_mercado):
    """{equipo: partidos disputados}, según el jugador más utilizado de cada uno."""
    if df_mercado is None or df_mercado.empty or 'Equipo' not in df_mercado.columns:
        return {}
    aux = df_mercado.dropna(subset=['Equipo']).copy()
    aux['_pj'] = pd.to_numeric(aux.get('PJ'), errors='coerce').fillna(0)
    return aux.groupby('Equipo')['_pj'].max().to_dict()


_CACHE_DIFICULTAD = {}


def dificultad_enfrentamiento(rival, es_casa, tabla_clas, valores_equipo=None, puntos_equipo=None):
    """Igual que siempre, pero recordando lo ya calculado.

    Medido con el perfilador: 3.522 llamadas y 24 segundos, o sea un 27% del
    arranque entero. Y para nada, porque solo hay 20 rivales × 2 condiciones =
    40 respuestas posibles: las calibraciones la llamaban una vez por cada
    actuación del histórico y recalculaban lo mismo una y otra vez. Cada llamada
    filtra tres DataFrames, y de ahí salen los millones de comparaciones que
    dominan el perfil.

    La caché vale dentro de una ejecución: las tablas se calculan una vez al
    arrancar y no cambian. Se guardan junto al resultado para que Python no
    pueda reciclar su id mientras estén en la caché, que es lo único que podría
    confundir una entrada con otra.
    """
    clave = (str(rival), bool(es_casa), id(tabla_clas), id(valores_equipo), id(puntos_equipo))
    guardado = _CACHE_DIFICULTAD.get(clave)
    if guardado is not None:
        return guardado[0]
    resultado = _calcular_dificultad_enfrentamiento(rival, es_casa, tabla_clas,
                                                    valores_equipo, puntos_equipo)
    _CACHE_DIFICULTAD[clave] = (resultado, tabla_clas, valores_equipo, puntos_equipo)
    return resultado




def dificultad_fixture(equipo, df_cal, tabla_clas, valores_equipo=None, puntos_equipo=None):
    """Dificultad del PRÓXIMO partido pendiente de un equipo."""
    if df_cal is None or df_cal.empty or not equipo or equipo == 'Desconocido':
        return None

    partidos_equipo = df_cal[(df_cal['Local'] == equipo) | (df_cal['Visitante'] == equipo)]
    pendientes = partidos_equipo[partidos_equipo['Estado'] == 'Pendiente']
    # Por fecha, no por número de jornada: con un partido aplazado, la jornada
    # más baja pendiente puede ser la que se juega dentro de un mes, mientras el
    # próximo partido de verdad es de una jornada posterior.
    orden = ['Fecha', 'Jornada'] if 'Fecha' in pendientes.columns else ['Jornada']
    pendientes = pendientes.sort_values(orden, na_position='last')
    if pendientes.empty:
        return None

    partido = pendientes.iloc[0]
    es_casa = partido['Local'] == equipo
    rival = partido['Visitante'] if es_casa else partido['Local']

    info = dificultad_enfrentamiento(rival, es_casa, tabla_clas, valores_equipo, puntos_equipo)
    info['jornada'] = int(partido['Jornada'])
    return info


def racha_equipo(equipo, df_cal, n=5):
    if df_cal is None or df_cal.empty or not equipo:
        return None
    jugados = df_cal[((df_cal['Local'] == equipo) | (df_cal['Visitante'] == equipo)) & (df_cal['Estado'] == 'Finalizado')]
    # También por fecha: la racha son los últimos partidos DISPUTADOS, y un
    # aplazado se juega mucho después del número de jornada que lleva.
    orden = ['Fecha', 'Jornada'] if 'Fecha' in jugados.columns else ['Jornada']
    jugados = jugados.sort_values(orden, na_position='last').tail(n)
    if jugados.empty:
        return None
    letras, pts = [], 0
    for _, p in jugados.iterrows():
        es_local = p['Local'] == equipo
        gf, gc = (p['Gol Local'], p['Gol Visitante']) if es_local else (p['Gol Visitante'], p['Gol Local'])
        if gf > gc: letras.append('G'); pts += 3
        elif gf == gc: letras.append('E'); pts += 1
        else: letras.append('P')
    return {'racha': ''.join(letras), 'ppp': round(pts / len(letras), 2)}


# Calendario y clasificación globales
df_cal_global = preparar_calendario(db.get('calendario'))
tabla_clasif_global = calcular_clasificacion(df_cal_global)
valores_equipos_global = calcular_valor_equipos(db.get('mercado'))
puntos_equipos_global = calcular_puntos_equipos(db.get('mercado'))
partidos_equipos_global = calcular_partidos_por_equipo(db.get('mercado'))


MODELO_DIFICULTAD_POR_DEFECTO = {'h': 1.0, 'b': 0.0, 'K': 4.0, 'medicion': 'sin datos suficientes'}
_PESOS_RESULTADOS_CANDIDATOS = (0.0, 0.25, 0.5, 0.75, 1.0)


def _z(serie):
    serie = pd.Series(serie, dtype=float)
    desv = serie.std()
    return (serie - serie.mean()) / desv if desv and not np.isnan(desv) else serie * 0.0


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_modelo_dificultad(huella=None):
    """Cómo se mide lo difícil que es un partido, comprobado contra lo que pasó.

    Para cada partido ya jugado se reconstruye lo que se sabía EL DÍA ANTES
    (valor de las plantillas en el Histórico de ese día, resultados anteriores)
    y se compara con los puntos fantasy que sacó de verdad el equipo en ese
    partido. Nada de mirar el futuro: la fórmula anterior se había calibrado
    con la clasificación y los puntos de HOY, que ya incluyen esos partidos.

    Medido el 24/09/2026 con 7 jornadas (118 partidos y 1.761 actuaciones):
      · el mejor retrato de un rival es el VALOR DE SU PLANTILLA (en escala
        logarítmica): +0,28 con los puntos del equipo, frente a +0,20 de la
        fórmula anterior; con los puntos de cada jugador respecto a su media,
        +0,16 frente a +0,04;
      · jugar fuera pesa MUCHO: -9,3 puntos fantasy por equipo y partido, lo
        mismo que un rival ~1,1 desviaciones más caro. El +12 fijo se queda
        corto y no estaba medido;
      · los resultados del rival (diferencia de goles por partido) aún no
        aportan con 6-7 partidos: son ruido. Su peso se recalcula con cada
        actualización y entrará solo cuando mejore la predicción.

    Devuelve {'h': peso de jugar fuera, 'b': peso de los resultados, 'K', 'medicion'}.
    """
    defecto = dict(MODELO_DIFICULTAD_POR_DEFECTO)
    try:
        cal = df_cal_global
        hist = cargar_historico_completo(huella)
        if cal is None or cal.empty or hist.empty:
            return defecto
        jugados = cal[(cal['Estado'] == 'Finalizado')].dropna(subset=['Fecha', 'Gol Local', 'Gol Visitante'])
        if len(jugados) < 40:
            return defecto

        h = hist[['Fecha', 'Jugador', 'Equipo', 'Puntos', 'Valor Actual (€)']].copy()
        h['Fecha'] = pd.to_datetime(h['Fecha'])
        h['Puntos'] = pd.to_numeric(h['Puntos'], errors='coerce')
        h = h.sort_values(['Jugador', 'Equipo', 'Fecha'])
        h['pts_dia'] = h.groupby(['Jugador', 'Equipo'])['Puntos'].diff()

        # Partidos desde el punto de vista de cada equipo.
        partidos = []
        for _, p in jugados.iterrows():
            gl, gv = float(p['Gol Local']), float(p['Gol Visitante'])
            partidos.append({'equipo': p['Local'], 'rival': p['Visitante'], 'fuera': 0.0,
                             'fecha': p['Fecha'], 'jornada': p['Jornada'], 'dg': gl - gv})
            partidos.append({'equipo': p['Visitante'], 'rival': p['Local'], 'fuera': 1.0,
                             'fecha': p['Fecha'], 'jornada': p['Jornada'], 'dg': gv - gl})
        partidos = pd.DataFrame(partidos)

        # Puntos fantasy que sacó cada equipo en cada partido: la foto del día
        # siguiente menos la anterior, sumada por equipo (como tabla_actuaciones).
        act = h[h['pts_dia'].notna() & (h['pts_dia'] != 0)]
        suma = act.groupby(['Equipo', 'Fecha'])['pts_dia'].sum()
        por_equipo = {e: g.sort_values('fecha') for e, g in partidos.groupby('equipo')}
        fpts = {}
        for (equipo, foto), total in suma.items():
            g = por_equipo.get(equipo)
            if g is None:
                continue
            cand = g[(g['fecha'] <= foto) & (g['fecha'] >= foto - pd.Timedelta(days=3))]
            if not cand.empty:
                clave = (equipo, cand['fecha'].iloc[-1])
                fpts[clave] = fpts.get(clave, 0.0) + float(total)
        partidos['fpts'] = [fpts.get((r.equipo, r.fecha)) for r in partidos.itertuples()]
        partidos = partidos.dropna(subset=['fpts'])

        # Lo que se sabía de cada rival el día antes de cada partido.
        fotos = sorted(h['Fecha'].unique())
        filas = []
        for fecha, grupo in partidos.groupby('fecha'):
            previas = [f for f in fotos if f < fecha]
            if not previas:
                continue
            foto = h[h['Fecha'] == previas[-1]]
            valores = foto.groupby('Equipo')['Valor Actual (€)'].sum()
            valores = valores[valores > 0]
            zv = _z(np.log(valores))
            antes = partidos[partidos['fecha'] < fecha]
            dg = antes.groupby('equipo')['dg'].mean()
            n = antes.groupby('equipo').size()
            zdg = _z(dg)
            for r in grupo.itertuples():
                if r.rival not in zv.index:
                    continue
                filas.append({'jornada': r.jornada, 'fpts': r.fpts, 'fuera': r.fuera,
                              'zv': float(zv[r.rival]), 'zdg': float(zdg.get(r.rival, 0.0)),
                              'n': float(n.get(r.rival, 0))})
        datos = pd.DataFrame(filas)
        if len(datos) < 60 or datos['jornada'].nunique() < 3:
            return defecto

        K = MODELO_DIFICULTAD_POR_DEFECTO['K']
        peso_n = datos['n'] / (datos['n'] + K)
        y = datos['fpts'].to_numpy(float)
        mejor = None
        for b in _PESOS_RESULTADOS_CANDIDATOS:
            s = (datos['zv'] + b * peso_n * datos['zdg']).to_numpy(float)
            X = np.c_[np.ones(len(s)), s, datos['fuera'].to_numpy(float)]
            pred = np.full(len(s), np.nan)
            # Se juzga cada jornada con los coeficientes del resto, para no
            # premiar lo que solo se ajusta a sí mismo.
            for j in datos['jornada'].unique():
                prueba = (datos['jornada'] == j).to_numpy()
                coef = np.linalg.lstsq(X[~prueba], y[~prueba], rcond=None)[0]
                pred[prueba] = X[prueba] @ coef
            rho = pd.Series(pred).corr(pd.Series(y), method='spearman')
            if mejor is None or rho > mejor[1] + 0.005:
                mejor = (b, rho)
        b = mejor[0]
        s = (datos['zv'] + b * peso_n * datos['zdg']).to_numpy(float)
        X = np.c_[np.ones(len(s)), s, datos['fuera'].to_numpy(float)]
        coef = np.linalg.lstsq(X, y, rcond=None)[0]
        if coef[1] >= 0:          # el rival más fuerte debería quitar puntos
            return defecto
        h_fuera = float(np.clip(coef[2] / coef[1], 0.3, 2.0))
        medicion = (f"{len(datos)} partidos: {coef[1]:+.1f} pts por desviación de fuerza del rival, "
                    f"{coef[2]:+.1f} jugando fuera; acierto de orden {mejor[1]:+.3f}")
        return {'h': round(h_fuera, 3), 'b': b, 'K': K, 'medicion': medicion}
    except Exception:
        return defecto


MODELO_DIFICULTAD = calibrar_modelo_dificultad(_huella_excel(resolver_excel_path()))
_ESCALA_DIFICULTAD = {}


def _escala_dificultad(tabla_clas, valores_equipo):
    """Fuerza de cada rival y los extremos de la escala 0-100, una vez por
    versión de las tablas. 0 = el partido más fácil posible de la liga (el
    rival más flojo, en casa); 100 = el más difícil (el más fuerte, fuera)."""
    clave = (id(tabla_clas), id(valores_equipo))
    if clave in _ESCALA_DIFICULTAD:
        return _ESCALA_DIFICULTAD[clave][0]
    modelo = globals().get('MODELO_DIFICULTAD', MODELO_DIFICULTAD_POR_DEFECTO)
    valores = pd.Series({e: v for e, v in (valores_equipo or {}).items() if v and v > 0}, dtype=float)
    if len(valores) < 2:
        _ESCALA_DIFICULTAD[clave] = (None, tabla_clas, valores_equipo)
        return None
    fuerza = _z(np.log(valores))
    if modelo['b'] and tabla_clas is not None and not tabla_clas.empty:
        t = tabla_clas.set_index('Equipo')
        pj = pd.to_numeric(t['PJ'], errors='coerce').fillna(0)
        dg = (pd.to_numeric(t['DG'], errors='coerce') / pj.replace(0, np.nan)).dropna()
        zdg = _z(dg)
        for e in fuerza.index:
            n = float(pj.get(e, 0))
            fuerza[e] += modelo['b'] * n / (n + modelo['K']) * float(zdg.get(e, 0.0))
    minimo, maximo = float(fuerza.min()), float(fuerza.max()) + modelo['h']
    escala = {'fuerza': fuerza.to_dict(), 'min': minimo, 'rango': max(1e-9, maximo - minimo),
              'h': modelo['h']}
    _ESCALA_DIFICULTAD[clave] = (escala, tabla_clas, valores_equipo)
    return escala


def _dificultades_posibles():
    """Las 40 dificultades posibles de la liga ahora mismo (20 rivales, en casa
    y fuera). Sirven de vara de medir para los colores y las etiquetas del
    tramo: con la escala nueva, «40» no significa lo mismo que antes."""
    escala = _escala_dificultad(tabla_clasif_global, valores_equipos_global)
    if not escala:
        return []
    return [100 * (f + extra - escala['min']) / escala['rango']
            for f in escala['fuerza'].values() for extra in (0.0, escala['h'])]


def cortes_color_dificultad():
    """Quintiles de los partidos posibles: cada color es un 20% de los cruces."""
    todas = _dificultades_posibles()
    if len(todas) < 10:
        return (30, 45, 60, 75)
    return tuple(float(np.percentile(todas, q)) for q in (20, 40, 60, 80))


def umbrales_tramo(n=3):
    """Cuándo un tramo de n partidos es cómodo o duro: por debajo o por encima
    del tercio central de lo que saldría con n rivales cualquiera de la liga."""
    todas = _dificultades_posibles()
    if len(todas) < 10:
        return 40.0, 60.0
    media, desv = float(np.mean(todas)), float(np.std(todas)) / max(1.0, n) ** 0.5
    return media - 0.43 * desv, media + 0.43 * desv


def _calcular_dificultad_enfrentamiento(rival, es_casa, tabla_clas, valores_equipo=None,
                                        puntos_equipo=None):
    """Dificultad (0-100) de enfrentarse a `rival` jugando en casa o fuera.

    Modelo medido contra lo que pasó (ver calibrar_modelo_dificultad): la
    fuerza del rival es el valor de su plantilla (en logaritmo, respecto al
    resto de la liga), más su diferencia de goles por partido cuando los datos
    demuestran que aporta, y jugar fuera suma lo que mide el Histórico.

    Además de 'dificultad' devuelve 'dificultad_sin_casa' (la del rival en
    campo neutral): es la que usa el motor de puntos, porque la localía del
    jugador ya entra por su media en casa y fuera."""
    escala = _escala_dificultad(tabla_clas, valores_equipo)
    pos_rival = None
    if tabla_clas is not None and not tabla_clas.empty and rival in tabla_clas['Equipo'].values:
        pos_rival = int(tabla_clas.loc[tabla_clas['Equipo'] == rival, 'Pos'].iloc[0])
    valor_rival = (valores_equipo or {}).get(rival)
    puntos_rival = (puntos_equipo or {}).get(rival)
    if not escala or rival not in escala['fuerza']:
        dificultad, sin_casa = 50.0, 50.0
    else:
        f = escala['fuerza'][rival]
        dificultad = 100 * (f + (0 if es_casa else escala['h']) - escala['min']) / escala['rango']
        sin_casa = 100 * (f + escala['h'] / 2 - escala['min']) / escala['rango']
    return {
        'rival': rival, 'es_casa': es_casa,
        'pos_rival': pos_rival, 'valor_rival': valor_rival, 'puntos_rival': puntos_rival,
        'dificultad': round(max(0.0, min(100.0, dificultad)), 1),
        'dificultad_sin_casa': round(max(0.0, min(100.0, sin_casa)), 1),
        'rival_fuerte_en_su_condicion': False,
        'comp_puntos': None, 'comp_clasif': None, 'comp_valor': None, 'credito': 0.0,
    }





# --- ⚡ CACHÉ DE CONTEXTO POR EQUIPO ---
# dificultad_fixture() y racha_equipo() recorren el calendario entero en cada
# llamada, y antes se llamaban una vez por CARTA pintada y varias veces por
# jugador dentro del optimizador del once. Como el resultado solo depende del
# equipo (20 valores posibles), se calcula una vez y se reutiliza.
_CACHE_FIXTURE = {}
_CACHE_RACHA = {}


@st.cache_data(show_spinner=False)
def _proximos_partidos_de_todos(huella=None):
    """El próximo partido de los veinte equipos. ⚡ Se calculaba de nuevo en
    cada clic (el diccionario de abajo se vacía con cada vuelta de la app) y
    solo cambia cuando cambian los datos."""
    if df_cal_global is None or df_cal_global.empty:
        return {}
    equipos = set(df_cal_global['Local'].dropna()) | set(df_cal_global['Visitante'].dropna())
    return {equipo: dificultad_fixture(equipo, df_cal_global, tabla_clasif_global,
                                       valores_equipos_global, puntos_equipos_global)
            for equipo in equipos}


def get_fixture_equipo(equipo):
    """Próximo partido pendiente del equipo: rival, si se juega en casa y dificultad."""
    if not _CACHE_FIXTURE:
        _CACHE_FIXTURE.update(_proximos_partidos_de_todos(_huella_excel(resolver_excel_path())))
    if equipo not in _CACHE_FIXTURE:
        _CACHE_FIXTURE[equipo] = dificultad_fixture(
            equipo, df_cal_global, tabla_clasif_global, valores_equipos_global,
            puntos_equipos_global
        )
    return _CACHE_FIXTURE[equipo]


def tramo_de_calendario(equipo, n=3, df_cal=None):
    """Cómo de duro es el tramo que le viene a un equipo en sus próximos n partidos.

    El motor solo mira el PRÓXIMO partido, y para decidir un fichaje eso se
    queda corto: un jugador al que le vienen tres rivales asequibles seguidos
    vale más que uno que tiene el mismo próximo rival y luego dos infiernos.
    Con fechas y resultados de verdad en el calendario, ese tramo ya se puede
    calcular.

    Devuelve None si no hay partidos por jugar; si no, un diccionario con la
    dificultad media (0-100), la lista de partidos y una etiqueta.
    """
    cal = df_cal if df_cal is not None else df_cal_global
    if cal is None or cal.empty or not equipo:
        return None
    # 🤖 El bot carga app.py con Streamlit simulado para reutilizar sus
    # funciones, y allí un st.slider no devuelve un número: devuelve un objeto
    # de relleno. Si eso llega a un .head(n) de pandas, el bot revienta al
    # arrancar y se queda sin actualizar nada. Cualquier valor que venga de un
    # widget y acabe en un cálculo tiene que sobrevivir a eso.
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 3

    pendientes = cal[((cal['Local'] == equipo) | (cal['Visitante'] == equipo))
                     & (cal['Estado'] != 'Finalizado')]
    if pendientes.empty:
        return None

    # Los que tienen fecha van primero y en orden; los que aún no la tienen van
    # detrás, porque son los de dentro de meses. Ordenar por jornada a secas
    # mezclaría un aplazado de la jornada 2 con lo que viene ahora.
    con_fecha = pendientes.dropna(subset=['Fecha']).sort_values('Fecha')
    sin_fecha = pendientes[pendientes['Fecha'].isna()].sort_values('Jornada')
    proximos = pd.concat([con_fecha, sin_fecha]).head(n)

    partidos = []
    for _, fila in proximos.iterrows():
        es_casa = fila['Local'] == equipo
        rival = fila['Visitante'] if es_casa else fila['Local']
        info = dificultad_enfrentamiento(rival, es_casa, tabla_clasif_global,
                                         valores_equipos_global, puntos_equipos_global)
        if not info:
            continue
        partidos.append({
            'jornada': int(fila['Jornada']) if pd.notna(fila['Jornada']) else None,
            'rival': rival, 'es_casa': es_casa,
            'fecha': fila['Fecha'] if pd.notna(fila['Fecha']) else None,
            'dificultad': info['dificultad'],
        })

    if not partidos:
        return None

    media = sum(p['dificultad'] for p in partidos) / len(partidos)
    comodo, duro = umbrales_tramo(len(partidos))
    if media < comodo:
        etiqueta = 'Tramo cómodo'
    elif media <= duro:
        etiqueta = 'Tramo normal'
    else:
        etiqueta = 'Tramo duro'
    return {'media': media, 'partidos': partidos, 'etiqueta': etiqueta,
            'sin_fecha': sum(1 for p in partidos if p['fecha'] is None)}


@st.cache_data(show_spinner=False)
def _rachas_de_todos(huella=None, n=5):
    """⚡ La racha de los veinte equipos, una vez por versión de los datos (el
    diccionario de abajo se vaciaba con cada clic)."""
    if df_cal_global is None or df_cal_global.empty:
        return {}
    equipos = set(df_cal_global['Local'].dropna()) | set(df_cal_global['Visitante'].dropna())
    return {(equipo, n): racha_equipo(equipo, df_cal_global, n=n) for equipo in equipos}


def get_racha_equipo(equipo, n=5):
    clave = (equipo, n)
    if clave not in _CACHE_RACHA and n == 5 and not _CACHE_RACHA:
        _CACHE_RACHA.update(_rachas_de_todos(_huella_excel(resolver_excel_path()), 5))
    if clave not in _CACHE_RACHA:
        _CACHE_RACHA[clave] = racha_equipo(equipo, df_cal_global, n=n)
    return _CACHE_RACHA[clave]


_CACHE_RATIO_CASA = {}


def get_ratio_casa_equipo(equipo):
    """Lo mismo, recordado: 1.058 llamadas para 20 equipos distintos."""
    clave = (str(equipo), id(tabla_clasif_global))
    if clave not in _CACHE_RATIO_CASA:
        _CACHE_RATIO_CASA[clave] = _calcular_ratio_casa_equipo(equipo)
    return _CACHE_RATIO_CASA[clave]


def _calcular_ratio_casa_equipo(equipo):
    """Proporción de los partidos ya disputados por el equipo que fueron en casa.
    Se usa para repartir el PJ del jugador entre casa y fuera: ni el export ni el
    Excel tienen ese desglose por jugador, así que se asume que ha seguido el
    mismo calendario que su equipo (exacto si no se ha perdido ningún partido).
    Es el mismo criterio que aplica Calcs!BS en el Excel, de modo que app y libro
    hablan el mismo idioma. 0.5 mientras no haya partidos jugados."""
    if tabla_clasif_global is None or tabla_clasif_global.empty:
        return 0.5
    fila = tabla_clasif_global.loc[tabla_clasif_global['Equipo'] == equipo]
    if fila.empty:
        return 0.5
    casa = float(fila.iloc[0].get('PJ_Casa', 0) or 0)
    fuera = float(fila.iloc[0].get('PJ_Fuera', 0) or 0)
    if casa + fuera <= 0:
        return 0.5
    return casa / (casa + fuera)


# --- 🔮 PUNTOS ESPERADOS POR JUGADOR ---
# Es la base de la predicción del once rival. La idea: partir de lo que el
# jugador puntúa DE VERDAD en la condición (casa/fuera) que le toca en su
# próximo partido, corregirlo por lo poco fiable que sea esa media cuando hay
# pocos partidos, y ajustarlo por el contexto del partido (rival y racha).

K_SHRINK_SPLIT = 6.0     # partidos "virtuales" antes de fiarse de la media casa/fuera.
                         # Subido de 3 a 6: con UN partido en cada condición la media
                         # casa/fuera es una anécdota, no un rasgo del jugador.
K_SHRINK_MUESTRA_MIN, K_SHRINK_MUESTRA_MAX = 3.0, 40.0
K_SHRINK_MUESTRA_POR_DEFECTO = 12.0   # mientras no haya histórico que medir


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_shrinkage_muestra(huella=None):
    """Cuántos partidos hacen falta para fiarse de la media de un jugador.

    Era una constante puesta a mano (4). Medido con las actuaciones que guarda
    el Histórico, ese 4 hacía daño: con una o dos jornadas, la media de un
    jugador NO predice lo que va a hacer el fin de semana (correlación -0,05
    con los puntos de esa jornada), mientras que su precio SÍ (+0,21). Dándole
    a la media un tercio del peso con solo dos partidos, se estaba metiendo
    ruido en el once ideal, en las cartas iluminadas y en todo lo que cuelga de
    los puntos esperados.

    Así que el número se calcula: se prueban varios valores contra lo que
    realmente pasó y se elige el que menos se equivoca. Conforme se acumulen
    jornadas la media irá ganando peso sola, sin tener que tocar nada.
    """
    try:
        hist = cargar_historico_completo(huella)
        if hist.empty or hist['Fecha'].nunique() < 4:
            return K_SHRINK_MUESTRA_POR_DEFECTO
        h = hist.sort_values(['Jugador', 'Fecha']).copy()
        h['pts_dia'] = h.groupby('Jugador')['Puntos'].diff()
        h['media_prev'] = h.groupby('Jugador')['Media Puntos'].shift(1)
        h['valor_prev'] = h.groupby('Jugador')['Valor Actual (€)'].shift(1)
        h['pts_prev'] = h.groupby('Jugador')['Puntos'].shift(1)
        act = h[h['pts_dia'].notna() & (h['pts_dia'] != 0)].dropna(
            subset=['media_prev', 'valor_prev', 'pts_prev'])
        act = act[act['valor_prev'] > 0]
        if len(act) < 60:
            return K_SHRINK_MUESTRA_POR_DEFECTO

        # Partidos jugados estimados a partir de puntos acumulados y media
        pj = np.where(act['media_prev'] > 0, act['pts_prev'] / act['media_prev'], 0)
        pj = np.round(np.clip(pj, 0, 40))
        media_liga = float(act['pts_dia'].mean())
        referencia = float(act['valor_prev'].median()) or 1.0
        prior = media_liga * np.clip((act['valor_prev'] / referencia) ** 0.35, 0.55, 1.8)

        mejor_k, mejor_error = K_SHRINK_MUESTRA_POR_DEFECTO, None
        for k in (3, 4, 6, 8, 10, 12, 15, 20, 25, 30, 40):
            peso = pj / (pj + k)
            pred = peso * act['media_prev'].values + (1 - peso) * prior.values
            error = float(np.abs(act['pts_dia'].values - pred).mean())
            if mejor_error is None or error < mejor_error:
                mejor_k, mejor_error = float(k), error
        return min(K_SHRINK_MUESTRA_MAX, max(K_SHRINK_MUESTRA_MIN, mejor_k))
    except Exception:
        return K_SHRINK_MUESTRA_POR_DEFECTO


K_SHRINK_MUESTRA = calibrar_shrinkage_muestra(_huella_excel(resolver_excel_path()))
MIN_PJ_REFERENCIA = 3    # muestra mínima para entrar en el cálculo del prior
# 🏠✈️ Topes del ajuste casa/fuera, MEDIDOS y no elegidos a ojo.
#
# Estaban en 0,65 y 1,45, o sea que el ajuste individual podía mover la
# estimación entre un -35% y un +45%. Y la ventaja real de jugar en casa,
# sobre 596 actuaciones, es del 13%: el rango era hasta OCHO VECES el efecto
# real, decidido muchas veces por un solo partido en cada condición.
#
# El destrozo que causaba: Pubill (18 puntos en 2 partidos, 15 en casa y 3
# fuera) quedaba por detrás de Arguibide (4 puntos), solo porque al primero le
# tocaba visitar y al segundo jugar en casa. Un partido bueno en casa y otro
# malo fuera no hacen a nadie "jugador de local".
#
# Medido con el motor completo:
#     sin ajuste          error 2,249 · correlación +0,371
#     ±13% (lo real)      error 2,245 · correlación +0,369   ← el elegido
#     ±30%                error 2,249 · correlación +0,357
#     ±80% (lo de antes)  error 2,336 · correlación +0,300
MULT_SPLIT_MIN = 0.90
MULT_SPLIT_MAX = 1.13
# Medido con 358 actuaciones emparejadas con su partido: en casa se hacen 4,09
# puntos de media y fuera 3,99, o sea un +2,6% y no el +5% que se suponía.
VENTAJA_LOCAL_POR_DEFECTO = 0.026
VENTAJA_LOCAL = VENTAJA_LOCAL_POR_DEFECTO   # se recalibra más abajo con calibrar_ventaja_local()

# 🎚️ Cuánto corrige el rival. El rango era [0,85 – 1,15] puesto a ojo, y se
# quedaba MUY corto: midiendo las actuaciones reales contra la dificultad del
# partido que jugaron, los rivales fáciles dan 5,42 puntos de media y los
# difíciles 3,44 (correlación -0,22). Eso es un abanico de [0,84 – 1,33] sobre
# la media de la liga, más del doble de ancho que el que se aplicaba.
#
# Se calibra con los datos y se acota, porque con pocas jornadas el extremo
# fácil se dispara con facilidad.
AMPLITUD_DIFICULTAD_MIN, AMPLITUD_DIFICULTAD_MAX = 0.30, 0.60


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_amplitud_dificultad(huella=None):
    """Cuánto separa de verdad un rival fácil de uno difícil."""
    try:
        hist = cargar_historico_completo(huella)
        cal = preparar_calendario(db.get('calendario'))
        if hist.empty or cal is None or cal.empty:
            return 0.30
        h = hist.sort_values(['Jugador', 'Fecha']).copy()
        h['pts_dia'] = h.groupby('Jugador')['Puntos'].diff()
        act = h[h['pts_dia'].notna() & (h['pts_dia'] != 0)].copy()
        if len(act) < 100:
            return 0.30
        cal = cal.dropna(subset=['Fecha']).copy()
        cal['dia'] = pd.to_datetime(cal['Fecha']).dt.normalize()
        # Los puntos aparecen en el export al día siguiente del partido.
        act['dia_partido'] = pd.to_datetime(act['Fecha']).dt.normalize() - pd.Timedelta(days=1)

        # ⚡ Índice (día, equipo) -> primer partido de ese día, en el orden del
        # calendario (lo mismo que hacía el filtro fila a fila, sin repetirlo).
        indice = {}
        for dia_p, local_p, visit_p in zip(cal['dia'], cal['Local'], cal['Visitante']):
            indice.setdefault((dia_p, local_p), (local_p, visit_p))
            indice.setdefault((dia_p, visit_p), (local_p, visit_p))
        dificultades = {}
        difs, puntos = [], []
        for dia_a, equipo_a, pts_a in zip(act['dia_partido'], act['Equipo'], act['pts_dia']):
            p = indice.get((dia_a, equipo_a))
            if p is None:
                continue
            es_casa = p[0] == equipo_a
            rival = p[1] if es_casa else p[0]
            if (rival, es_casa) not in dificultades:
                dificultades[(rival, es_casa)] = dificultad_enfrentamiento(
                    rival, es_casa, tabla_clasif_global, valores_equipos_global, puntos_equipos_global)
            info = dificultades[(rival, es_casa)]
            if info:
                difs.append(info.get('dificultad_sin_casa', info['dificultad']))
                puntos.append(pts_a)
        if len(difs) < 80:
            return 0.30

        marco = pd.DataFrame({'dif': difs, 'pts': puntos})
        faciles = marco[marco['dif'] <= 40]['pts'].mean()
        duros = marco[marco['dif'] >= 60]['pts'].mean()
        media = marco['pts'].mean()
        if not media or pd.isna(faciles) or pd.isna(duros) or faciles <= duros:
            return 0.30
        # Diferencia entre los dos extremos, llevada a la escala 0-100 de la
        # dificultad (los centros de esos grupos distan unos 50 puntos).
        amplitud = (faciles - duros) / media
        return float(min(AMPLITUD_DIFICULTAD_MAX, max(AMPLITUD_DIFICULTAD_MIN, amplitud)))
    except Exception:
        return 0.30


AMPLITUD_DIFICULTAD = calibrar_amplitud_dificultad(_huella_excel(resolver_excel_path()))
AMPLITUD_DIFICULTAD_CENTRO = 1.0 + AMPLITUD_DIFICULTAD / 2

# Cuánto puntúa cada posición respecto a la media de la liga, MIENTRAS NO HAYA
# DATOS REALES. En clave fantasy los medios y delanteros tienen más vías de
# puntuar que los defensas, así que dos jugadores del mismo precio y distinta
# posición no valen lo mismo. Son una suposición de partida, no una medición:
# en cuanto haya 5 jugadores por posición con 3 partidos, la app calcula la
# mediana real de cada posición y estos números dejan de usarse. Si crees que
# el reparto debería ser otro, se toca aquí y ya está.
# Actualizados con lo medido en 358 actuaciones (puntos de cada posición sobre
# la media de la liga): portero 1,20 · centrocampista 1,04 · delantero 1,03 ·
# defensa 0,90. Defensa y centrocampista estaban bien; el portero estaba muy
# mal (se suponía 0,95 cuando es la posición que más puntúa, por las porterías
# a cero) y el delantero algo inflado. El portero se deja algo por debajo de lo
# medido porque son solo 24 actuaciones y con tan pocas la cifra baila.
PESO_POSICION_POR_DEFECTO = {
    'Portero': 1.00, 'Defensa': 0.95, 'Centrocampista': 1.02, 'Delantero': 1.03,
}
K_MUESTRA_POSICION = 60   # actuaciones antes de fiarse del dato de una posición


def _a_float(valor, defecto=None):
    """Convierte a float tolerando comas decimales y celdas vacías del Excel."""
    try:
        num = float(str(valor).replace(',', '.'))
    except (TypeError, ValueError):
        return defecto
    return defecto if pd.isna(num) else num


def construir_prior_media(df_mercado, min_pj=MIN_PJ_REFERENCIA):
    """Devuelve una función jugador -> media de puntos esperada según su posición
    y su precio, calibrada con los jugadores que SÍ tienen muestra.

    Es el ancla para quien apenas ha jugado. Sin ella pasan dos cosas malas: un
    fichaje caro con un solo partido flojo se hunde en el ranking, y a principio
    de temporada (todos a 0 partidos) el optimizador se queda sin criterio.

    Cuando una posición ya tiene suficientes jugadores rodados, manda su mediana
    real. Mientras no la tenga, se usa la mediana global corregida por
    PESO_POSICION, para que un defensa y un delantero del mismo precio no
    arranquen empatados: en fantasy el delantero tiene más vías de puntuar."""
    referencia = {}
    global_media, global_valor = 4.0, 3000000.0

    if df_mercado is not None and not df_mercado.empty:
        aux = df_mercado.copy()
        aux['_pj'] = pd.to_numeric(aux.get('PJ'), errors='coerce').fillna(0)
        aux['_media'] = pd.to_numeric(aux.get('Media Puntos'), errors='coerce')
        aux['_valor'] = pd.to_numeric(aux.get('Valor Actual (€)'), errors='coerce')
        aux['_pos'] = aux.get('Posición').astype(str).str.split('/').str[0].str.strip()
        con_muestra = aux[(aux['_pj'] >= min_pj) & aux['_media'].notna() & aux['_valor'].gt(0)]

        if not con_muestra.empty:
            global_media = float(con_muestra['_media'].median())
            global_valor = float(con_muestra['_valor'].median())
            for pos, grupo in con_muestra.groupby('_pos'):
                if len(grupo) >= 5:
                    referencia[pos] = (float(grupo['_media'].median()), float(grupo['_valor'].median()))

    def prior(player):
        pos = str(player.get('Posición', '')).split('/')[0].strip()
        if pos in referencia:
            media_ref, valor_ref = referencia[pos]
        else:
            media_ref = global_media * PESO_POSICION.get(pos, 1.0)
            valor_ref = global_valor
        valor = _a_float(player.get('Valor Actual (€)'), 0.0) or 0.0
        if valor <= 0 or valor_ref <= 0:
            return media_ref
        # El precio informa, pero con rendimientos decrecientes: un jugador que
        # cuesta el doble no puntúa el doble. El exponente ya no está puesto a
        # ojo, lo mide calibrar_exponente_precio(). Acotado para que ni un
        # galáctico ni un descarte se salgan de la escala real de la liga.
        factor = (valor / valor_ref) ** globals().get('EXPONENTE_PRECIO', 0.35)
        return media_ref * max(0.55, min(1.8, factor))

    return prior


prior_media_liga = construir_prior_media(db.get('mercado'))


def media_esperada_jugador(player, es_casa=True, ratio_casa=0.5, prior_fn=None):
    """Media de puntos que cabe esperar del jugador en la condición (casa/fuera)
    que le toca en su próximo partido.

    Dos ajustes, los dos por tamaño de muestra:
      1) su media general se mezcla con el prior de posición/precio según los
         partidos que lleve jugados,
      2) la media casa/fuera se aplica como MULTIPLICADOR sobre ese nivel
         (cuánto mejor o peor rinde en esa condición), no como un nivel propio.

    El punto 2 es importante y no es un capricho. Las columnas F y G del Excel
    reparten los puntos usando el ratio casa/fuera del EQUIPO, así que cuando un
    jugador se ha perdido partidos el denominador puede ser una fracción de
    partido y la media se dispara: un portero que jugó un solo partido fuera y
    sacó 11 puntos aparece con "27,50 de media fuera". Ese 27,50 no es su nivel,
    es un artefacto del prorrateo. Como multiplicador acotado informa (rinde
    mejor fuera) sin contaminar la escala.

    Nota: una media casa/fuera de 0 se trata como "sin dato", no como "puntúa 0".
    El Excel no puede distinguir "jugó en casa e hizo 0" de "no jugó en casa", y
    dar por bueno el 0 castigaría a quien simplemente no ha tenido el partido.

    Devuelve (media, peso_split), donde peso_split va de 0 a 1 y dice cuánto se
    ha podido fiar de los datos propios del jugador en esa condición. Lo usa
    puntos_esperados_jugador para saber si hace falta aplicar la ventaja de
    local genérica o si ya está contada en sus propias medias."""
    prior_fn = prior_fn or prior_media_liga
    pj = _a_float(player.get('PJ'), 0.0) or 0.0
    media_general = _a_float(player.get('Media Puntos'), None)
    media_split = _a_float(
        player.get('Media Puntos Casa' if es_casa else 'Media Puntos Fuera'), None
    )

    prior = prior_fn(player)

    if media_general is None or pj <= 0:
        base = prior
    else:
        peso = pj / (pj + K_SHRINK_MUESTRA)
        base = peso * media_general + (1 - peso) * prior

    ratio = min(max(ratio_casa if ratio_casa is not None else 0.5, 0.05), 0.95)
    # Desglose exacto si la hoja PJ_Split está al día; si no, el reparto
    # aproximado de siempre con el calendario del equipo.
    pj_split = _a_float(player.get('PJ Casa' if es_casa else 'PJ Fuera'), None)
    if pj_split is None:
        pj_split = pj * (ratio if es_casa else (1 - ratio))

    if not media_split or not media_general or pj_split <= 0:
        return base, 0.0

    peso_split = pj_split / (pj_split + K_SHRINK_SPLIT)
    multiplicador = 1 + peso_split * (media_split / media_general - 1)
    return base * max(MULT_SPLIT_MIN, min(MULT_SPLIT_MAX, multiplicador)), peso_split


def factor_dificultad(fixture):
    """Corrección por el rival del próximo partido. Rango [0,85 – 1,15].

    Usa la dificultad del rival en campo neutral: la localía del jugador ya
    entra por su media casa/fuera, y contarla dos veces penalizaría de más a
    todo el que juegue como visitante."""
    if not fixture:
        return 1.0
    # La del rival en campo neutral: la localía del jugador ya entra por su
    # media en casa y fuera, y contarla dos veces penalizaría de más.
    dif = _a_float(fixture.get('dificultad_sin_casa'), None)
    if dif is None:
        dif = _a_float(fixture.get('dificultad'), 50.0)
        if dif is None:
            dif = 50.0
    dif = max(0.0, min(100.0, dif))
    return AMPLITUD_DIFICULTAD_CENTRO - (dif / 100.0) * AMPLITUD_DIFICULTAD


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_pesos_posicion(huella=None):
    """Cuánto puntúa cada posición, medido en vez de escrito a mano.

    Los valores estaban congelados de una medición puntual. Ahora se recalculan
    con las actuaciones del Histórico y se encogen hacia 1 según la muestra que
    haya: con 24 actuaciones de portero no se puede afirmar gran cosa, así que
    su peso se queda cerca del neutro hasta que haya datos de sobra."""
    try:
        hist = cargar_historico_completo(huella)
        if hist.empty:
            return dict(PESO_POSICION_POR_DEFECTO)
        h = hist.sort_values(['Jugador', 'Fecha']).copy()
        h['pts_dia'] = h.groupby('Jugador')['Puntos'].diff()
        act = h[h['pts_dia'].notna() & (h['pts_dia'] != 0)].copy()
        if len(act) < 100:
            return dict(PESO_POSICION_POR_DEFECTO)
        act['_pos'] = act['Posición'].astype(str).str.split('/').str[0].str.strip()
        media = float(act['pts_dia'].mean())
        if not media:
            return dict(PESO_POSICION_POR_DEFECTO)

        pesos = dict(PESO_POSICION_POR_DEFECTO)
        for pos, grupo in act.groupby('_pos'):
            if pos not in pesos:
                continue
            bruto = float(grupo['pts_dia'].mean()) / media
            confianza = len(grupo) / (len(grupo) + K_MUESTRA_POSICION)
            pesos[pos] = round(1.0 + (bruto - 1.0) * confianza, 3)
        return pesos
    except Exception:
        return dict(PESO_POSICION_POR_DEFECTO)


AMPLITUD_RACHA_MIN, AMPLITUD_RACHA_MAX = 0.0, 0.70


@st.cache_data(show_spinner=False, persist="disk")
def tabla_actuaciones(huella=None):
    """Cada actuación real con las condiciones en que se produjo.

    Es la base de todas las calibraciones: qué hizo un jugador un día concreto,
    cuánto valía la víspera, contra quién jugaba, cómo iba su equipo y si era en
    casa. Se construye una vez y se cachea en disco."""
    try:
        hist = cargar_historico_completo(huella)
        cal = preparar_calendario(db.get('calendario'))
        if hist.empty or cal is None or cal.empty:
            return pd.DataFrame()
        h = hist.sort_values(['Jugador', 'Fecha']).copy()
        h['pts_dia'] = h.groupby('Jugador')['Puntos'].diff()
        h['valor_prev'] = h.groupby('Jugador')['Valor Actual (€)'].shift(1)
        h['media_prev'] = h.groupby('Jugador')['Media Puntos'].shift(1)
        h['pts_prev'] = h.groupby('Jugador')['Puntos'].shift(1)
        act = h[h['pts_dia'].notna() & (h['pts_dia'] != 0)].dropna(subset=['valor_prev'])
        act = act[act['valor_prev'] > 0]
        if act.empty:
            return pd.DataFrame()

        cal = cal.dropna(subset=['Fecha'])
        jugados = cal[cal['Estado'] == 'Finalizado'].dropna(subset=['Gol Local', 'Gol Visitante'])

        # ⚡ Antes, por cada una de las ~2.000 actuaciones se filtraba el
        # calendario entero dos veces y se recorrían sus partidos previos: 4 s
        # de cada arranque en frío (y hay uno cada vez que cambian los datos,
        # también con el botón de actualizar). Ahora se prepara una vez por
        # equipo y cada actuación se resuelve con una búsqueda binaria. Mismo
        # resultado, comprobado fila a fila.
        import bisect
        previos_por_equipo = {}      # equipo -> (fechas ordenadas, puntos acumulados)
        for equipo_j in set(jugados['Local']) | set(jugados['Visitante']):
            propios = jugados[(jugados['Local'] == equipo_j) | (jugados['Visitante'] == equipo_j)]
            registro = []
            for fecha_p, local_p, gl_p, gv_p in zip(propios['Fecha'], propios['Local'],
                                                    propios['Gol Local'], propios['Gol Visitante']):
                mios, ajenos = (gl_p, gv_p) if local_p == equipo_j else (gv_p, gl_p)
                registro.append((fecha_p, 3 if mios > ajenos else (1 if mios == ajenos else 0)))
            registro.sort(key=lambda r: r[0])
            acumulado, suma = [], 0
            for _, puntos_p in registro:
                suma += puntos_p
                acumulado.append(suma)
            previos_por_equipo[equipo_j] = ([r[0] for r in registro], acumulado)
        partidos_por_equipo = {}     # equipo -> [(fecha, local, visitante)] por fecha
        for fecha_p, local_p, visit_p in zip(cal['Fecha'], cal['Local'], cal['Visitante']):
            partidos_por_equipo.setdefault(local_p, []).append((fecha_p, local_p, visit_p))
            partidos_por_equipo.setdefault(visit_p, []).append((fecha_p, local_p, visit_p))
        for lista in partidos_por_equipo.values():
            lista.sort(key=lambda r: r[0])
        dificultades = {}

        filas = []
        for a in act.to_dict('records'):
            equipo, fecha = a['Equipo'], a['Fecha']
            fechas_prev, acumulado = previos_por_equipo.get(equipo, ([], []))
            n_previos = bisect.bisect_left(fechas_prev, fecha)
            candidatos = [p for p in partidos_por_equipo.get(equipo, [])
                          if fecha - pd.Timedelta(days=3) <= p[0] <= fecha]
            if not n_previos or not candidatos:
                continue
            ganados = acumulado[n_previos - 1]
            _, local_p, visit_p = candidatos[-1]
            en_casa = local_p == equipo
            rival = visit_p if en_casa else local_p
            if (rival, en_casa) not in dificultades:
                dificultades[(rival, en_casa)] = dificultad_enfrentamiento(
                    rival, en_casa, tabla_clasif_global, valores_equipos_global, puntos_equipos_global)
            info = dificultades[(rival, en_casa)]
            if not info:
                continue
            media_prev = _a_float(a.get('media_prev'), 0.0) or 0.0
            pts_prev = _a_float(a.get('pts_prev'), 0.0) or 0.0
            filas.append({
                # El nombre y la fecha no los usaba nadie, pero sin ellos no se
                # puede cruzar esta tabla con nada de fuera (goles, asistencias,
                # jornada), y eso deja el motor encerrado en lo que ya sabe.
                'jugador': a.get('Jugador'), 'equipo': equipo, 'fecha': fecha,
                'pts': a['pts_dia'], 'valor': a['valor_prev'], 'media': media_prev,
                'pj': round(pts_prev / media_prev) if media_prev > 0 else 0,
                'ppp': ganados / n_previos, 'dif': info['dificultad'],
                'casa': bool(en_casa),
                'comp_puntos': info.get('comp_puntos'), 'comp_clasif': info.get('comp_clasif'),
                'comp_valor': info.get('comp_valor'), 'credito': info.get('credito', 0.0),
                'pos': str(a['Posición']).split('/')[0].strip(),
            })
        return pd.DataFrame(filas)
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_amplitud_racha(huella=None):
    """Cuánto corrige el momento del equipo (sus últimos 5 resultados) los
    puntos de un jugador, descontando lo que ya dicen su precio, el rival y si
    juega en casa.

    Revisado el 24/09/2026: la versión de agosto medía con los puntos por
    partido de TODA la temporada del equipo, no con los cinco últimos que usa
    el motor, y tenía un suelo de 0,16. Salía 0,47: el factor más fuerte del
    motor. Medido bien, con 7 jornadas, el efecto real es mucho menor (~0,13), y
    con 0,47 el once se ordenaba peor: entre los titulares probables de cada
    posición, la correlación con los puntos de la jornada pasaba de +0,25 a
    +0,28 al quitarlo."""
    try:
        import bisect
        from sklearn.linear_model import LinearRegression
        datos = tabla_actuaciones(huella)
        cal = df_cal_global
        if datos.empty or len(datos) < 150 or cal is None or cal.empty:
            return AMPLITUD_RACHA_MIN
        jugados = cal[cal['Estado'] == 'Finalizado'].dropna(subset=['Fecha', 'Gol Local', 'Gol Visitante'])
        por_equipo = {}
        for _, p in jugados.sort_values('Fecha').iterrows():
            for equipo, mios, ajenos in ((p['Local'], p['Gol Local'], p['Gol Visitante']),
                                         (p['Visitante'], p['Gol Visitante'], p['Gol Local'])):
                por_equipo.setdefault(equipo, []).append(
                    (p['Fecha'], 3 if mios > ajenos else (1 if mios == ajenos else 0)))
        rachas = []
        for equipo, fecha in zip(datos['equipo'], pd.to_datetime(datos['fecha'])):
            lista = por_equipo.get(equipo, [])
            # El partido de esta actuación es el último hasta la foto; la racha,
            # los cinco anteriores a él.
            i = bisect.bisect_right([f for f, _ in lista], fecha) - 1
            previos = [r for _, r in lista[max(0, i - 5):max(0, i)]]
            rachas.append(float(np.mean(previos)) if previos else np.nan)
        marco = datos.assign(racha=rachas).dropna(subset=['valor', 'dif', 'racha', 'pts'])
        marco = marco[marco['valor'] > 0]
        if len(marco) < 150:
            return AMPLITUD_RACHA_MIN
        media = float(marco['pts'].mean())
        if not media:
            return AMPLITUD_RACHA_MIN
        X = np.c_[np.log10(marco['valor']), marco['dif'], marco['casa'].astype(float), marco['racha']]
        coef = LinearRegression().fit(X, marco['pts']).coef_[3]
        # Diferencia entre ir a 0 y a 3 puntos por partido, sobre la media. Si
        # sale negativa, no hay efecto que aplicar.
        amplitud = max(0.0, float(coef)) * 3.0 / media
        return float(min(AMPLITUD_RACHA_MAX, max(AMPLITUD_RACHA_MIN, amplitud)))
    except Exception:
        return AMPLITUD_RACHA_MIN


PESO_POSICION = calibrar_pesos_posicion(_huella_excel(resolver_excel_path()))
AMPLITUD_RACHA = calibrar_amplitud_racha(_huella_excel(resolver_excel_path()))


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_ventaja_local(huella=None):
    """Cuánto más puntúa un jugador en casa que fuera, medido y no a ojo.

    Era 0,026, de una medición de agosto con 358 actuaciones. Con 7 jornadas se
    hacen 4,57 puntos de media en casa y 3,86 fuera: un ±8%, tres veces más.
    Se encoge hacia cero según la muestra para no exagerarlo con pocos datos."""
    try:
        datos = tabla_actuaciones(huella)
        if datos.empty or len(datos) < 150:
            return VENTAJA_LOCAL_POR_DEFECTO
        casa = datos.loc[datos['casa'].astype(bool), 'pts']
        fuera = datos.loc[~datos['casa'].astype(bool), 'pts']
        if len(casa) < 50 or len(fuera) < 50 or (casa.mean() + fuera.mean()) <= 0:
            return VENTAJA_LOCAL_POR_DEFECTO
        bruta = (casa.mean() - fuera.mean()) / (casa.mean() + fuera.mean())
        confianza = len(datos) / (len(datos) + 400.0)
        return float(np.clip(bruta * confianza, 0.0, 0.15))
    except Exception:
        return VENTAJA_LOCAL_POR_DEFECTO


VENTAJA_LOCAL = calibrar_ventaja_local(_huella_excel(resolver_excel_path()))




@st.cache_data(show_spinner=False, persist="disk")
def calibrar_escala_motor(huella=None):
    """(media de puntos por jornada, cuánto encoger la predicción del motor).

    El motor multiplica cinco factores en cadena y eso dispersa sus resultados
    mucho más de lo que se dispersa la realidad: ordenaba bien (correlación
    +0,37) pero su error absoluto era PEOR que el de predecir simplemente la
    media de la liga. Encogiendo hacia esa media el orden NO cambia —el once
    ideal es el mismo— pero los números dejan de estar inflados.

    El factor se elige probando valores contra las actuaciones reales."""
    datos = tabla_actuaciones(huella)
    if datos.empty or len(datos) < 100:
        return (4.0, 0.6)
    media = float(datos['pts'].mean())
    referencia = float(datos['valor'].median()) or 1.0

    pred = media * np.clip((datos['valor'] / referencia) ** 0.35, 0.55, 1.8).values
    pred = pred * datos['pos'].map(PESO_POSICION).fillna(1.0).values
    peso = datos['pj'] / (datos['pj'] + K_SHRINK_MUESTRA)
    pred = peso.values * datos['media'].values + (1 - peso.values) * pred
    pred = pred * np.clip((1 + AMPLITUD_DIFICULTAD / 2) - (datos['dif'] / 100) * AMPLITUD_DIFICULTAD,
                          1 - AMPLITUD_DIFICULTAD / 2, 1 + AMPLITUD_DIFICULTAD / 2).values
    pred = pred * np.clip((1 - AMPLITUD_RACHA / 2) + (datos['ppp'] / 3) * AMPLITUD_RACHA,
                          1 - AMPLITUD_RACHA / 2, 1 + AMPLITUD_RACHA / 2).values
    pred = pred * np.where(datos['casa'], 1 + VENTAJA_LOCAL, 1.0)

    mejor, mejor_error = 1.0, None
    for alfa in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0):
        error = float(np.abs(datos['pts'].values - (media + alfa * (pred - media))).mean())
        if mejor_error is None or error < mejor_error:
            mejor, mejor_error = alfa, error
    return (media, mejor)


EXPONENTE_PRECIO_POR_DEFECTO = 0.35


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_exponente_precio(huella=None):
    """Cuánto informa el precio sobre los puntos que hará un jugador.

    El 0,35 estaba puesto a ojo. Medido contra las actuaciones reales, un
    exponente más suave acierta bastante mejor en la cifra (error 2,37 frente a
    2,47), aunque ordena una pizca peor. Como el orden es lo que decide el once,
    se elige el que menos se equivoca ENTRE los que conservan casi toda la
    capacidad de ordenar: así se gana precisión sin aplanar el ranking."""
    datos = tabla_actuaciones(huella)
    if datos.empty or len(datos) < 100:
        return EXPONENTE_PRECIO_POR_DEFECTO
    media = float(datos['pts'].mean())
    referencia = float(datos['valor'].median()) or 1.0

    resultados = []
    for exponente in (0.15, 0.20, 0.25, 0.30, 0.35, 0.45, 0.60):
        pred = media * np.clip((datos['valor'] / referencia) ** exponente, 0.55, 1.8)
        error = float(np.abs(datos['pts'] - pred).mean())
        corr = float(np.corrcoef(pred, datos['pts'])[0, 1])
        resultados.append((exponente, error, corr))
    mejor_corr = max(r[2] for r in resultados)
    # Solo se consideran los que no pierden más de un 5% de correlación.
    validos = [r for r in resultados if r[2] >= mejor_corr * 0.95]
    return float(min(validos, key=lambda r: r[1])[0]) if validos else EXPONENTE_PRECIO_POR_DEFECTO


EXPONENTE_PRECIO = calibrar_exponente_precio(_huella_excel(resolver_excel_path()))







MEDIA_LIGA_JORNADA, ESCALA_MOTOR = calibrar_escala_motor(_huella_excel(resolver_excel_path()))


def factor_racha(racha):
    """Corrección por el momento de forma del equipo. La amplitud ya no está
    puesta a mano: la mide calibrar_amplitud_racha() con las actuaciones reales.
    Neutro a 1,5 puntos por partido, que es el rendimiento medio de un equipo."""
    if not racha:
        return 1.0
    ppp = _a_float(racha.get('ppp'), None)
    if ppp is None:
        return 1.0
    minimo = 1.0 - AMPLITUD_RACHA / 2.0
    return max(minimo, min(1.0 + AMPLITUD_RACHA / 2.0, minimo + (ppp / 3.0) * AMPLITUD_RACHA))


# --- 👤 PROBABILIDAD DE JUGAR ---
# El motor trabajaba con la media POR PARTIDO JUGADO y nunca se preguntaba si el
# jugador va a jugar. Un suplente que ha entrado dos veces y ha cuajado dos
# buenas actuaciones tiene una media altísima, y el domingo se queda en el
# banquillo y hace cero. Medido sobre una temporada simulada de 6 jornadas: 63
# jugadores tenían media de 6 o más jugando la mitad o menos de los partidos, y
# son justo los que se colaban en el once por delante de un titular fijo.
#
# La tasa sale de sus partidos entre los de su equipo, encogida hacia una
# probabilidad de partida: con dos jornadas nadie es "suplente confirmado", así
# que al principio todos salen parecidos y las diferencias se marcan solas.
#
# Los partidos del equipo se deducen del PROPIO EXPORT (el jugador más usado de
# cada equipo los ha jugado todos), no de la clasificación: así el cálculo no
# depende de que los resultados estén metidos en el calendario.
K_TITULARIDAD_POR_DEFECTO, PROB_TITULARIDAD_POR_DEFECTO = 3.0, 0.60


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_titularidad(huella=None):
    """(partidos virtuales, probabilidad de partida) para estimar quién juega.

    Estaban puestos a ojo en 3 y 0,70, y ese 0,70 salía caro: a los jugadores
    sin historial los empujaba hacia "titular", y medido resultó que la app les
    daba un 52% de probabilidad cuando en realidad juegan el 27% de las veces.
    Con los fijos acertaba (78% estimado, 79% real), o sea que el problema era
    justo el arranque, que es donde más falta hace afinar.

    Se eligen los dos valores que mejor calibran contra lo que pasó de verdad,
    midiendo con el error cuadrático de la probabilidad (Brier), que es el que
    penaliza tanto pasarse como quedarse corto."""
    try:
        hist = cargar_historico_completo(huella)
        if hist.empty:
            return (K_TITULARIDAD_POR_DEFECTO, PROB_TITULARIDAD_POR_DEFECTO)
        h = hist.sort_values(['Jugador', 'Fecha']).copy()
        h['pts_dia'] = h.groupby('Jugador')['Puntos'].diff()
        h['pts_prev'] = h.groupby('Jugador')['Puntos'].shift(1)
        h['media_prev'] = h.groupby('Jugador')['Media Puntos'].shift(1)
        h['jugo'] = (h['pts_dia'].notna() & (h['pts_dia'] != 0)).astype(int)

        # Solo cuentan los días en que su equipo jugó: si no hay partido, no
        # jugar no dice nada del jugador.
        dias = h[h['jugo'] == 1][['Equipo', 'Fecha']].drop_duplicates()
        casos = h.merge(dias, on=['Equipo', 'Fecha'], how='inner').dropna(
            subset=['pts_prev', 'media_prev'])
        if len(casos) < 80:
            return (K_TITULARIDAD_POR_DEFECTO, PROB_TITULARIDAD_POR_DEFECTO)

        jornada = dias.sort_values(['Equipo', 'Fecha']).copy()
        jornada['jornada_eq'] = jornada.groupby('Equipo').cumcount()
        casos = casos.merge(jornada, on=['Equipo', 'Fecha'], how='left')
        casos = casos[casos['jornada_eq'] > 0]
        if len(casos) < 80:
            return (K_TITULARIDAD_POR_DEFECTO, PROB_TITULARIDAD_POR_DEFECTO)

        pj = np.where(casos['media_prev'] > 0,
                      (casos['pts_prev'] / casos['media_prev']).round(), 0)
        real = casos['jugo'].values

        # Señal de racha: qué hizo en la jornada anterior de su equipo. Hoy
        # aporta poco porque con dos jornadas dice casi lo mismo que la
        # proporción global; el peso se calibra, así que crecerá solo cuando
        # empiece a distinguir de verdad (un 60% de titularidad no significa lo
        # mismo si viene de jugar que si viene de chupar banquillo).
        casos = casos.sort_values(['Jugador', 'Fecha'])
        anterior = casos.groupby('Jugador')['jugo'].shift(1)
        hay_ant = anterior.notna().values
        ant = anterior.fillna(0).values

        mejor, mejor_brier = (K_TITULARIDAD_POR_DEFECTO, PROB_TITULARIDAD_POR_DEFECTO), None
        for k in (1.0, 2.0, 3.0, 4.0, 6.0):
            for base in (0.30, 0.40, 0.50, 0.60, 0.70):
                prob = np.clip((pj + k * base) / (casos['jornada_eq'].values + k), 0.05, 1.0)
                brier = float(np.mean((prob - real) ** 2))
                if mejor_brier is None or brier < mejor_brier:
                    mejor, mejor_brier = (float(k), float(base)), brier
        return mejor
    except Exception:
        return (K_TITULARIDAD_POR_DEFECTO, PROB_TITULARIDAD_POR_DEFECTO)


K_TITULARIDAD, PROB_TITULARIDAD_BASE = calibrar_titularidad(_huella_excel(resolver_excel_path()))


MEJORA_MINIMA_RECENCIA = 0.02   # 2% de mejora relativa para tomárselo en serio


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_recencia(huella=None):
    """(peso de la recencia, probabilidad si jugó la última, si no jugó).

    Quien jugó la jornada pasada repite el 77,8% de las veces y quien no, solo
    el 24,7%. Suena a señal potente, pero AHORA MISMO no aporta: con dos o tres
    jornadas disputadas, "jugó la última" y "ha jugado la mitad de los partidos"
    dicen casi lo mismo, y mezclarlas mejora el acierto un 0,8%, que es ruido.

    Donde separará de verdad es dentro de unos meses: un jugador puede llevar 10
    de 20 partidos y encadenar las cuatro últimas titularidades, y entonces la
    tasa global se queda vieja mientras la recencia lo ve.

    Por eso el peso NO se fija: se mide, y solo se usa si mejora al menos un 2%.
    Hoy sale 0 y el cálculo se queda como estaba; el día que la señal sea real,
    se enciende sola sin tocar nada."""
    try:
        hist = cargar_historico_completo(huella)
        if hist.empty:
            return (0.0, 0.75, 0.30)
        h = hist.sort_values(['Jugador', 'Fecha']).copy()
        h['pts_dia'] = h.groupby('Jugador')['Puntos'].diff()
        h['jugo'] = (h['pts_dia'].notna() & (h['pts_dia'] != 0)).astype(int)
        dias = h[h['jugo'] == 1][['Equipo', 'Fecha']].drop_duplicates().sort_values(['Equipo', 'Fecha'])
        if dias.empty:
            return (0.0, 0.75, 0.30)
        dias['je'] = dias.groupby('Equipo').cumcount()
        casos = h.merge(dias, on=['Equipo', 'Fecha'], how='inner').sort_values(['Jugador', 'Fecha'])
        casos['ant'] = casos.groupby('Jugador')['jugo'].shift(1)
        casos['acum'] = casos.groupby('Jugador')['jugo'].cumsum() - casos['jugo']
        d = casos[(casos['je'] > 0) & casos['ant'].notna()]
        if len(d) < 100:
            return (0.0, 0.75, 0.30)

        real = d['jugo'].values
        p_si = float(d[d['ant'] == 1]['jugo'].mean()) if (d['ant'] == 1).any() else 0.75
        p_no = float(d[d['ant'] == 0]['jugo'].mean()) if (d['ant'] == 0).any() else 0.30
        tasa = (d['acum'].values + K_TITULARIDAD * PROB_TITULARIDAD_BASE) / (d['je'].values + K_TITULARIDAD)
        recencia = np.where(d['ant'].values == 1, p_si, p_no)

        base = float(np.mean((tasa - real) ** 2))
        mejor_w, mejor_err = 0.0, base
        for w in (0.2, 0.4, 0.6, 0.8, 1.0):
            err = float(np.mean(((1 - w) * tasa + w * recencia - real) ** 2))
            if err < mejor_err:
                mejor_w, mejor_err = w, err
        # Solo se usa si la mejora es de verdad, no una décima de casualidad.
        if base <= 0 or (base - mejor_err) / base < MEJORA_MINIMA_RECENCIA:
            return (0.0, p_si, p_no)
        return (mejor_w, p_si, p_no)
    except Exception:
        return (0.0, 0.75, 0.30)


PESO_RECENCIA, PROB_SI_JUGO_ULTIMA, PROB_SI_NO_JUGO = calibrar_recencia(_huella_excel(resolver_excel_path()))


@st.cache_data(show_spinner=False)
def jugo_ultima_jornada(huella=None):
    """{jugador: si disputó la última jornada de su equipo}."""
    try:
        hist = cargar_historico_completo(huella)
        if hist.empty:
            return {}
        h = hist.sort_values(['Jugador', 'Fecha']).copy()
        h['pts_dia'] = h.groupby('Jugador')['Puntos'].diff()
        h['jugo'] = (h['pts_dia'].notna() & (h['pts_dia'] != 0)).astype(int)
        dias = h[h['jugo'] == 1][['Equipo', 'Fecha']].drop_duplicates()
        casos = h.merge(dias, on=['Equipo', 'Fecha'], how='inner')
        if casos.empty:
            return {}
        ultima = casos.sort_values('Fecha').groupby(['Jugador', 'Equipo']).tail(1)
        return {(str(f['Jugador']).strip(), str(f['Equipo']).strip()): int(f['jugo'])
                for _, f in ultima.iterrows()}
    except Exception:
        return {}


# --- 👤 QUIÉN JUEGA: LAS ÚLTIMAS JORNADAS Y EL PRECIO ---
# Para elegir un once, lo que más pesa es acertar quién juega: el que no sale
# hace cero, y ningún rival fácil lo arregla. La fórmula de siempre mira la
# proporción de partidos de la temporada y, desde hace poco, la última jornada.
#
# Medido el 20/09/2026 con cada jugador en cada partido de su equipo (3.107
# casos, incluidos los que no jugaron, que la tabla de actuaciones no ve),
# ajustando con las jornadas 1-3 y juzgando con la 4 en adelante:
#     solo la proporción de la temporada     error 0,179
#     la fórmula actual (con la última)      error 0,168
#     + las tres últimas jornadas y precio   error 0,158   ← un 6% menos
# El precio pesa mucho: al barato lo rotan. Y en puntos, el once que sale con
# esto ordena bien el 70,9% de las parejas de la misma posición (antes 70,3%)
# y sus elegidos puntúan 4,95 frente a 4,89.
#
# Se probaron también la fuerza del equipo y la forma reciente del jugador para
# la parte de "cuánto puntúa cuando juega": ninguna de las dos mejora hoy nada,
# así que no entran.
#
# Nada de esto va fijo: el modelo se reentrena con los datos de cada día y se
# compara solo contra la fórmula de siempre. Si deja de mejorarla al menos un
# 2%, se apaga y vuelve la de siempre.
MEJORA_MINIMA_TITULARIDAD = 0.02


@st.cache_data(show_spinner=False, persist="disk")
def partidos_de_cada_jugador(huella=None):
    """Cada jugador en cada partido ya jugado de su equipo, con lo que se sabía
    de él la víspera y si lo disputó. Y sus tres últimas jornadas.

    'Lo disputó' sale de que le suba el número de partidos jugados, no de que
    le cambien los puntos: así un partido de cero puntos cuenta como jugado.
    Comprobado: los puntos partido a partido suman el total de Biwenger en el
    96% de los jugadores.

    Devuelve (tabla, {(jugador, equipo): (última, penúltima, antepenúltima)})."""
    vacio = (pd.DataFrame(columns=['je', 'jugo', 'pj_antes', 'valor_antes', 'ant1', 'ant2', 'ant3']), {})
    try:
        hist = cargar_historico_completo(huella)
        cal = df_cal_global
        if hist is None or hist.empty or cal is None or cal.empty:
            return vacio
        hist = hist.dropna(subset=['Fecha', 'Jugador']).copy()
        hist['Jugador'] = hist['Jugador'].astype(str).str.strip()
        hist['Equipo'] = hist['Equipo'].astype(str).str.strip()
        hist = hist.sort_values('Fecha')
        terminados = cal[cal['Estado'] == 'Finalizado'].dropna(subset=['Fecha'])
        fechas_de = {}
        for equipo in set(cal['Local']) | set(cal['Visitante']):
            fechas_de[equipo] = sorted(cal[(cal['Local'] == equipo) | (cal['Visitante'] == equipo)]
                                       ['Fecha'].dropna().unique())
        partidos_de = {equipo: terminados[(terminados['Local'] == equipo) | (terminados['Visitante'] == equipo)]
                       .sort_values('Fecha')['Fecha'].values
                       for equipo in fechas_de}

        filas, ultimos = [], {}
        for jugador, serie in hist.groupby('Jugador'):
            if serie['Fecha'].duplicated().any():      # dos jugadores con el mismo nombre
                continue
            fechas = serie['Fecha'].values
            puntos = pd.to_numeric(serie['Puntos'], errors='coerce').values
            medias = pd.to_numeric(serie['Media Puntos'], errors='coerce').values
            valores = pd.to_numeric(serie['Valor Actual (€)'], errors='coerce').values
            equipos = serie['Equipo'].values
            historial = []
            for equipo in pd.unique(equipos):
                propios = equipos == equipo
                siguientes = fechas_de.get(equipo, [])
                for je, dia in enumerate(partidos_de.get(equipo, [])):
                    posterior = [f for f in siguientes if f > dia]
                    limite = posterior[0] if posterior else None
                    antes = np.where((fechas < dia) & propios)[0]
                    despues = np.where((fechas >= dia) & propios
                                       & ((fechas < limite) if limite is not None else True))[0]
                    if not len(antes) or not len(despues):
                        continue
                    i, j = antes[-1], despues[-1]
                    if pd.isna(puntos[i]) or pd.isna(puntos[j]):
                        continue
                    pj_i = _partidos_jugados_dia(puntos[i], medias[i])
                    pj_j = _partidos_jugados_dia(puntos[j], medias[j])
                    jugo = (pj_j > pj_i) if (pj_i is not None and pj_j is not None) else (puntos[j] != puntos[i])
                    filas.append((je, int(jugo), pj_i or 0, valores[i],
                                  historial[-1] if len(historial) >= 1 else np.nan,
                                  historial[-2] if len(historial) >= 2 else np.nan,
                                  historial[-3] if len(historial) >= 3 else np.nan))
                    historial.append(int(jugo))
                if historial:
                    ultimos[(jugador, equipo)] = tuple(reversed(historial[-3:]))
        tabla = pd.DataFrame(filas, columns=['je', 'jugo', 'pj_antes', 'valor_antes', 'ant1', 'ant2', 'ant3'])
        return tabla, ultimos
    except Exception:
        return vacio


def _partidos_jugados_dia(puntos, media):
    """Partidos jugados que se deducen de los puntos y la media de un día."""
    if media is None or pd.isna(media) or abs(float(media)) < 1e-9:
        return 0 if (puntos is None or pd.isna(puntos) or float(puntos) == 0) else None
    return int(round(float(puntos) / float(media)))


def _variables_titularidad(pj, partidos_equipo, ant1, ant2, ant3, valor):
    """Las cinco variables del modelo: proporción de partidos jugados (encogida
    un poco hacia la mitad), si jugó cada una de las tres últimas jornadas de
    su equipo (0,5 si aún no hay tantas) y el precio en escala logarítmica."""
    relleno = lambda v: np.where(pd.isna(v), 0.5, v)
    return np.column_stack([
        (np.asarray(pj, dtype=float) + 1.0) / (np.asarray(partidos_equipo, dtype=float) + 2.0),
        relleno(np.asarray(ant1, dtype=float)), relleno(np.asarray(ant2, dtype=float)),
        relleno(np.asarray(ant3, dtype=float)),
        np.log1p(np.nan_to_num(np.asarray(valor, dtype=float), nan=1e6) / 1e6),
    ])


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_titularidad_reciente(huella=None):
    """(intercepto, pesos, error antes, error ahora) del modelo de quién juega,
    o None si no mejora a la fórmula de siempre en partidos que no ha visto."""
    try:
        from sklearn.linear_model import LogisticRegression
        tabla, _ = partidos_de_cada_jugador(huella)
        d = tabla[tabla['je'] >= 1]
        if len(d) < 400 or d['je'].nunique() < 4:
            return None
        X = _variables_titularidad(d['pj_antes'], d['je'], d['ant1'], d['ant2'], d['ant3'], d['valor_antes'])
        y = d['jugo'].values
        # Se entrena con las primeras jornadas y se juzga con las siguientes:
        # un modelo que acierta lo que ya ha visto no demuestra nada.
        corte = float(np.median(d['je']))
        entreno, prueba = d['je'].values <= corte, d['je'].values > corte
        if entreno.sum() < 200 or prueba.sum() < 150:
            return None
        modelo = LogisticRegression(max_iter=500).fit(X[entreno], y[entreno])
        error_nuevo = float(np.mean((modelo.predict_proba(X[prueba])[:, 1] - y[prueba]) ** 2))

        tasa = (d['pj_antes'].values + K_TITULARIDAD * PROB_TITULARIDAD_BASE) / (d['je'].values + K_TITULARIDAD)
        if PESO_RECENCIA > 0:
            ultima = np.where(d['ant1'].values == 1, PROB_SI_JUGO_ULTIMA, PROB_SI_NO_JUGO)
            tasa = np.where(pd.notna(d['ant1'].values), (1 - PESO_RECENCIA) * tasa + PESO_RECENCIA * ultima, tasa)
        error_viejo = float(np.mean((np.clip(tasa, 0.05, 1.0)[prueba] - y[prueba]) ** 2))
        if error_viejo <= 0 or (error_viejo - error_nuevo) / error_viejo < MEJORA_MINIMA_TITULARIDAD:
            return None
        final = LogisticRegression(max_iter=500).fit(X, y)
        return (float(final.intercept_[0]), [float(c) for c in final.coef_[0]],
                round(error_viejo, 4), round(error_nuevo, 4))
    except Exception:
        return None


MODELO_TITULARIDAD = calibrar_titularidad_reciente(_huella_excel(resolver_excel_path()))
# Las tres últimas jornadas de cada jugador, cargadas una vez: la probabilidad
# se pide miles de veces al montar los onces de la liga.
ULTIMAS_JORNADAS = partidos_de_cada_jugador(_huella_excel(resolver_excel_path()))[1] if MODELO_TITULARIDAD else {}


def _probabilidad_reciente(player):
    intercepto, pesos = MODELO_TITULARIDAD[0], MODELO_TITULARIDAD[1]
    clave = (str(player.get('Jugador') or '').strip(), str(player.get('Equipo') or '').strip())
    previas = ULTIMAS_JORNADAS.get(clave, ())
    ant = [previas[i] if len(previas) > i else np.nan for i in range(3)]
    x = _variables_titularidad([_a_float(player.get('PJ'), 0.0) or 0.0],
                               [partidos_equipos_global.get(player.get('Equipo'), 0) or 0],
                               [ant[0]], [ant[1]], [ant[2]],
                               [_a_float(player.get('Valor Actual (€)'), 0.0) or 0.0])[0]
    z = intercepto + float(np.dot(pesos, x))
    return min(1.0, max(0.05, 1.0 / (1.0 + np.exp(-z))))


def probabilidad_de_jugar(player):
    """Con qué probabilidad disputa su próximo partido. Devuelve entre 0,05 y 1."""
    # Si el modelo de las últimas jornadas ha demostrado acertar más (ver
    # calibrar_titularidad_reciente), manda él. Si no, la fórmula de siempre.
    if MODELO_TITULARIDAD:
        return _probabilidad_reciente(player)
    # Sin caso especial para los equipos que aún no han debutado: la propia
    # fórmula les da la probabilidad de partida (0,70), que queda POR DEBAJO de
    # quien sí jugó su partido (0,775) y por encima de quien se lo perdió
    # (0,525). Devolverles un 1,0 haría que no haber jugado puntuara mejor que
    # haber jugado, que es justo el artefacto que ya arreglamos en la dificultad.
    partidos_equipo = partidos_equipos_global.get(player.get('Equipo'), 0) or 0
    pj = _a_float(player.get('PJ'), 0.0) or 0.0
    tasa = ((pj + K_TITULARIDAD * PROB_TITULARIDAD_BASE)
            / (partidos_equipo + K_TITULARIDAD))

    # Si haber jugado la última jornada demuestra aportar, se mezcla. Hoy el
    # calibrador le da peso CERO —con dos jornadas dice casi lo mismo que la
    # proporción global— así que esto no hace nada; se activará solo cuando las
    # dos señales empiecen a discrepar, que es cuando un 60% de titularidad ya
    # no significa lo mismo viniendo de jugar que de chupar banquillo.
    if PESO_RECENCIA > 0:
        # La clave del registro es (jugador, equipo), no solo el nombre: con un
        # texto suelto nunca casaba y la mezcla no se habría aplicado jamás.
        clave = (str(player.get('Jugador') or '').strip(),
                 str(player.get('Equipo') or '').strip())
        ultima = jugo_ultima_jornada(_huella_excel(resolver_excel_path())).get(clave)
        if ultima is not None:
            reciente = PROB_SI_JUGO_ULTIMA if ultima else PROB_SI_NO_JUGO
            tasa = (1 - PESO_RECENCIA) * tasa + PESO_RECENCIA * reciente

    return min(1.0, max(0.05, tasa))


def puntos_esperados_jugador(player, fixture=None):
    """Puntos que se espera que saque el jugador en su próximo partido.
    Media ajustada por muestra × dificultad del rival × racha del equipo.

    Con `fixture` (un partido con 'dificultad' y 'es_casa', como los que da
    tramo_de_calendario) evalúa ese partido en vez del próximo. Es lo que
    permite comparar jugadores en las próximas jornadas y no solo en la que
    viene; sin él, todo sigue exactamente igual que antes."""
    equipo = player.get('Equipo')
    if fixture is None:
        fixture = get_fixture_equipo(equipo)
    es_casa = fixture['es_casa'] if fixture else True
    media, peso_split = media_esperada_jugador(
        player, es_casa=es_casa, ratio_casa=get_ratio_casa_equipo(equipo))

    # Ventaja de local genérica, aplicada SOLO en la medida en que el jugador no
    # tenga datos propios que la midan. Sin esto, a principio de temporada jugar
    # en casa o fuera daba exactamente igual: factor_dificultad descuenta el
    # recargo de localía a propósito (para no contarlo dos veces con la media
    # casa/fuera del jugador), pero cuando esa media aún no existe no lo cuenta
    # nadie. Conforme el jugador acumula partidos, esto se desvanece solo y
    # manda su propio rendimiento.
    localia = 1 + (1 - peso_split) * (VENTAJA_LOCAL if es_casa else -VENTAJA_LOCAL)

    # 👤 Y por último, lo que faltaba: la media es "puntos por partido jugado",
    # así que hay que multiplicarla por la probabilidad de que juegue. Sin esto,
    # el motor daba por hecho que todos son titulares fijos.
    bruto = (media * probabilidad_de_jugar(player) * localia
             * factor_dificultad(fixture) * factor_racha(get_racha_equipo(equipo)))
    # Encogimiento hacia la media de la liga: multiplicar cinco factores en
    # cadena exagera las diferencias. No altera el ORDEN (y por tanto ni el once
    # ideal ni las cartas iluminadas cambian), solo devuelve los números a una
    # escala creíble.
    return max(0.0, MEDIA_LIGA_JORNADA + ESCALA_MOTOR * (bruto - MEDIA_LIGA_JORNADA))

# 🗓️ Diccionario {equipo: dificultad 0-100} reutilizando exactamente la misma
# lógica que ya usa la pestaña de Análisis de Rivales (dificultad_fixture): en
# cuanto haya partidos jugados usa la clasificación real; mientras tanto (como
# ahora, con la liga sin empezar) recurre al valor de mercado agregado de la
# plantilla rival como proxy de su fuerza, y si tampoco hay eso, se queda en 50
# (neutro). Se calcula UNA vez para todos los equipos, para no recalcularlo
# partido a partido en cada fila de entrenamiento (sería carísimo con RF).
mapa_dificultad_calendario_global = {
    eq: ((get_fixture_equipo(eq) or {}).get('dificultad', 50.0))
    for eq in (db['mercado']['Equipo'].dropna().unique() if 'mercado' in db and 'Equipo' in db['mercado'].columns else [])
}


# --- 🥈 PUJAS PERDIDAS → EVENTOS DE PUJA ---
# --- ⭐ CUÁNDO SE ILUMINA UNA CARTA ---
# La regla anterior era `media >= 7 o valor >= 10.000.000`, y tenía tres taras:
#
#  · umbrales absolutos: 10 M€ era mucho en pretemporada y será poco en enero,
#    igual que un 7,00 de media significa cosas distintas en agosto y en mayo;
#  · el `o` hacía brillar a los caros sin mirar si rinden — de las 34 cartas que
#    se iluminaban con sus datos, 19 lo hacían SOLO por precio;
#  · ignoraba la muestra: 15 de esas 34 brillaban por una media alta de UN
#    partido (Roberto Fernández, 18,00 de un día).
#
# La regla nueva: una carta brilla si el jugador está entre el 10% mejor DE SU
# POSICIÓN, medido con el mismo motor que elige el once (media corregida por
# tamaño de muestra, precio como respaldo mientras no haya partidos, dificultad
# del próximo rival y racha del equipo).
#
# Tres propiedades que la hacen distinta de un umbral a pelo:
#  · es relativa a la liga, así que el brillo significa lo mismo en agosto que
#    en mayo y no se descontrola cuando suba el mercado;
#  · es relativa a la POSICIÓN, porque un portero y un delantero no puntúan en
#    la misma escala: si no, no brillaría ni un portero;
#  · el motor ya encoge las medias con poca muestra hacia el nivel que sugiere
#    el precio, así que un 18,00 de un partido sube, pero no dispara.
#
# Y los lesionados no brillan: ahora mismo no son una joya, son un problema.
PERCENTIL_ESTRELLA = 0.90
# Sin margen de tolerancia en la frontera: se probó y CUESTA acierto. Con un 5%
# los elegidos rinden un +49% sobre el resto en vez de un +60%, y hasta con un
# 1,5% cae a +51%. Los que están justo por debajo del corte son de verdad peores,
# así que ensanchar solo mete ruido.
TOLERANCIA_ESTRELLA = 0.0
MIN_POR_POSICION_ESTRELLA = 8


# Valores de partida, solo por si no hay datos para medir: los de la fórmula
# anterior (precio + fuerza del equipo, sin la media del jugador).
PESO_FUERZA_EQUIPO_POR_DEFECTO = 0.5
K_CALIDAD_POR_DEFECTO = None          # None = la media propia no entra

# Rejilla que se prueba. K es cuántos partidos "pesa" el precio frente a la
# media real del jugador; None es no usar la media en absoluto.
_K_CALIDAD_CANDIDATOS = (None, 3, 6, 10, 15, 20, 30, 40)
_PESO_FUERZA_CANDIDATOS = (0.0, 0.25, 0.5)


@st.cache_data(show_spinner=False, persist="disk")
def calibrar_indice_calidad(huella=None):
    """Qué mezcla de precio, media propia y fuerza del equipo acierta mejor a
    quién va a rendir, medido sin mirar el futuro.

    Para varias fechas de corte se toma la foto del Histórico de ESE día (precio,
    media, partidos y puntos de cada club tal como estaban) y se juzga contra lo
    que cada jugador hizo DESPUÉS, con al menos dos actuaciones. Se elige la
    combinación cuyo 10% de arriba de cada posición rinde más sobre el resto,
    entre las que conservan casi toda la capacidad de ordenar (correlación de
    rangos), igual que se hace con el exponente del precio.

    Medido el 24/09/2026 con 7 jornadas (1.140 casos en 4 cortes):
        precio + fuerza, sin media (lo de antes)   ->  +47%, rangos +0,259
        solo el precio                             ->  +48%, rangos +0,304
        precio + media (K=15), sin fuerza          ->  +52%, rangos +0,309
    La fuerza del equipo, tomada de la fecha de corte, ya no aporta: el estudio
    de agosto la usaba con los puntos de HOY, que incluyen lo que se juzgaba, y
    con esa fuga la correlación sube sola de 0,30 a 0,36.

    Devuelve (K, peso_fuerza, texto con la medición)."""
    defecto = (K_CALIDAD_POR_DEFECTO, PESO_FUERZA_EQUIPO_POR_DEFECTO, "sin datos suficientes")
    try:
        hist = cargar_historico_completo(huella)
        act = tabla_actuaciones(huella)
        if hist.empty or act.empty or len(act) < 300:
            return defecto
        act = act.copy()
        act['fecha'] = pd.to_datetime(act['fecha'])
        hist = hist.copy()
        hist['Fecha'] = pd.to_datetime(hist['Fecha'])
        primera, ultima = act['fecha'].min(), act['fecha'].max()
        # Cortes semanales dejando al menos una semana de muestra antes y
        # cinco días de juez después.
        cortes = []
        corte = primera + pd.Timedelta(days=9)
        while corte <= ultima - pd.Timedelta(days=5):
            cortes.append(corte)
            corte += pd.Timedelta(days=7)
        if not cortes:
            return defecto

        bloques = []      # por corte y posición: arrays para evaluar la rejilla
        for corte in cortes:
            dia = hist.loc[hist['Fecha'] <= corte, 'Fecha'].max()
            if pd.isna(dia):
                continue
            foto = hist[hist['Fecha'] == dia].copy()
            foto['Media Puntos'] = pd.to_numeric(foto['Media Puntos'], errors='coerce')
            foto['Puntos'] = pd.to_numeric(foto['Puntos'], errors='coerce').fillna(0)
            foto['Valor Actual (€)'] = pd.to_numeric(foto['Valor Actual (€)'], errors='coerce')
            media = foto['Media Puntos'].fillna(0)
            foto['PJ'] = np.where(media != 0, (foto['Puntos'] / media.replace(0, np.nan)).round(), 0)
            foto['PJ'] = pd.to_numeric(foto['PJ'], errors='coerce').fillna(0).clip(lower=0)
            futuro = act[act['fecha'] > corte].groupby('jugador')['pts'].agg(['mean', 'count'])
            futuro = futuro[futuro['count'] >= 2]
            foto = foto[foto['Jugador'].isin(futuro.index) & (foto['Valor Actual (€)'] > 0)]
            if len(foto) < 60:
                continue
            prior = construir_prior_media(foto)
            fuerza = foto.groupby('Equipo')['Puntos'].sum().to_dict()
            ref = float(np.median([v for v in fuerza.values() if v] or [0])) or 1.0
            foto['_prior'] = [prior(f) for _, f in foto.iterrows()]
            foto['_rel'] = foto['Equipo'].map(fuerza).fillna(0) / ref - 1.0
            foto['_fut'] = foto['Jugador'].map(futuro['mean'])
            foto['_pos'] = foto['Posición'].astype(str).str.split('/').str[0].str.strip()
            for _, g in foto.groupby('_pos'):
                if len(g) >= 20:
                    bloques.append((g['_prior'].to_numpy(float), g['Media Puntos'].to_numpy(float),
                                    g['PJ'].to_numpy(float), g['_rel'].to_numpy(float),
                                    g['_fut'].to_numpy(float)))
        casos = sum(len(b[0]) for b in bloques)
        if casos < 300:
            return defecto

        resultados = []
        for k in _K_CALIDAD_CANDIDATOS:
            for w in _PESO_FUERZA_CANDIDATOS:
                suma_lift, suma_rho, peso_total = 0.0, 0.0, 0
                for prior_v, media_v, pj_v, rel_v, fut_v in bloques:
                    base = prior_v.copy()
                    if k is not None:
                        con = (pj_v > 0) & ~np.isnan(media_v)
                        base[con] = (pj_v[con] * media_v[con] + k * prior_v[con]) / (pj_v[con] + k)
                    s = base * np.clip(1.0 + w * rel_v, 0.5, 1.6)
                    umbral = np.quantile(s, PERCENTIL_ESTRELLA)
                    arriba, resto = fut_v[s >= umbral], fut_v[s < umbral]
                    if not len(arriba) or not len(resto) or resto.mean() == 0:
                        continue
                    n = len(s)
                    suma_lift += n * (arriba.mean() / resto.mean() - 1.0)
                    suma_rho += n * pd.Series(s).corr(pd.Series(fut_v), method='spearman')
                    peso_total += n
                if peso_total:
                    resultados.append((k, w, suma_lift / peso_total, suma_rho / peso_total))
        if not resultados:
            return defecto
        mejor_rho = max(r[3] for r in resultados)
        validos = [r for r in resultados if r[3] >= 0.97 * mejor_rho]
        k, w, lift, rho = max(validos, key=lambda r: r[2])
        antes = next((r for r in resultados if r[0] is None and r[1] == 0.5), None)
        texto = (f"{casos} casos en {len(cortes)} cortes: el 10% de arriba rinde {lift:+.0%} "
                 f"sobre el resto (rangos {rho:+.3f})")
        if antes:
            texto += f"; con la fórmula anterior, {antes[2]:+.0%} ({antes[3]:+.3f})"
        return k, w, texto
    except Exception:
        return defecto


K_CALIDAD, PESO_FUERZA_EQUIPO, MEDICION_CALIDAD = calibrar_indice_calidad(
    _huella_excel(resolver_excel_path()))


def indice_calidad_jugador(player):
    """Cuánto de bueno es un jugador, medido contra lo que rinden de verdad.

    Es lo que decide qué cartas se iluminan y el orden "Calidad del jugador" del
    Mercado. Tres ingredientes, y cuánto pesa cada uno NO está puesto a mano: lo
    mide calibrar_indice_calidad() contra lo que cada jugador hizo después.

     · EL PRECIO, siempre: es lo que mejor predice con poca muestra.
     · SU MEDIA, encogida hacia lo que dice el precio según los partidos que
       lleve (K_CALIDAD). Con 2-3 jornadas era ruido y se dejó fuera; con 7 ya
       aporta. Antes no había forma de que volviera a entrar sola.
     · LA FUERZA DE SU EQUIPO, como multiplicador suave. Hoy pesa 0: medida sin
       fuga (con los puntos del club EN la fecha de corte), no aporta.

    Y aquí NO entra nada del próximo partido: ni rival, ni racha, ni si juega
    en casa. Eso convertía el brillo en algo que parpadeaba cada semana — De la
    Fuente se iluminaba o no según dónde jugara el Levante el domingo.
    """
    valor = _a_float(player.get('Valor Actual (€)'), 0.0) or 0.0
    if valor <= 0:
        return 0.0
    base = prior_media_liga(player)

    if K_CALIDAD is not None:
        pj = _a_float(player.get('PJ'), 0.0) or 0.0
        media = _a_float(player.get('Media Puntos'), None)
        if media is not None and pj > 0:
            base = (pj * media + K_CALIDAD * base) / (pj + K_CALIDAD)

    if PESO_FUERZA_EQUIPO:
        fuerza = puntos_equipos_global.get(player.get('Equipo'), 0.0) or 0.0
        referencia = _referencia_fuerza_equipos()
        if referencia > 0:
            factor = 1.0 + PESO_FUERZA_EQUIPO * ((fuerza / referencia) - 1.0)
            base *= min(1.6, max(0.5, factor))
    return max(0.0, base)


def indice_brillo_jugador(player):
    """Lo que decide el brillo de la carta: su calidad por la probabilidad de
    que juegue.

    Medido el 24/09/2026 contra lo que cada jugador hizo después (jornadas 3 a
    6 como corte, juez: sus puntos por partido de su equipo en lo que quedaba):
      · calidad sola:              rangos +0,517, el 10% de arriba rinde +96%
      · calidad × prob. de jugar:  rangos +0,552, el 10% de arriba rinde +94%
    Ordena bastante mejor y elige igual de bien. En agosto, con dos jornadas,
    la probabilidad de jugar era ruido y restaba; ya no.

    También se probó meter los puntos que lleva (el "6º de 66 delanteros"): a
    más peso de esos puntos, peor predice (con la mitad, +87%; solo puntos,
    +89% y rangos +0,452). Lo que ya ha pasado cuenta menos de lo que parece."""
    return indice_calidad_jugador(player) * probabilidad_de_jugar(player)


@st.cache_data(show_spinner=False)
def _referencia_fuerza_equipos(huella=None):
    """Puntos fantasy del equipo medio, para poder comparar."""
    valores = [v for v in puntos_equipos_global.values() if v]
    return float(np.median(valores)) if valores else 0.0


@st.cache_data(show_spinner=False)
def umbrales_estrella(huella=None):
    """Nivel de puntos esperados a partir del cual una carta se ilumina, por
    posición. Se calcula una sola vez (228 ms para los ~520 del mercado) en vez
    de recorrer la liga por cada carta pintada."""
    mercado = db.get('mercado')
    if mercado is None or mercado.empty:
        return {}
    aux = mercado.dropna(subset=['Jugador']).copy()
    aux['_x'] = [indice_brillo_jugador(fila) for _, fila in aux.iterrows()]
    aux['_pos'] = aux['Posición'].astype(str).str.split('/').str[0].str.strip()

    umbrales = {'_global': float(aux['_x'].quantile(PERCENTIL_ESTRELLA))}
    for pos, grupo in aux.groupby('_pos'):
        if len(grupo) >= MIN_POR_POSICION_ESTRELLA:
            umbrales[pos] = float(grupo['_x'].quantile(PERCENTIL_ESTRELLA))
    return umbrales


def es_carta_estrella(player):
    """¿Merece esta carta el borde dorado?"""
    if str(player.get('Lesion', 'no')).strip().lower() == 'si':
        return False
    umbrales = umbrales_estrella(_huella_excel(resolver_excel_path()))
    if not umbrales:
        return False
    pos = str(player.get('Posición', '')).split('/')[0].strip()
    umbral = umbrales.get(pos, umbrales.get('_global'))
    if umbral is None:
        return False
    # 🎚️ Margen de tolerancia en la frontera. Con un corte a secas pasaba esto:
    # Catena con 3,46 se iluminaba y De la Fuente con 3,42 no, cuatro milésimas
    # de diferencia. Dos jugadores prácticamente iguales no pueden quedar uno
    # dentro y otro fuera; se admite todo lo que esté a menos de un 5% del
    # corte, que es la precisión real que tiene esta medida.
    return indice_brillo_jugador(player) >= umbral * (1 - TOLERANCIA_ESTRELLA)


# --- 💸 QUÉ VENDER PARA CUBRIR UNA DEUDA O PAGAR UN FICHAJE ---
# Revisado el 24/09/2026 porque te proponía vender a Kang-in Lee (titular, 9,4
# M€) antes que a cuatro suplentes. Dos fallos:
#   · cada jugador costaba sus puntos esperados como si todos fueran titulares,
#     así que vender a un suplente "dolía" casi lo mismo que a un titular;
#   · solo se miraban combinaciones de hasta 3 jugadores, y para 10,9 M€ con tus
#     suplentes hacían falta cuatro o cinco.
# Ahora el coste de una venta es lo que pierde TU MEJOR ONCE sin esos jugadores
# (más un poco del banquillo, que es lo que te salva de una lesión), con la
# calidad de cada uno (la misma del brillo de las cartas), y se prueban hasta 6
# ventas. Vender por encima de lo que debes no se castiga casi: a la máquina se
# vende al valor de mercado y ese dinero sigue siendo tuyo.
#
# Medido reconstruyendo las plantillas de las jornadas 3 a 5 con deudas de 3, 8
# y 12 M€ (75 casos) y contando los puntos REALES que dejó de hacer el once en
# las jornadas siguientes: la forma anterior perdía 6,8 puntos de media; esta,
# 4,2 (un 38% menos). Sin contar el banquillo, 5,5.
PESO_BANQUILLO_VENTAS = 0.10
EXCESO_VENTAS_POR_MILLON = 0.02
_SLOT_POSICION = {'Portero': 0, 'Defensa': 1, 'Centrocampista': 2, 'Delantero': 3}


def _elegibilidad(filas):
    """Matriz jugadores × (POR, DEF, MED, DEL): en qué puestos puede jugar cada uno."""
    E = np.zeros((len(filas), 4), dtype=bool)
    for i, fila in enumerate(filas):
        for pos in str(fila.get('Posición') or '').split('/'):
            k = _SLOT_POSICION.get(pos.strip())
            if k is not None:
                E[i, k] = True
    return E


def _once_optimo(valores, E, activos):
    """(calidad del mejor once + parte del banquillo, {índice: puesto}) con los
    jugadores `activos`. Puesto: 0 POR, 1 DEF, 2 MED, 3 DEL. Resuelve cada
    formación como un problema de asignación (-4 por hueco, como en Biwenger)."""
    from scipy.optimize import linear_sum_assignment
    idx = np.flatnonzero(activos)
    if not len(idx):
        return -44.0, {}
    v, e = valores[idx], E[idx]
    mejor, mejor_filas, mejor_huecos = -1e9, None, None
    for huecos in _HUECOS_FORMACIONES:
        C = np.where(e[:, huecos], -(100.0 + v[:, None]), 1e6)
        filas_a, cols_a = linear_sum_assignment(C)
        validos = C[filas_a, cols_a] < 1e5
        total = float(v[filas_a[validos]].sum()) - 4.0 * (11 - int(validos.sum()))
        if total > mejor:
            mejor, mejor_filas, mejor_huecos = total, filas_a[validos], huecos[cols_a[validos]]
    banquillo = np.delete(v, mejor_filas)
    once = {int(idx[fa]): int(h) for fa, h in zip(mejor_filas, mejor_huecos)}
    return mejor + PESO_BANQUILLO_VENTAS * float(np.sort(banquillo)[::-1][:3].sum()), once


_HUECOS_FORMACIONES = [np.array([0] + [1] * d + [2] * m + [3] * f) for d, m, f in
                       [(3, 4, 3), (3, 5, 2), (4, 3, 3), (4, 4, 2), (4, 5, 1), (5, 3, 2), (5, 4, 1)]]


def _valor_plantilla_ventas(valores, E, activos):
    """Calidad del mejor once que se puede alinear con los jugadores `activos`
    más una parte de los tres mejores del banquillo."""
    return _once_optimo(valores, E, activos)[0]


def _mejores_ventas(completa, vendible, deuda, max_ventas=6, max_opciones=3):
    """Las combinaciones de ventas que cubren `deuda` quitando menos calidad.

    `completa`: lista de filas de la plantilla (incluidos los que no se pueden
    vender, que cuentan para el once). `vendible`: máscara de los que sí."""
    if deuda <= 0 or not completa:
        return []
    valores_mercado = np.array([_a_float(f.get('Valor Actual (€)'), 0.0) or 0.0 for f in completa])
    calidad = np.array([indice_brillo_jugador(f) for f in completa])
    E = _elegibilidad(completa)
    todos = np.ones(len(completa), dtype=bool)
    base = _valor_plantilla_ventas(calidad, E, todos)
    candidatos = [i for i in range(len(completa)) if vendible[i] and valores_mercado[i] > 0]
    maximo = min(max_ventas, len(completa) - MIN_PLANTILLA_TRAS_VENDER)
    precio = [float(x) for x in valores_mercado]      # sumar floats es mucho más rápido que numpy aquí
    opciones = []
    for n in range(1, maximo + 1):
        for combo in itertools.combinations(candidatos, n):
            cobros = [precio[i] for i in combo]
            ingreso = sum(cobros)
            if ingreso < deuda:
                continue
            # Solo combinaciones mínimas: si quitando la venta más barata sigue
            # llegando, esa venta sobra.
            if ingreso - min(cobros) >= deuda:
                continue
            activos = todos.copy()
            activos[list(combo)] = False
            perdida = base - _valor_plantilla_ventas(calidad, E, activos)
            exceso = ingreso - deuda
            opciones.append({
                'jugadores': [completa[i] for i in combo],
                'ingreso': ingreso,
                'exceso': exceso,
                'coste': perdida + EXCESO_VENTAS_POR_MILLON * exceso / 1e6,
            })
    opciones.sort(key=lambda o: o['coste'])
    return opciones[:max_opciones]


def _texto_esperas_venta(jugadores, persona):
    """' Kang-in Lee no se puede vender hasta el 30/09.' si alguno de la venta
    aún tiene candado (pero se libera antes de la jornada)."""
    esperas = [(f['Jugador'], fecha_desbloqueo(f['Jugador'], persona)) for f in jugadores]
    esperas = [(j, d) for j, d in esperas if d]
    if not esperas:
        return ""
    return " " + "; ".join(f"{j} no se puede vender hasta el {d:%d/%m}" for j, d in esperas) + "."


def buscar_ventas_para_deuda(plantilla, deuda, max_jugadores=6, max_opciones=3):
    """Las mejores ventas para cubrir `deuda` con los jugadores de `plantilla`
    (los que se pueden vender). El resto de su plantilla, aunque tenga candado,
    cuenta para ver qué once le queda."""
    if plantilla is None or plantilla.empty or deuda <= 0:
        return []
    vendibles = plantilla.to_dict('records')
    completa, vendible = list(vendibles), [True] * len(vendibles)
    if 'Participante' in plantilla.columns and plantilla['Participante'].notna().any():
        persona = plantilla['Participante'].dropna().iloc[0]
        claves = {(str(f.get('Jugador')).strip(), str(f.get('Equipo')).strip()) for f in vendibles}
        for _, fila in db['plantillas'][db['plantillas']['Participante'] == persona].iterrows():
            if (str(fila.get('Jugador')).strip(), str(fila.get('Equipo')).strip()) not in claves:
                completa.append(fila.to_dict())
                vendible.append(False)
    return _mejores_ventas(completa, vendible, deuda, max_jugadores, max_opciones)


def construir_eventos_puja(contabilidad):
    compras = contabilidad[contabilidad['Tipo de Operación'] == 'Compra'].copy()
    if compras.empty:
        return compras

    cols_perdedores = [(f'Manager {i}', f'Subasta perdida {i}') for i in range(1, 10)]
    tiene_cols_perdidas = all(c[0] in contabilidad.columns and c[1] in contabilidad.columns for c in cols_perdedores)

    eventos = []
    for _, fila in compras.iterrows():
        valor_mercado = fila['Valor Mercado (€)']
        jugador_nombre = fila.get('Jugador')
        equipo_jugador = fila.get('Equipo')
        eventos.append({
            'Jugador': jugador_nombre,
            'Persona': fila['Persona'], 'Posición': fila.get('Posición'), 'Equipo': equipo_jugador,
            'Valor Mercado (€)': valor_mercado, 'Importe (€)': fila['Importe (€)'],
            'Gano_Puja': 1
        })
        if tiene_cols_perdidas and pd.notna(valor_mercado) and valor_mercado > 0:
            for col_mgr, col_importe in cols_perdedores:
                mgr = fila.get(col_mgr)
                importe_perdido = fila.get(col_importe)
                if pd.notna(mgr) and str(mgr).strip() != '' and pd.notna(importe_perdido):
                    eventos.append({
                        'Jugador': jugador_nombre,
                        'Persona': mgr, 'Posición': fila.get('Posición'), 'Equipo': equipo_jugador,
                        'Valor Mercado (€)': valor_mercado, 'Importe (€)': importe_perdido,
                        'Gano_Puja': 0
                    })

    return pd.DataFrame(eventos)


# --- 🤖 ENTRENAMIENTO DE IA HÍBRIDA 2.0 (AVANZADO) ---
# Lista única de features, compartida por entrenamiento, backtesting y predicción,
# para que las tres nunca puedan desincronizarse entre sí (antes cada función
# mantenía su propia copia de la lista).
# 🗑️ 'Índice Fichajes (usado en predicción) (€)' se ha quitado a propósito: es
# la MISMA columna que 'Sobrepuja Media Personal (€)' duplicada con otro nombre
# en el Excel (valores idénticos fila a fila). Meter las dos no aporta información
# nueva al modelo, solo reparte artificialmente el peso de una sola señal real
# entre dos "variables" en el gráfico de importancia.
# 🗑️ 'Gano_Puja' también se ha quitado de las features (antes de entreno): en
# predecir_amenazas() siempre se fija a 1 porque solo predecimos "cuánto pujará
# el ganador", así que en inferencia era una constante — no aportaba información,
# solo ruido/riesgo de sobreajuste. Sigue existiendo como columna para FILTRAR
# los eventos de entreno (ver más abajo), pero ya no entra como variable del modelo.
# 🗓️ 'Dificultad_Calendario_Rival' es la mejora pendiente que se dejó preparada:
# usa mapa_dificultad_calendario_global (definido más abajo, reutilizando la
# lógica de la pestaña de Análisis de Rivales). Con la liga sin empezar hoy es
# un proxy por valor de mercado del rival (o 50 neutro si tampoco hay eso), así
# que aporta poco por ahora — pero en cuanto haya jornadas jugadas empezará a
# usar la clasificación real automáticamente, sin tocar código.
# 🗑️ 'Riqueza_Relativa' se ha quitado de las features: es 'Balance Total (€)'
# dividido por la suma de saldos de TODA la liga en el momento de entrenar —
# esa suma es la MISMA constante para las 80 filas de entreno (no varía fila a
# fila), así que dividir por ella no cambia el orden ni añade información:
# correlación medida con los datos reales = 1.0 exacta. Es el mismo tipo de
# duplicado que 'Índice Fichajes', solo que disfrazado de variable distinta por
# llevar otra escala. No se muestra en ninguna pantalla de la app, así que se ha
# eliminado también su cálculo (no solo de la lista de features).
# ➕ 'Media Puntos' faltaba: estaban las medias en casa y fuera pero no la
# general, que es la señal más directa de lo bueno que es un jugador y por tanto
# de las ganas que le va a poner la gente en la subasta.
# ⚖️ MENOS ES MÁS. Con solo ~100 pujas para entrenar, cada variable extra es
# una oportunidad de que el bosque aprenda ruido. Medido con backtest sobre sus
# 102 pujas y tres semillas distintas:
#
#   10 variables (Balance, Sobrepuja Media, las tres medias, dificultad...)
#        -> error 12,90% ± 0,05
#   4 variables (valor, perfil de derroche, su desviación y la posición)
#        -> error 12,43% ± 0,03   ← y además más estable
#
# Todo lo que se quitó EMPEORABA el modelo, no lo mejoraba. Tiene sentido: lo
# que decide una puja es cuánto vale el jugador y cómo de manirroto es quien
# puja; el rendimiento del jugador ya está dentro de su precio, y el saldo que
# se usaba era el de HOY, no el que tenía el día de la subasta.
#
# Si algún día hay 300 o 400 pujas registradas, merece la pena volver a probar
# las variables descartadas: con más datos puede que empiecen a aportar.
FEATURES_ML = [
    'Valor Mercado (€)', 'Perfil_Derroche', 'Std_Derroche', 'Pos_Limpia'
]

# 🎯 Rejilla de hiperparámetros candidatos para el RandomForest. Antes estaban
# fijos a ojo (max_depth=4, min_samples_leaf=5) en las tres funciones a la vez.
# Ahora se prueban varias combinaciones con el propio backtest leave-one-out
# y se elige la que dé menor error (MAE) — ver seleccionar_mejores_hiperparametros().
# 'max_features' entra ahora en la rejilla: estaba fijo en 'sqrt', que con diez
# variables deja solo tres candidatas por nodo. Con tan pocas filas de entreno
# eso poda demasiado; medido, 0.5 va mejor.
GRID_HIPERPARAMETROS_ML = [
    {'max_depth': 3, 'min_samples_leaf': 5, 'max_features': 0.5},
    {'max_depth': 3, 'min_samples_leaf': 5, 'max_features': 'sqrt'},
    {'max_depth': 4, 'min_samples_leaf': 5, 'max_features': 0.5},
    {'max_depth': 4, 'min_samples_leaf': 8, 'max_features': 0.5},
    {'max_depth': 5, 'min_samples_leaf': 5, 'max_features': 0.5},
    {'max_depth': 5, 'min_samples_leaf': 8, 'max_features': 'sqrt'},
    {'max_depth': 6, 'min_samples_leaf': 10, 'max_features': 0.5},
]
# 80 árboles daban una predicción que bailaba según la semilla del generador
# (±0,15 puntos de MAE). 400 la estabilizan (±0,07).
N_ESTIMATORS_ML = 400
# Para BUSCAR hiperparámetros no hace falta esa precisión: con 120 árboles el
# orden entre combinaciones es el mismo y la búsqueda cuesta la tercera parte.
# Combinación fija: la del medio de la rejilla, ni la más simple ni la más
# compleja. Ver el comentario de seleccionar_mejores_hiperparametros().
BUSCAR_HIPERPARAMETROS = False
HIPERPARAMETROS_FIJOS_ML = {'max_depth': 4, 'min_samples_leaf': 5, 'max_features': 0.5}
N_ESTIMATORS_BUSQUEDA = 120
# ...y tampoco hace falta dejar fuera cada una de las pujas, una por una: para
# ORDENAR combinaciones basta con una de cada tres. La validación final sí se
# hace dejando fuera todas, una a una, porque ese número es el que se enseña.
PASO_FOLDS_BUSQUEDA = 3

# 📅 Ventana de proyección de precio: antes 'roi' usaba *5 días y 'precio_proy'
# usaba *4 días para el mismo concepto (cuánto subirá el precio a corto plazo)
# sin ninguna razón para que fueran distintos. Se unifica en una sola constante.
DIAS_PROYECCION = 5


def _rellenar_casa_fuera(df, col_casa='Media Puntos Casa', col_fuera='Media Puntos Fuera', col_media='Media Puntos'):
    """Convierte a numérico y rellena huecos en Media Puntos Casa/Fuera SIN usar 0.
    Antes se hacía fillna(0), lo cual es engañoso: 0 no significa "sin dato", significa
    "puntúa 0 en casa/fuera", una señal negativa fuerte y falsa para el modelo. Se rellena
    primero con la Media Puntos general del propio jugador (mejor estimación disponible) y,
    si tampoco existe, con la mediana de la liga."""
    df = df.copy()
    for col in (col_casa, col_fuera):
        df[col] = pd.to_numeric(df.get(col), errors='coerce')
    mediana_liga = pd.to_numeric(df.get(col_media), errors='coerce').median()
    if pd.isna(mediana_liga): mediana_liga = 0.0
    media_propia = pd.to_numeric(df.get(col_media), errors='coerce')
    for col in (col_casa, col_fuera):
        df[col] = df[col].fillna(media_propia).fillna(mediana_liga)
    return df


def _preparar_datos_entreno(compras):
    """Construye df_train + patron_psicologico a partir de TODOS los eventos
    (pujas ganadas y perdidas), que es lo que necesitamos para el perfil de
    comportamiento de cada manager (Perfil_Derroche, Std_Derroche, etc. — cuánto
    se pasa de precio CUANDO puja, gane o pierda, es una señal de su forma de ser).
    Devuelve también df_train filtrado SOLO a pujas ganadas (Gano_Puja == 1),
    que es el subconjunto correcto para entrenar el objetivo real: "cuánto pagó
    el que se llevó al jugador". Mezclar aquí las pujas perdidas metía en el
    mismo target dos procesos distintos (cuánto ofrezco si gano vs. cuánto
    ofrezco y aun así pierdo), y encima 'Gano_Puja' se colaba como feature que
    en producción (predecir_amenazas) siempre vale 1 — es decir, no informaba
    nada al modelo, solo ruido.
    """
    compras = compras.copy()
    compras['Pct_Sobrepuja'] = (compras['Importe (€)'] - compras['Valor Mercado (€)']) / compras['Valor Mercado (€)']
    compras['Modulo_10k'] = (compras['Importe (€)'] % 10000 == 0).astype(int)

    patron_psicologico = compras.groupby('Persona').agg(
        Perfil_Derroche_Crudo=('Pct_Sobrepuja', 'mean'),
        Std_Derroche=('Pct_Sobrepuja', 'std'),
        Prob_Redondeo=('Modulo_10k', 'mean')
    ).reset_index()

    mediana_std = patron_psicologico['Std_Derroche'].median()
    if pd.isna(mediana_std): mediana_std = 0.15
    patron_psicologico['Std_Derroche'] = patron_psicologico['Std_Derroche'].fillna(mediana_std)

    df_part = db['participantes'].dropna(subset=['Persona'])

    if 'Tasa Sobrepuja % (shrinkage, uso interno predicción)' in df_part.columns:
        df_part_shrink = df_part[['Persona', 'Tasa Sobrepuja % (shrinkage, uso interno predicción)']].copy()
        df_part_shrink = df_part_shrink.rename(columns={'Tasa Sobrepuja % (shrinkage, uso interno predicción)': 'Perfil_Derroche'})
    else:
        df_part_shrink = df_part[['Persona']].copy()
        df_part_shrink = df_part_shrink.merge(patron_psicologico[['Persona', 'Perfil_Derroche_Crudo']], on='Persona', how='left')
        df_part_shrink = df_part_shrink.rename(columns={'Perfil_Derroche_Crudo': 'Perfil_Derroche'})

    patron_psicologico = patron_psicologico.merge(df_part_shrink[['Persona', 'Perfil_Derroche']], on='Persona', how='left')

    df_train = compras.merge(patron_psicologico, on='Persona', how='left')

    cols_part = ['Persona', 'Balance Total (€)']
    if 'Sobrepuja Media Personal (€)' in df_part.columns:
        cols_part.append('Sobrepuja Media Personal (€)')

    df_train = df_train.merge(df_part[cols_part], on='Persona', how='left')

    stats_mercado = db['mercado'][['Jugador', 'Media Puntos', 'Media Puntos Casa', 'Media Puntos Fuera']].drop_duplicates('Jugador')
    df_train = df_train.merge(stats_mercado, on='Jugador', how='left')
    df_train = _rellenar_casa_fuera(df_train)

    if 'Sobrepuja Media Personal (€)' in df_train.columns:
        df_train['Sobrepuja Media Personal (€)'] = pd.to_numeric(df_train['Sobrepuja Media Personal (€)'], errors='coerce').fillna(0)
    else:
        df_train['Sobrepuja Media Personal (€)'] = 0

    # fillna antes de astype(str): con la columna 'Posición' vacía (es una
    # fórmula de búsqueda que devuelve "" si el jugador ya no está en
    # Mercado_Global) el astype dejaba NaN y el split reventaba la app entera.
    df_train['Pos_Limpia'] = df_train['Posición'].fillna('').astype(str).apply(lambda x: x.split('/')[0].strip())
    df_train['Objetivo_Pct'] = df_train['Pct_Sobrepuja']
    df_train['Dificultad_Calendario_Rival'] = df_train['Equipo'].map(mapa_dificultad_calendario_global).fillna(50.0)

    # 🎯 Se entrena con TODAS las pujas, ganadas y perdidas. Antes solo con las
    # ganadas, que por definición son la más alta de cada subasta: el modelo
    # aprendía "cuánto ofrece el que gana" y luego se usaba para predecir lo que
    # ofrecerá CADA mánager. Medido sobre sus 186 pujas, eso inflaba todas las
    # predicciones en +5,6 puntos porcentuales. Una puja perdida no es un dato
    # incompleto: es exactamente lo que ese mánager estaba dispuesto a pagar.
    df_train_ganadas = df_train.copy()

    return df_train_ganadas, patron_psicologico


def _entrenar_random_forest(X_encoded, y, max_depth, min_samples_leaf, max_features=0.5,
                            n_estimators=None):
    modelo = RandomForestRegressor(
        n_estimators=n_estimators or N_ESTIMATORS_ML, max_depth=max_depth,
        min_samples_leaf=min_samples_leaf, max_features=max_features, random_state=42
    )
    modelo.fit(X_encoded, y)
    return modelo


# 💾 persist="disk": el resultado sobrevive a reiniciar la app. Con
# cache_resource se guardaba solo en memoria, así que CADA vez que arrancabas
# volvía a hacer el backtest entero (~90 s mirando una pantalla en blanco).
# Ahora esos 90 s se pagan una sola vez por cada cambio en las pujas: al día
# siguiente, tras registrar una compra nueva; el resto de arranques son
# instantáneos.
# --- 🧪 VALIDACIÓN DEL MODELO: BACKTESTING LEAVE-ONE-OUT ---
# Ahora acepta max_depth/min_samples_leaf como parámetros (antes estaban fijos
# a 4 y 5 aquí dentro) para poder reutilizar esta misma función tanto para
# validar el modelo final como para comparar la rejilla de hiperparámetros en
# seleccionar_mejores_hiperparametros(). Y, como en el entrenamiento, se
# restringe a pujas GANADAS: evaluar con pujas perdidas mezcladas medía un
# problema distinto al que resuelve predecir_amenazas() en producción.
# 🚀 Llamadas a nivel de módulo, en orden: primero se decide la mejor combinación
# de hiperparámetros con el backtest, luego se entrena el modelo final con ella,
# y por último se guardan las métricas de validación de esa combinación ganadora
# (antes 'metricas_validacion_ml' medía SIEMPRE max_depth=4/min_samples_leaf=5,
# aunque el modelo real entrenado usara otra cosa — ahora son siempre coherentes).
_huella_ml = _huella_pujas(db['contabilidad'])
# El modelo antiguo de sobrepuja ya no predice nada: las pujas las decide el
# sistema de dos etapas. De todo aquel montaje solo se sigue usando el patrón de
# gasto de cada mánager (su regularidad al pujar), que no necesita modelo: sale
# directamente de las subastas registradas.
@st.cache_data(show_spinner=False)
def patron_de_gasto(huella=None):
    compras = construir_eventos_puja(db['contabilidad'])
    if len(compras) < 5:
        return pd.DataFrame()
    _, patron = _preparar_datos_entreno(compras)
    return patron


patron_mgr = patron_de_gasto(_huella_ml)
# Con las pujas perdidas dentro, el backtest pasó de 103 a 186 pliegues y el
# arranque se fue a 122 s. Dejando fuera una de cada dos pujas la estimación
# sigue apoyándose en 93 casos —de sobra para una cifra honesta— y el arranque
# vuelve a su sitio. Solo se paga al registrar una puja nueva.


# --- 🔬 TRANSPARENCIA DEL MODELO: IMPORTANCIA DE VARIABLES ---
# Solo las cuatro que usa el modelo: las demás se retiraron porque empeoraban
# la predicción, y dejar aquí sus etiquetas hacía pensar que seguían contando.
ETIQUETAS_FEATURES_ML = {
    'Valor Mercado (€)': '💰 Precio del jugador',
    'Perfil_Derroche': '🎭 Perfil de gasto histórico (Patrón ML)',
    'Std_Derroche': '📊 Regularidad/impulsividad al pujar',
    'Pos_Limpia': '🏃 Posición del jugador',
}

# --- 🎨 HERRAMIENTAS DE COLOR Y ESTILO ---
ESTILO_CABECERA = [{'selector': 'th', 'props': [('background-color', '#87cefa'), ('color', '#000000'), ('font-weight', 'bold'), ('font-size', '14px')]}]

def formato_euro(valor):
    if pd.isna(valor): return ""
    return f"{valor:,.0f} €".replace(",", ".")

def formato_euro_corto(valor):
    """Euros abreviados para las métricas: 59.320.000 € -> 59,3 M€.

    Las cajas de st.metric tienen el ancho de su columna y recortan el texto con
    puntos suspensivos cuando no cabe: con seis métricas en fila, "59.320.000 €"
    salía como "59.320….". El número completo se sigue viendo en la ayuda (?)."""
    if pd.isna(valor):
        return ""
    try:
        num = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    signo = "-" if num < 0 else ""
    num = abs(num)
    if num >= 1_000_000:
        return f"{signo}{num / 1_000_000:,.1f} M€".replace(".", "|").replace(",", ".").replace("|", ",")
    # Por debajo del millón, la cifra entera: "940.000 €", nunca "940 k€".
    return f"{signo}{num:,.0f} €".replace(",", ".")


def formato_tendencia(valor):
    if pd.isna(valor): return ""
    if isinstance(valor, (int, float)) and valor > 0: return f"+{valor:,.0f} €".replace(",", ".")
    return f"{valor:,.0f} €".replace(",", ".")

def formato_puntos(valor):
    if pd.isna(valor): return ""
    # except concreto: un 'except:' pelado se traga también los errores de
    # programación (un NameError, por ejemplo) y los convierte en texto raro.
    try: return f"{float(valor):.2f}".replace(".", ",")
    except (TypeError, ValueError): return str(valor)

# 🎨 Escala de color para las medias, compartida por Mercado y Plantillas.
# Vivía dentro de ui_mercado, así que Plantillas no podía usarla. Antes de eso
# recibía el valor y lo ignoraba: pintaba TODAS las celdas del mismo rojo, y una
# media de 12 y una de 1 se veían igual. Los cortes son los de la liga: por
# debajo de 3 es flojo, por encima de 6 es bueno.
def aviso_sin_resultados(filtros_activos, claves_estado):
    """Cuando un filtro deja la lista a cero, decir CUÁL es el que estorba y
    ofrecer quitarlos. Antes solo salía "Ningún jugador cumple esos filtros",
    que es un callejón sin salida: en Mercado se llega ahí fácil combinando
    posición, equipo, precio y estado físico, y no se sabía cuál sobraba."""
    if filtros_activos:
        st.info("Ningún jugador cumple estos filtros: **"
                + "**, **".join(filtros_activos) + "**.")
    else:
        st.info("No hay jugadores que mostrar.")
    if st.button("Quitar los filtros", key="limpiar_" + "_".join(claves_estado)[:40]):
        for clave in claves_estado:
            st.session_state.pop(clave, None)
        st.rerun()


def pintar_escala_medias(valor):
    try:
        num = float(str(valor).replace(',', '.'))
    except (TypeError, ValueError):
        return ''
    if pd.isna(num) or num <= 0:
        return 'color: #6b7280;'                                  # sin datos aún
    if num < 3:
        return 'background-color: rgba(220, 38, 38, 0.22); color: #fca5a5;'
    if num < 4.5:
        return 'background-color: rgba(245, 158, 11, 0.20); color: #fcd34d;'
    if num < 6:
        return 'background-color: rgba(132, 204, 22, 0.18); color: #bef264;'
    if num < 8:
        return 'background-color: rgba(34, 197, 94, 0.22); color: #86efac;'
    return 'background-color: rgba(16, 185, 129, 0.32); color: #6ee7b7; font-weight: 800;'


def pintar_fondo_tendencias(valor):
    if isinstance(valor, (int, float)):
        if valor < 0: return 'background-color: rgba(255, 100, 100, 0.2); color: #ff6666; font-weight: bold;'
        elif valor > 0: return 'background-color: rgba(100, 255, 100, 0.2); color: #66ff66; font-weight: bold;'
        else: return 'background-color: transparent; color: #888888; font-weight: normal;'
    return ''

COLORES_MANAGERS = {
    'Algeciras': '#f4b084', 'Barreño': '#ffe699', 'Competa': '#9bc2e6',
    'Ciudad Algeciras': '#a9d08e', 'Real Madrid': '#ffffff', 'Nike': '#ffd966',
    'La Caleta': '#c6e0b4', 'Cordoba': '#f8cbad', 'Rizo Team': '#bdd7ee',
    'Vodka Juniors': '#e2efda'
}

def pintar_filas_manager(row):
    manager = ""
    if 'Persona' in row.index: manager = row['Persona']
    elif 'Participante' in row.index: manager = row['Participante']
    color = COLORES_MANAGERS.get(manager, '#2b2b40')
    return [f'background-color: {color}dd; color: #000000;' for _ in row]

# --- ⚡ OPTIMIZACIÓN DE RENDIMIENTO: CACHÉ DE IMÁGENES ---
def _huella_imagen(ruta):
    """Fecha de modificación y tamaño del archivo, o None si no existe."""
    try:
        info = os.stat(ruta)
        return (info.st_mtime, info.st_size)
    except OSError:
        return None


@st.cache_data(show_spinner=False, max_entries=4000)
def _leer_imagen_base64(ruta, huella):
    """La huella entra en la clave de caché a propósito: es lo que permite que al
    dejar una cara nueva en 'caras/' (o cambiar un escudo) baste con refrescar el
    navegador, sin reiniciar la app. Cuando el archivo no existía, la huella era
    None; en cuanto aparece pasa a ser otra cosa, la clave cambia y se lee.

    El parámetro no lleva guion bajo por el mismo motivo que en load_data:
    Streamlit ignora a efectos de caché los argumentos que empiezan por '_', y
    entonces la huella no serviría para nada."""
    if huella is None:
        return None
    try:
        with open(ruta, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception:
        return None


def img_to_base64(ruta):
    """Imagen en base64, cacheada pero atenta a los cambios en disco. Comprobar
    la huella es un os.stat por imagen y llamada (microsegundos); leer y
    recodificar el archivo, que es lo caro, solo pasa cuando cambia de verdad."""
    return _leer_imagen_base64(ruta, _huella_imagen(ruta))

# ⚡ IMÁGENES SERVIDAS COMO ARCHIVOS, NO METIDAS EN EL HTML
# Cada carta llevaba su cara y su escudo dentro del HTML, codificados en texto
# (base64): en Plantillas o Rivales eso son del orden de 1-2 MB que viajan al
# navegador EN CADA CLIC. Con el servidor de archivos de Streamlit activado
# (server.enableStaticServing = true en .streamlit/config.toml), las imágenes
# se piden por su dirección y el navegador las guarda: el HTML pasa a pesar
# unos pocos KB. La app copia sola tus carpetas caras/ y equipo/ dentro de
# static/, que es la única carpeta que Streamlit sirve. Si la opción no está
# activada, todo sigue como antes.
CARPETA_APP = os.path.dirname(os.path.abspath(__file__))
CARPETAS_IMAGENES = ('caras', 'equipo')


def _servir_estaticos():
    try:
        return st.get_option("server.enableStaticServing") is True
    except Exception:
        return False


@st.cache_data(show_spinner=False)
def _copiar_imagenes_a_static(huella_carpetas=None):
    """Copia a static/ las imágenes que falten o hayan cambiado. Se repite solo
    cuando cambia algo en caras/ o equipo/."""
    import shutil
    copiadas = 0
    for carpeta in CARPETAS_IMAGENES:
        origen = os.path.join(CARPETA_APP, carpeta)
        if not os.path.isdir(origen):
            continue
        destino = os.path.join(CARPETA_APP, 'static', carpeta)
        os.makedirs(destino, exist_ok=True)
        for nombre in os.listdir(origen):
            desde, hasta = os.path.join(origen, nombre), os.path.join(destino, nombre)
            if os.path.isfile(desde) and (not os.path.exists(hasta)
                                          or os.path.getmtime(hasta) < os.path.getmtime(desde)):
                shutil.copy2(desde, hasta)
                copiadas += 1
    return copiadas


def _huella_carpetas_imagenes():
    huella = []
    for carpeta in CARPETAS_IMAGENES:
        ruta = os.path.join(CARPETA_APP, carpeta)
        if os.path.isdir(ruta):
            huella.append((carpeta, os.path.getmtime(ruta), len(os.listdir(ruta))))
    return tuple(huella)


# ⚠️ Servir las imágenes como archivos (static/) se probó el 24/09/2026 y en tu
# PC las dejó todas rotas: caras, escudos de las cartas, del calendario y de la
# clasificación. Se vuelve a lo que funcionaba, la imagen incrustada. Aunque en
# config.toml siga puesto enableStaticServing, aquí no se usa.
SERVIR_IMAGENES = False
if SERVIR_IMAGENES:
    try:
        _copiar_imagenes_a_static(_huella_carpetas_imagenes())
    except Exception:
        SERVIR_IMAGENES = False


def url_imagen(*rutas):
    """La dirección de la primera de `rutas` que exista: servida como archivo
    si se puede, incrustada en base64 si no. None si no hay ninguna."""
    import urllib.parse
    for ruta in rutas:
        if SERVIR_IMAGENES and os.path.exists(os.path.join(CARPETA_APP, 'static', ruta)):
            return "app/static/" + urllib.parse.quote(ruta.replace(os.sep, '/'))
        b64 = img_to_base64(ruta)
        if b64:
            return f"data:image/{'png' if ruta.lower().endswith('.png') else 'jpeg'};base64,{b64}"
    return None


def escudo_html(nombre_equipo, size=34):
    url = url_imagen(f"equipo/{nombre_equipo}.png", f"equipo/{nombre_equipo}.jpg")
    if url:
        return f'<img src="{url}" style="width:{size}px; height:{size}px; object-fit:contain; vertical-align:middle;">'
    inicial = (nombre_equipo or '?')[:1].upper()
    return (f'<div style="width:{size}px; height:{size}px; border-radius:50%; background:#33334d; '
            f'color:#ccc; display:inline-flex; align-items:center; justify-content:center; '
            f'font-size:{int(size*0.5)}px; font-weight:800; vertical-align:middle;">{inicial}</div>')

# --- 🃏 MOTOR GLOBAL DE RENDERIZADO DE CARTAS ---
# El icono de abajo a la izquierda de la carta: (fondo, icono, rótulo al pasar el ratón).
# El lesionado sigue con su ambulancia de siempre; la duda es una exclamación y
# la sanción, una tarjeta roja dibujada.
ICONO_ESTADO = {
    'lesionado': ('#dc2626', '🚑', 'Lesionado'),
    'sancionado': ('#111827', "<span style='display:block; width:10px; height:14px; background:#ef4444; "
                              "border-radius:2px; transform:rotate(12deg); "
                              "box-shadow:0 1px 2px rgba(0,0,0,0.6);'></span>", 'Sancionado'),
    'duda': ('#f59e0b', "<span style='color:#ffffff; font-weight:900; font-size:17px; "
                        "line-height:1; font-family:Inter, sans-serif;'>!</span>", 'En duda'),
    'descartado': ('#4b5563', '🚫', 'Descartado por su club'),
}


def _enumerar(cosas):
    cosas = list(cosas)
    return cosas[0] if len(cosas) == 1 else ", ".join(cosas[:-1]) + " y " + cosas[-1]


def _mini_icono_estado(estado):
    """El icono de la carta en pequeño, para acompañar un nombre en un texto."""
    if estado not in ICONO_ESTADO:
        return ""
    fondo, icono, rotulo = ICONO_ESTADO[estado]
    icono = (icono.replace("width:10px; height:14px", "width:7px; height:10px")
                  .replace("font-size:17px", "font-size:11px"))
    return (f"<span title='{rotulo}' style='display:inline-flex; align-items:center; justify-content:center; "
            f"width:17px; height:17px; border-radius:50%; background:{fondo}; font-size:9px; "
            f"vertical-align:-3px; margin-right:4px; border:1px solid rgba(255,255,255,0.7);'>{icono}</span>")


def generar_carta_html(player, pos_type='MED', is_empty=False, mostrar_proximo_rival=True,
                       variacion_invertida=False, candado_dias=None):
    uid = uuid.uuid4().hex[:6]

    if is_empty:
        return (
            f'<div id="empty_{uid}" class="fut-card" style="background: rgba(50, 0, 0, 0.8); border: 2px dashed #ff4b4b; border-radius: 8px; width: 125px; padding: 10px 3px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.5); z-index: 2;">'
            '<div style="font-size: 20px; line-height: 1; margin-bottom: 2px;">🚷</div>'
            '<div style="color: #ff4b4b; font-size: 0.7em; font-weight: bold; white-space: nowrap;">Hueco Libre</div>'
            '<div style="color: #ff8c8c; font-size: 0.7em; font-weight: bold;">-4 Puntos</div>'
            '</div>'
        )
    else:
        if pos_type == 'DEL': bg, bd, text = '#3a1515', '#ff4b4b', '#ff8c8c'
        elif pos_type == 'MED': bg, bd, text = '#3a3515', '#ffd966', '#ffe699'
        elif pos_type == 'DEF': bg, bd, text = '#15153a', '#4b4bff', '#8c8cff'
        elif pos_type == 'POR': bg, bd, text = '#153a15', '#a9d08e', '#c6e0b4'
        else: bg, bd, text = '#222222', '#ffffff', '#ffffff'

        var_diaria = player.get('Variación Diaria (€)', 0)
        if pd.isna(var_diaria):
            var_diaria = 0

        # 🎨 En una carta normal, subir de valor es bueno (verde) y bajar es malo.
        # En una carta de movimiento ese hueco lo ocupa la SOBREPUJA, y ahí el
        # signo significa lo contrario: pagar por encima del valor de mercado es
        # perder dinero, y comprar por debajo es ganarlo. Con variacion_invertida
        # se cambian los colores sin tocar el resto de la carta.
        color_sube = '#f87171' if variacion_invertida else '#4ade80'
        color_baja = '#4ade80' if variacion_invertida else '#f87171'

        if var_diaria > 0:
            var_html = f'<div style="color: {color_sube}; font-size: 0.65em; font-weight: bold; margin-top: 2px;">⬆ {formato_euro(var_diaria)}</div>'
        elif var_diaria < 0:
            var_html = f'<div style="color: {color_baja}; font-size: 0.65em; font-weight: bold; margin-top: 2px;">⬇ {formato_euro(abs(var_diaria))}</div>'
        else:
            var_html = f'<div style="color: #a0aec0; font-size: 0.65em; font-weight: bold; margin-top: 2px;">- 0 €</div>'

        puntos = player.get('Puntos', None)
        media = player.get('Media Puntos', None)
        media_casa = player.get('Media Puntos Casa', None)
        media_fuera = player.get('Media Puntos Fuera', None)

        puntos_fmt = str(int(puntos)) if pd.notna(puntos) and puntos != 0 else "-"
        media_fmt = formato_puntos(media) if pd.notna(media) and media != 0 else "-"
        casa_fmt = formato_puntos(media_casa) if pd.notna(media_casa) and media_casa != 0 else "-"
        fuera_fmt = formato_puntos(media_fuera) if pd.notna(media_fuera) and media_fuera != 0 else "-"

        is_star = es_carta_estrella(player)
        extra_class = " star-card" if is_star else ""

        esquina_izq = (
            '<div style="position:absolute; top:5px; left:6px; text-align:left; line-height:1.15; z-index: 3;">'
            f'<div style="color:#ffffff; font-size:0.68em; font-weight:bold;">{puntos_fmt}</div>'
            f'<div style="color:#cccccc; font-size:0.6em;">{media_fmt}</div>'
            '</div>'
        )
        esquina_dcha = (
            '<div style="position:absolute; top:5px; right:6px; text-align:right; line-height:1.3; z-index: 3;">'
            f'<div style="color:#ffffff; font-size:0.64em;">🏠 {casa_fmt}</div>'
            f'<div style="color:#ffffff; font-size:0.64em; margin-top:2px;">✈️ {fuera_fmt}</div>'
            '</div>'
        )

        abrev_pos = {'Portero': 'POR', 'Defensa': 'DEF', 'Centrocampista': 'MED', 'Delantero': 'DEL'}
        pos_lista = [p.strip() for p in str(player.get('Posición', '')).split('/') if p.strip()]
        pos_abrevs = [abrev_pos.get(p, p[:3].upper()) for p in pos_lista] or [pos_type]
        pos_lineas_html = ''.join(f'<div style="padding:1px 0;">{p}</div>' for p in pos_abrevs)
        badge_posicion = (
            '<div style="position:absolute; top:40%; left:-8px; transform:translateY(-50%); z-index:20; '
            'display:flex; flex-direction:column; align-items:center; gap:2px; '
            'background:#4b5563; color:#d1d5db; font-size:0.5em; font-weight:800; letter-spacing:0.5px; '
            'line-height:1.1; text-align:center; padding:4px 3px; border-radius:8px; border:1px solid #d1d5db; '
            'box-shadow:0 2px 4px rgba(0,0,0,0.6);">'
            f'{pos_lineas_html}'
            '</div>'
        )

        goles_val = player.get('Goles', 0)
        asist_val = player.get('Asistencias', 0)
        try: goles_val = int(goles_val) if pd.notna(goles_val) else 0
        except (TypeError, ValueError): goles_val = 0
        try: asist_val = int(asist_val) if pd.notna(asist_val) else 0
        except (TypeError, ValueError): asist_val = 0

        # 🔒 Candado de venta bloqueada. Va pegado al borde derecho y a la altura
        # 🔒 Candado de venta bloqueada, en la esquina inferior derecha y
        # desbordando la carta, con el mismo tamaño y hechura que el badge de
        # posición. Va FUERA del div de la carta, junto a los demás badges: la
        # carta lleva overflow:hidden, así que cualquier cosa colocada dentro se
        # recorta en el borde y no puede sobresalir. Solo lo pide la pestaña de
        # Plantillas; el resto de la app pinta la carta igual que antes.
        candado_html = ""
        if candado_dias:
            candado_html = (
                '<div style="position:absolute; bottom:-7px; right:-10px; z-index:25; display:flex; '
                'align-items:center; gap:4px; background:#7f1d1d; color:#ffdada; '
                'font-size:0.66em; font-weight:800; letter-spacing:0.5px; line-height:1.1; '
                'padding:5px 10px; border-radius:9px; border:1px solid #ff4b4b; '
                'box-shadow:0 2px 5px rgba(0,0,0,0.7); white-space:nowrap;" '
                f'title="No se puede vender hasta dentro de {candado_dias} día'
                f'{"s" if candado_dias != 1 else ""}">'
                f'<span style="line-height:1;">🔒</span><span>{candado_dias}d</span>'
                '</div>'
            )

        badge_stats = ""
        if goles_val > 0 or asist_val > 0:
            badge_stats = (
                '<div style="position:absolute; top:40%; right:-18px; transform:translateY(-50%); z-index:20; '
                'display:flex; flex-direction:column; align-items:center; gap:2px; '
                'background:#4b5563; color:#d1d5db; font-size:0.58em; font-weight:800; '
                'line-height:1.1; text-align:center; padding:4px 5px; border-radius:8px; border:1px solid #d1d5db; '
                'box-shadow:0 2px 4px rgba(0,0,0,0.6); white-space:nowrap;">'
                f'<div style="padding:1px 0;">⚽ {goles_val}</div>'
                f'<div style="padding:1px 0;">🅰️ {asist_val}</div>'
                '</div>'
            )
            
        # Lógica de Lesión / Duda MOVIDA ABAJO A LA IZQUIERDA
        badge_lesion = ""
        estado_carta = estado_jugador(player)
        if estado_carta in ICONO_ESTADO:
            fondo, icono, rotulo = ICONO_ESTADO[estado_carta]
            badge_lesion = (
                '<div style="position:absolute; bottom:-5px; left:-10px; z-index:30; '
                f'background:{fondo}; border-radius:50%; width:26px; height:26px; '
                'display:flex; align-items:center; justify-content:center; '
                f'font-size:14px; box-shadow:0 3px 6px rgba(0,0,0,0.8); border:2px solid #fff;" title="{rotulo}">'
                f'{icono}'
                '</div>'
            )

        nombre_equipo = str(player.get("Equipo", ""))
        escudo_png = f"equipo/{nombre_equipo}.png"
        escudo_jpg = f"equipo/{nombre_equipo}.jpg"
        
        escudo_bg_html = ""
        escudo_url = url_imagen(escudo_png, escudo_jpg)
        
        if escudo_url:
            escudo_bg_html = f'<div id="bg_{uid}" style="position: absolute; top: 5%; left: 5%; width: 90%; height: 90%; background-image: url(\'{escudo_url}\'); background-repeat: no-repeat; background-position: center center; background-size: contain; opacity: 0.20; z-index: 1; pointer-events: none;"></div>'
        else:
            escudo_bg_html = f'<div id="bg_{uid}" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 1;"></div>'

        nombre_jugador = str(player["Jugador"])
        ruta_png = f"caras/{nombre_jugador}.png"
        ruta_jpg = f"caras/{nombre_jugador}.jpg"
        
        foto_url = url_imagen(ruta_png, ruta_jpg)
        
        if foto_url:
            foto_html = f'<img id="face_{uid}" src="{foto_url}" style="width: 55px; height: 55px; border-radius: 50%; object-fit: cover; border: 2px solid {bd}; margin-bottom: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.5); position: relative; z-index: 3;">'
        else:
            parts = nombre_jugador.split()
            if len(parts) >= 2: iniciales = (parts[0][0] + parts[1][0]).upper()
            elif len(parts) == 1: iniciales = parts[0][:2].upper()
            else: iniciales = "??"
            foto_html = f'<div id="face_{uid}" style="width: 55px; height: 55px; border-radius: 50%; background-color: {bd}; color: #111; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 900; margin-bottom: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.5); position: relative; z-index: 3; border: 2px solid white; box-sizing: border-box;">{iniciales}</div>'

        proximo_rival_html = ""
        if mostrar_proximo_rival:
            fix_card = get_fixture_equipo(nombre_equipo)
            if fix_card is not None:
                icono_lugar = "🏠" if fix_card['es_casa'] else "✈️"
                escudo_rival_html = escudo_html(fix_card['rival'], size=16)
                if fix_card['dificultad'] < cortes_color_dificultad()[0]:
                    color_badge = '#0f5c2e'
                    borde_badge = '#22c55e'
                elif fix_card['dificultad'] >= cortes_color_dificultad()[3]:
                    color_badge = '#5c0f14'
                    borde_badge = '#dc2626'
                else:
                    color_badge = '#4b5563'
                    borde_badge = '#d1d5db'
                proximo_rival_html = (
                    f'<div title="Jornada {fix_card["jornada"]}: vs {fix_card["rival"]}" '
                    f'style="position:absolute; top:-11px; left:50%; transform:translateX(-50%); z-index:20; display:flex; align-items:center; gap:2px; '
                    f'background:{color_badge}; border:1px solid {borde_badge}; border-radius:12px; '
                    'padding:2px 6px; box-shadow:0 2px 4px rgba(0,0,0,0.6); white-space:nowrap;">'
                    f'<span style="font-size:0.7em; line-height:1;">{icono_lugar}</span>{escudo_rival_html}'
                    '</div>'
                )

        return (
            f'<div style="position:relative; display:inline-block;">'
            f'{badge_lesion}'
            f'{proximo_rival_html}'
            f'{badge_posicion}'
            f'{badge_stats}'
            f'{candado_html}'
            f'<div id="card_{uid}" class="fut-card{extra_class}" style="background: linear-gradient(180deg, {bg} 0%, #111 100%); border: 2px solid {bd}; border-radius: 8px; width: 125px; padding: 24px 3px 10px 3px; text-align: center; box-shadow: 0 4px 8px rgba(0,0,0,0.8); z-index: 2; position: relative; overflow: hidden; display: inline-block;">'
            f'{escudo_bg_html}'
            f'{esquina_izq}'
            f'{esquina_dcha}'
            f'<div style="display: flex; justify-content: center; margin-top: 6px; position: relative; z-index: 3;">{foto_html}</div>'
            f'<div style="color: white; font-size: 0.85em; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 4px; position: relative; z-index: 3;">{nombre_jugador}</div>'
            f'<div style="color: {text}; font-size: 0.85em; font-weight: bold; margin-top: 2px; position: relative; z-index: 3;">{formato_euro(player["Valor Actual (€)"])}</div>'
            f'<div style="position: relative; z-index: 3;">{var_html}</div>'
            f'</div>'
            f'</div>'
        )


def generar_tarjeta_amenaza_html(icono, color_borde, row):
    # La barra muestra la PROBABILIDAD DE QUE PUJE, no el encaje táctico. El
    # encaje se quedó plano en el 5% para dos tercios de las tarjetas cuando dejó
    # de usarse como filtro, y además ya no es el criterio con el que la app
    # elige a estos mánagers.
    score_val = _a_float(row.get('Prob'), None)
    if score_val is None:
        score_val = row['Score']

    # 💸 Si la puja prevista se le va del saldo, decir CON QUÉ la pagaría. Es la
    # diferencia entre "no puede permitírselo" y "puede, vendiendo a estos dos".
    saldo_row = _a_float(row.get('Saldo'), 0.0) or 0.0
    bloque_ventas = ""
    if row['Puja'] > saldo_row:
        a_vender = ventas_necesarias(row['Manager'], row['Puja'])
        if a_vender:
            nombres = ", ".join(
                f"<b>{j['Jugador']}</b> ({formato_euro(j['Valor Actual (€)'])})" for j in a_vender
            )
            ingreso = sum(_a_float(j['Valor Actual (€)'], 0.0) or 0.0 for j in a_vender)
            bloque_ventas = (
                f'<div style="margin-top:10px; background:rgba(245,158,11,0.10); '
                f'border-left:3px solid #f59e0b; border-radius:6px; padding:8px 12px; '
                f'color:#fcd34d; font-size:0.88em;">'
                f'💸 Le faltan <b>{formato_euro(row["Puja"] - saldo_row)}</b> '
                f'(tiene {formato_euro(saldo_row)}): tendría que vender a {nombres} '
                f'para reunir {formato_euro(ingreso)}.</div>'
            )
        elif a_vender is None:
            # Antes se le buscaba una combinación mirando la plantilla entera y
            # salían disparates: vender dos defensas para quedarse con diez
            # jugadores y no poder alinear. Si no puede, se dice.
            bloque_ventas = (
                '<div style="margin-top:10px; background:rgba(255,107,107,0.10); '
                'border-left:3px solid #ff6b6b; border-radius:6px; padding:8px 12px; '
                'color:#ffb3b3; font-size:0.88em;">'
                'No puede llegar a esa cifra: ni vendiendo lo que le sobra reúne el dinero, '
                'y bajar de once jugadores lo dejaría sin poder alinear.</div>'
            )

    return f"""
    <div class="fut-card" style="background: rgba(30, 30, 46, 0.8); backdrop-filter: blur(5px); border-left: 5px solid {color_borde}; padding: 15px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.5);">
        <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <h4 style="margin: 0; color: white;">{icono} {row['Manager']}</h4>
            <h3 style="margin: 0; color: {color_borde};">{formato_euro(row['Puja'])}</h3>
        </div>
        <div style="margin-top: 10px; color: #ccc; font-size: 0.95em;">
            <strong>Motivo:</strong> {row['Razon']}
        </div>
        <div style="margin-top: 12px; display: flex; align-items: center;">
            <div style="width: 100%; background: rgba(0,0,0,0.5); height: 8px; border-radius: 4px; overflow: hidden; margin-right: 15px;">
                <div style="width: {score_val}%; background: {color_borde}; height: 100%; border-radius: 4px;"></div>
            </div>
            <span style="color: white; font-weight: bold; font-size: 0.85em;" title="Probabilidad estimada de que este mánager puje">{score_val:.0f}%</span>
        </div>
        {bloque_ventas}
    </div>
    """


# --- 🧠 MOTOR PREDICTIVO 2.0 (AVANZADO) ---
# --- 💰 CUÁNTO PUEDE LLEGAR A PAGAR UN MÁNAGER ---
# Nadie puja solo con el saldo que tiene: si le interesa un jugador, vende. El
# caso que lo destapó: Competa fichó por 15 millones teniendo -2 de saldo, y la
# app ni siquiera lo contaba como pujador posible porque descartaba a todo el
# que no llegase al precio con la caja.
#
# Lo que puede reunir de verdad = saldo + lo que sacaría vendiendo, sin
# desmantelarse: se le exige quedarse con 11 jugadores como mínimo y no se
# cuentan los que tienen el candado de los 10 días, que no se pueden vender.
MIN_PLANTILLA_TRAS_VENDER = 11


def jugadores_vendibles(persona, antes_de_jornada=True, recortar=True):
    """Plantilla de ese mánager quitando lo que no puede vender.

    Por defecto, lo que puede vender ANTES DE QUE EMPIECE LA JORNADA (que es el
    plazo que importa para el dinero), no solo hoy. Con recortar=False no se
    limita a los que le sobran por encima de once: eso lo decide la búsqueda
    de ventas, que ya comprueba que le quede equipo."""
    plantilla = db['plantillas'][db['plantillas']['Participante'] == persona]
    if plantilla.empty:
        return plantilla
    if antes_de_jornada:
        libres = plantilla[[vendible_antes_de_jornada(fila['Jugador'], persona)
                            for _, fila in plantilla.iterrows()]]
    else:
        libres = plantilla[[not dias_para_desbloquear(fila['Jugador'], persona)
                            for _, fila in plantilla.iterrows()]]
    if not recortar:
        return libres
    # Tiene que quedarse con un equipo: como mucho puede vender los que le
    # sobren por encima de once.
    margen = max(0, len(plantilla) - MIN_PLANTILLA_TRAS_VENDER)
    if len(libres) <= margen:
        return libres
    # Se venderían primero los que menos aportan, así que esos son los que
    # marcan su techo real de recaudación.
    libres = libres.assign(_x=[puntos_esperados_jugador(f) for _, f in libres.iterrows()])
    return libres.nsmallest(margen, '_x').drop(columns=['_x'])


def techo_de_puja(persona):
    """Lo máximo que puede llegar a ofrecer sin quedarse sin equipo.

    Saldo más lo que sacaría vendiendo, contando SOLO a quien puede vender de
    verdad: sin el candado de los 10 días y sin bajar de once jugadores, que es
    el mínimo para alinear."""
    fila = db['participantes'][db['participantes']['Persona'] == persona]
    saldo = _a_float(fila.iloc[0].get('Balance Total (€)'), 0.0) if not fila.empty else 0.0
    vendibles = jugadores_vendibles(persona)
    recaudable = (float(pd.to_numeric(vendibles.get('Valor Actual (€)'), errors='coerce')
                        .fillna(0).sum()) if not vendibles.empty else 0.0)
    return (saldo or 0.0) + recaudable


@st.cache_data(show_spinner=False)
def techos_de_la_liga(huella=None):
    """El techo de puja de cada mánager, calculado una vez por versión del Excel."""
    return {str(p).strip(): techo_de_puja(str(p).strip())
            for p in db['participantes']['Persona'].dropna().unique()}


def ventas_necesarias(persona, importe):
    """Qué tendría que vender para llegar a ese importe.

    Lista vacía si le llega con el saldo; None si no le llega NI VENDIENDO lo
    que puede vender.

    Antes, cuando no le salían las cuentas, se buscaba la combinación mirando la
    plantilla entera: eso proponía cosas imposibles, como que Competa vendiera
    dos defensas para quedarse con diez jugadores y no poder alinear. Si no
    llega, no llega, y así hay que decirlo.
    """
    fila = db['participantes'][db['participantes']['Persona'] == persona]
    saldo = _a_float(fila.iloc[0].get('Balance Total (€)'), 0.0) if not fila.empty else 0.0
    deuda = importe - (saldo or 0.0)
    if deuda <= 0:
        return []
    # Hasta 6 y no 4: con saldos muy negativos hacen falta más ventas para
    # cubrir la deuda, y con el tope en 4 se decía "no puede" a mánagers que sí
    # podían (Nike tenía 15,8 M€ vendibles para una deuda de 10,7 M€).
    opciones = buscar_ventas_para_deuda(jugadores_vendibles(persona, recortar=False), deuda,
                                        max_jugadores=6)
    return opciones[0]['jugadores'] if opciones else None


# --- 👥 CUÁNTA GENTE PUJA DE VERDAD ---
# Al dejar que cualquiera financie una puja vendiendo, la lista de pujadores se
# disparó a siete u ocho por subasta. La realidad de esta liga, contada de la
# propia Contabilidad (127 subastas registradas):
#
#   1 pujador → 67 subastas   ·   2 → 28   ·   3 → 19   ·   4 → 9   ·   5 → 4
#
# O sea: la MITAD de las subastas las gana alguien sin que nadie más puje, y el
# máximo histórico es cinco. La media sube con el precio, que es lo lógico:
# 1,31 pujadores por debajo del millón y 3,25 por encima de quince.
#
# Así que ya no se enseña a todo el que "podría" pujar, sino a los que más
# probablemente lo harán, y en la cantidad que marca el histórico. El criterio
# para ordenarlos combina lo que le encaja el jugador (índice de amenaza) con lo
# activo que es ese mánager en el mercado (en cuántas subastas ha pujado).
# --- 🏁 CUÁNTO HAY QUE PASARSE PARA GANAR UNA SUBASTA ---
# El margen no es un número inventado: sale de mirar, en cada subasta disputada
# de la Contabilidad, cuánto se pasó el ganador sobre la mejor puja perdida.
# Se recalcula solo conforme se acumulan subastas, así que el consejo mejora con
# el tiempo en vez de quedarse fijo.
MARGEN_POR_DEFECTO = {50: 0.15, 75: 0.22, 90: 0.40, 'n': 0}


@st.cache_data(show_spinner=False)
def margenes_victoria(huella=None):
    """Percentiles del margen con que se ganan las subastas en esta liga."""
    contabilidad = db.get('contabilidad')
    if contabilidad is None or contabilidad.empty:
        return dict(MARGEN_POR_DEFECTO)
    compras = contabilidad[contabilidad['Tipo de Operación'] == 'Compra']
    margenes = []
    for _, fila in compras.iterrows():
        perdidas = [_a_float(fila.get(f'Subasta perdida {i}'), None) for i in range(1, 10)]
        perdidas = [x for x in perdidas if x and x > 0]
        importe = _a_float(fila.get('Importe (€)'), None)
        if perdidas and importe:
            margenes.append((importe - max(perdidas)) / max(perdidas))
    if len(margenes) < 10:          # con menos de diez no hay de dónde sacar nada
        return dict(MARGEN_POR_DEFECTO)
    serie = pd.Series(margenes)
    return {50: float(serie.quantile(0.50)), 75: float(serie.quantile(0.75)),
            90: float(serie.quantile(0.90)), 'n': len(serie)}


# ==========================================
# 🎯 PREDICTOR DE PUJAS EN DOS ETAPAS
# ==========================================
# Sustituye al sistema anterior, que mezclaba reglas a ojo (índice de amenaza,
# umbrales de saldo, márgenes fijos) con un modelo entrenado solo sobre las
# pujas ganadas. Ahora son dos preguntas separadas, cada una con su modelo y su
# validación contra la realidad:
#
#   A) ¿Pujará este mánager por este jugador?      -> clasificación
#   B) Si puja, ¿cuánto ofrecerá?                  -> regresión
#
# Lo importante es de dónde salen los datos de entrenamiento. Para la etapa A
# hacen falta EJEMPLOS NEGATIVOS: los mánagers que NO pujaron en cada subasta.
# Eso se obtiene cruzando cada subasta con los diez mánagers, y da 1.270 casos
# reales (236 pujas y 1.034 no-pujas) en vez de las 127 filas de ganadores.
#
# Y todas las variables se reconstruyen A LA FECHA DE CADA SUBASTA: quién tenía
# a quién y con cuánto saldo ese día. Contabilidad guarda fecha en todas las
# compras y ventas, así que la plantilla y el saldo de cualquier día se pueden
# rehacer hacia atrás desde los de hoy. Sin eso, el modelo entrenaría con
# información del futuro y las cifras de validación serían mentira.
#
# VALIDACIÓN TEMPORAL (cada subasta predicha usando solo las anteriores, que es
# la situación real de adelantarse a una puja), 25/09/2026, 208 subastas:
#
#   Etapa A: AUC 0,716  ·  frente a 0,573 usando solo lo activo que es cada uno
#
# La etapa B (un número de cuánto pujará) se queda solo como referencia en la
# validación: en la app manda la distribución de pujas de cada mánager (abajo).

# Revisado el 25/09/2026 con 196 subastas y todas las pujas (ganadas y
# perdidas). La etapa A pasa a usar cómo estaba el jugador EL DÍA de la subasta
# (puntos, media y subida de precio de esa semana, sacados del Histórico) en vez
# de sus puntos de hoy, que eran información del futuro: AUC 0,692 -> 0,710 en
# validación temporal con tres semillas.
#
# Probadas y DESCARTADAS por medición (ninguna mueve el AUC más allá del ruido):
# si le falta gente o titulares en esa posición, cuánto mejoraría su once, su
# ritmo de pujas de la última semana, su gusto por la posición o por ese rango
# de precio, los días desde su última puja, si ya pujó antes por ese jugador,
# 'hueco_posicion' y 'dias_sin_comprar'. Se siguen calculando donde ya estaban.
FEATURES_PUJA_A = ['log_valor', 'plantilla', 'en_posicion',
                   'tasa_previa', 'pujas_previas', 'victorias_previas',
                   'sobrepuja_previa', 'saldo', 'saldo_sobre_valor', 'le_llega',
                   'media_asof', 'pts_asof', 'tend7']
FEATURES_PUJA_B = ['log_valor', 'media_asof', 'pts_asof', 'tend7', 'plantilla', 'en_posicion',
                   'tasa_previa', 'sobrepuja_previa', 'saldo_sobre_valor']

# CUÁNTO PUJA CADA UNO. Para la puja ya no se usa un número por mánager sino
# TODAS sus sobrepujas pasadas (su distribución), encogida hacia la de la liga
# con K=5 pujas: con pocas pujas manda la liga, con muchas manda lo suyo. Un
# número solo (la etapa B) no decía nada del riesgo, y el modelo de boosting
# apenas mejoraba a la mediana (15,12 frente a 15,33 puntos de error).
K_SOBREPUJA_PERSONAL = 5

# Probabilidad de ganar con una puja b: que cada rival, o no puje, o puje por
# debajo de b (y nadie puede pasar de su techo):
#       P(ganar con b) = Π  (1 - p_i + p_i · F_i(b))
# Medido en las 148 subastas con rivales (validación temporal): el precio del
# ganador quedó por debajo de las tres pujas el 30% / 59% / 78% de las veces
# (lo ideal 25 / 50 / 75). El sistema anterior, márgenes de la liga sobre la
# mayor puja esperada, se quedaba en 44% / 53% / 55%: su "segura" ganaba poco
# más de la mitad. Error de cuantiles 0,112 -> 0,077.
# Las probabilidades de pujar están bien calibradas: los que el modelo da al
# 14% pujan el 16%; al 24%, el 24%; al 36%, el 32%.
OBJETIVOS_PUJA = (("Arriesgada", 0.25), ("La justa", 0.50), ("Segura", 0.75))

# Listón para aparecer en la lista de pujadores. Solo decide a quién se
# ENSEÑA: las pujas recomendadas cuentan con todos los rivales, cada uno con su
# probabilidad. Ajustado el 25/09/2026 sobre los 379 libres del día para que la
# media de rivales enseñados (1,49) case con la de rivales esperados según el
# modelo (1,37): con 0,32 salían 0,60 y con 0,20, 1,91.
UMBRAL_PROB_PUJA = 0.25
MIN_SUBASTAS_MODELO = 30


def _pos_principal(valor):
    return str(valor).split('/')[0].strip()


@st.cache_data(show_spinner=False, persist="disk")
def construir_dataset_pujas(huella=None):
    """Una fila por (subasta, mánager) con lo que se sabía ANTES de esa subasta."""
    conta = db.get('contabilidad')
    plantillas = db.get('plantillas')
    if conta is None or conta.empty or plantillas is None:
        return pd.DataFrame()

    conta = conta.dropna(subset=['Tipo de Operación']).copy()
    conta['_fecha'] = pd.to_datetime(conta.get('Fecha Fichaje'), errors='coerce')
    # 🗓️ Fuera las fechas imposibles. Al teclear una fecha mal, Excel la
    # convierte en enero de 1900, y esas filas se colocaban las PRIMERAS de
    # todo: el modelo daba por hecho que esas compras fueron antes que ninguna
    # otra y reconstruía mal las plantillas y los saldos de ese momento.
    conta = conta[conta['_fecha'] >= pd.Timestamp('2000-01-01')]
    conta = conta.dropna(subset=['_fecha'])
    if conta.empty:
        return pd.DataFrame()

    managers = sorted(db['participantes']['Persona'].dropna().unique().tolist())
    mercado = db['mercado'].dropna(subset=['Jugador']).copy()
    mercado['_k'] = mercado['Jugador'].astype(str).str.strip()
    info_jugador = mercado.drop_duplicates('_k').set_index('_k')
    pos_de = {k: _pos_principal(v) for k, v in info_jugador['Posición'].items()}

    movimientos = sorted(
        ({'fecha': f['_fecha'], 'tipo': f['Tipo de Operación'],
          'persona': str(f['Persona']).strip() if pd.notna(f['Persona']) else '',
          'jugador': str(f['Jugador']).strip() if pd.notna(f['Jugador']) else None,
          'importe': _a_float(f.get('Importe (€)'), 0.0) or 0.0}
         for _, f in conta.iterrows()),
        key=lambda x: x['fecha'])

    # Estado inicial: lo que tiene hoy, deshaciendo todos los movimientos.
    plantel_ini, saldo_ini = {}, {}
    for _, f in plantillas.dropna(subset=['Jugador', 'Participante']).iterrows():
        plantel_ini.setdefault(str(f['Participante']).strip(), set()).add(str(f['Jugador']).strip())
    plantel_ini = {m: set(plantel_ini.get(m, set())) for m in managers}
    for _, f in db['participantes'].dropna(subset=['Persona']).iterrows():
        saldo_ini[str(f['Persona']).strip()] = _a_float(f.get('Balance Total (€)'), 0.0) or 0.0
    for mov in movimientos:
        if mov['persona'] not in plantel_ini:
            continue
        if mov['tipo'] == 'Compra':
            if mov['jugador']:
                plantel_ini[mov['persona']].discard(mov['jugador'])
            saldo_ini[mov['persona']] += mov['importe']
        else:
            if mov['jugador']:
                plantel_ini[mov['persona']].add(mov['jugador'])
            saldo_ini[mov['persona']] -= mov['importe']

    subastas = conta[conta['Tipo de Operación'] == 'Compra'].sort_values('_fecha')
    plantel = {m: set(v) for m, v in plantel_ini.items()}
    saldos = dict(saldo_ini)
    idx_mov = 0
    veces_pujo = {m: 0 for m in managers}
    suma_sobre = {m: 0.0 for m in managers}
    veces_gano = {m: 0 for m in managers}
    ultima_compra = {}
    filas = []

    for orden, (_, sub) in enumerate(subastas.iterrows()):
        fecha = sub['_fecha']
        # Se aplican los movimientos anteriores a esta subasta (van en orden,
        # así que basta con avanzar el índice: no se recorre la lista entera
        # por cada subasta).
        while idx_mov < len(movimientos) and movimientos[idx_mov]['fecha'] < fecha:
            mov = movimientos[idx_mov]
            if mov['persona'] in plantel:
                if mov['tipo'] == 'Compra':
                    if mov['jugador']:
                        plantel[mov['persona']].add(mov['jugador'])
                    saldos[mov['persona']] -= mov['importe']
                else:
                    if mov['jugador']:
                        plantel[mov['persona']].discard(mov['jugador'])
                    saldos[mov['persona']] += mov['importe']
            idx_mov += 1

        jugador = str(sub['Jugador']).strip() if pd.notna(sub['Jugador']) else None
        valor = _a_float(sub.get('Valor Mercado (€)'), None)
        if not jugador or not valor or valor <= 0:
            continue
        pos_jug = pos_de.get(jugador, '')
        info = info_jugador.loc[jugador] if jugador in info_jugador.index else None

        pujas = {}
        ganador = str(sub['Persona']).strip() if pd.notna(sub['Persona']) else ''
        pujas[ganador] = _a_float(sub.get('Importe (€)'), None)
        for i in range(1, 10):
            quien = sub.get(f'Manager {i}')
            if pd.notna(quien) and str(quien).strip():
                pujas[str(quien).strip()] = _a_float(sub.get(f'Subasta perdida {i}'), None)

        for manager in managers:
            mios = plantel.get(manager, set())
            saldo_m = saldos.get(manager, 0.0)
            en_pos = sum(1 for j in mios if pos_de.get(j, '') == pos_jug)
            # ¿Le falta gente en esa posición para poder alinear? Un mánager con
            # un solo portero mira los porteros de otra manera.
            minimos = {'Portero': 2, 'Defensa': 5, 'Centrocampista': 5, 'Delantero': 3}
            hueco = 1 if en_pos < minimos.get(pos_jug, 4) else 0
            # 🥅 Cuántos de esa posición JUEGAN de verdad. Contar cuántos tiene
            # no basta: solo un portero sale al campo, así que quien ya tiene uno
            # bueno tiene la portería resuelta y un segundo portero caro es
            # dinero parado en el banquillo. En cambio ir cuarto de cinco medios
            # sí deja hueco. 'suplentes_pos' es cuántos le sobrarían en esa línea
            # si fichara a este: cuanto más alto, menos sentido tiene el fichaje.
            # Probada en el modelo y NO aporta (AUC 0,689 -> 0,691, ruido): los
            # mánagers de verdad SÍ compran suplentes caros. Se deja calculada
            # por si con más subastas empieza a valer, y el aviso de dinero
            # parado se da donde sí corresponde, en las recomendaciones propias.
            titulares_pos = {'Portero': 1, 'Defensa': 4, 'Centrocampista': 4, 'Delantero': 2}
            suplentes_pos = max(0, (en_pos + 1) - titulares_pos.get(pos_jug, 4))
            # Cuántos días lleva sin comprar: quien acaba de fichar suele estar
            # sin saldo y sin ganas, y quien lleva semanas quieto está esperando.
            ultima = ultima_compra.get(manager)
            dias_sin_comprar = (fecha - ultima).days if ultima is not None else 30
            filas.append({
                'orden': orden, 'manager': manager, 'valor': valor,
                'fecha': fecha, 'jugador': jugador, 'mios_asof': tuple(sorted(mios)),
                'equipo': str(sub.get('Equipo') or '').strip(),
                'ganador': ganador,
                'log_valor': np.log10(valor),
                'pos': pos_jug,
                'puntos': _a_float(info.get('Puntos'), 0.0) if info is not None else 0.0,
                'media': _a_float(info.get('Media Puntos'), 0.0) if info is not None else 0.0,
                'plantilla': len(mios),
                'en_posicion': en_pos,
                'hueco_posicion': hueco,
                'suplentes_pos': suplentes_pos,
                'dias_sin_comprar': min(30, dias_sin_comprar),
                'saldo': saldo_m,
                'saldo_sobre_valor': saldo_m / valor,
                'le_llega': 1 if saldo_m >= valor else 0,
                'tasa_previa': veces_pujo[manager] / max(1, orden),
                'sobrepuja_previa': (suma_sobre[manager] / veces_pujo[manager]) if veces_pujo[manager] else np.nan,
                'pujas_previas': veces_pujo[manager],
                'victorias_previas': veces_gano[manager],
                'pujo': 1 if manager in pujas else 0,
                'sobrepuja': ((pujas[manager] - valor) / valor) if pujas.get(manager) else np.nan,
            })

        for quien, cuanto in pujas.items():
            if quien in veces_pujo:
                veces_pujo[quien] += 1
                if cuanto:
                    suma_sobre[quien] += (cuanto - valor) / valor
        if ganador in veces_gano:
            veces_gano[ganador] += 1
        ultima_compra[ganador] = fecha

    return _variables_jugador_asof(_variables_del_dia(pd.DataFrame(filas)))


@st.cache_resource(show_spinner=False)
def _fotos_del_historico(huella=None):
    """(fechas ordenadas, {fecha: {jugador: (puntos, media, valor)}}) del Histórico.

    Se guarda una vez por versión del Excel: rehacerlo en cada jugador costaba
    0,2 s por consulta y la lista de fichajes consulta decenas."""
    try:
        hist = cargar_historico_completo(huella)
    except Exception:
        return [], {}
    if hist is None or hist.empty:
        return [], {}
    h = hist.dropna(subset=['Fecha', 'Jugador'])
    fotos = {}
    for fecha, dia in h.groupby('Fecha'):
        dia = dia.drop_duplicates('Jugador')
        fotos[pd.Timestamp(fecha)] = {
            str(j).strip(): (_a_float(p, None), _a_float(m, None), _a_float(v, None))
            for j, p, m, v in zip(dia['Jugador'], dia['Puntos'], dia['Media Puntos'], dia['Valor Actual (€)'])}
    return sorted(fotos), fotos


def _foto_anterior(fechas, fotos, fecha):
    """La última foto del Histórico ESTRICTAMENTE anterior a `fecha`."""
    i = bisect.bisect_left(fechas, pd.Timestamp(fecha)) - 1
    return fotos[fechas[i]] if i >= 0 else None


def _variables_jugador_asof(datos):
    """Cómo estaba el jugador EL DÍA de su subasta, no cómo está hoy.

    Antes el modelo aprendía con los puntos y la media de HOY de cada jugador
    subastado: para una subasta de agosto usaba lo que el jugador hizo en
    septiembre. Eso es mirar el futuro, y además no dice nada de lo que vio el
    mánager al pujar. Ahora cada subasta lleva la foto del Histórico del día
    anterior: sus puntos, su media y cuánto había subido su precio esa semana.

    Medido con validación temporal (cada subasta con solo las anteriores, tres
    semillas): AUC 0,692 -> 0,710. La subida de la última semana es de lo que
    más pesa: los que están subiendo atraen pujas.
    """
    if datos.empty:
        return datos
    fechas, fotos = _fotos_del_historico(_huella_excel(resolver_excel_path()))
    extra = {}
    for orden, fecha, jugador in datos.drop_duplicates('orden')[['orden', 'fecha', 'jugador']].itertuples(index=False):
        hoy = _foto_anterior(fechas, fotos, fecha) if fechas else None
        antes = _foto_anterior(fechas, fotos, pd.Timestamp(fecha) - pd.Timedelta(days=7)) if fechas else None
        pts = media = tend = np.nan
        if hoy and jugador in hoy:
            pts, media, valor = hoy[jugador]
            if antes and jugador in antes and antes[jugador][2] and valor:
                tend = valor / antes[jugador][2] - 1
        extra[orden] = (pts, media, tend)
    d = datos.copy()
    d['pts_asof'] = [extra[o][0] for o in d['orden']]
    d['media_asof'] = [extra[o][1] for o in d['orden']]
    d['tend7'] = [extra[o][2] for o in d['orden']]
    return _limpiar_asof(d)


def _limpiar_asof(d):
    d['pts_asof'] = pd.to_numeric(d['pts_asof'], errors='coerce').fillna(0.0)
    d['media_asof'] = pd.to_numeric(d['media_asof'], errors='coerce').fillna(0.0)
    d['tend7'] = pd.to_numeric(d['tend7'], errors='coerce').clip(-0.5, 2.0).fillna(0.0)
    return d


def _variables_del_dia(datos):
    """El mercado del día entero, no cada subasta por su cuenta.

    La idea era que un mánager no decide subasta a subasta: mira las opciones
    que hay esa noche y reparte entre ellas su atención y su saldo. Suena
    razonable, así que se midió contra sus datos (192 subastas, 47 días de
    mercado, 1.920 decisiones) y NO se sostiene:

      · La tasa de puja por subasta NO baja cuando hay más opciones. Con una
        sola opción se puja el 10% de las veces; con 3, el 20%; con 8, el 20%;
        con 11, el 21%. Si hubiera una atención fija que repartir, esa tasa
        tendría que caer al haber más donde elegir. No cae: más mercado es
        simplemente más pujas.
      · Tampoco reparten el saldo. De los 81 mánager-días con dos o más pujas,
        en 33 la suma de lo pujado SUPERA su saldo de ese día. Pujan a varios
        sabiendo que no los van a ganar todos, así que un tope del tipo "lo que
        puje hoy no puede sumar más que su techo" sería falso: castigaría algo
        que hacen a propósito. El freno correcto a nivel de día es el gasto
        ESPERADO (probabilidad × importe), no la suma bruta.
      · Y como variables del clasificador tampoco aportan: con una semilla
        subían el AUC 0,011, pero repetido con tres semillas la base gana
        (0,687 frente a 0,674 con las tres mejores y 0,671 con las ocho). Era
        ruido, como ya pasó con 'hueco_posicion' y 'dias_sin_comprar'.

    Se quedan calculadas y fuera de FEATURES_PUJA_A, por si con muchas más
    subastas empiezan a decir algo: para probarlas basta con añadirlas ahí.
    """
    if datos.empty or 'fecha' not in datos.columns:
        return datos

    d = datos.copy()
    dia = pd.to_datetime(d['fecha'], errors='coerce').dt.normalize()
    # Catálogo de opciones de cada noche: una fila por subasta.
    opciones = d.assign(_dia=dia).drop_duplicates(['_dia', 'orden'])[['_dia', 'orden', 'valor', 'pos']].copy()
    por_dia = opciones.groupby('_dia')
    opciones['_n'] = por_dia['orden'].transform('size')
    opciones['_total'] = por_dia['valor'].transform('sum')
    opciones['_rango'] = por_dia['valor'].rank(ascending=False, method='min')
    opciones['_rango_rel'] = (opciones['_rango'] - 1) / np.maximum(1, opciones['_n'] - 1)
    opciones['_cuota'] = opciones['valor'] / opciones['_total'].replace(0, np.nan)
    por_pos = opciones.groupby(['_dia', 'pos'])
    opciones['_n_pos'] = por_pos['orden'].transform('size')
    opciones['_mejor_pos'] = (por_pos['valor'].rank(ascending=False, method='min') == 1).astype(int)

    d = d.merge(opciones[['orden', '_n', '_total', '_rango_rel', '_cuota',
                          '_n_pos', '_mejor_pos']], on='orden', how='left')
    d['opciones_dia'] = d['_n']
    d['rango_valor_dia'] = d['_rango_rel']
    d['cuota_valor_dia'] = d['_cuota']
    d['es_el_mas_caro'] = (d['_rango_rel'] == 0).astype(int)
    d['mejor_de_su_pos_dia'] = d['_mejor_pos']
    d['rivales_misma_pos_dia'] = d['_n_pos']
    d['saldo_sobre_dia'] = d['saldo'] / d['_total'].replace(0, np.nan)
    return d.drop(columns=[c for c in d.columns if c.startswith('_')])


def _matriz(df, columnas, referencia=None):
    X = pd.get_dummies(df[columnas + ['pos']], columns=['pos'])
    X = X.fillna(X.median(numeric_only=True)).fillna(0)
    if referencia is not None:
        X = X.reindex(columns=referencia, fill_value=0)
    return X


@st.cache_resource
def entrenar_modelos_puja(huella=None):
    """(modelo de si puja, modelo de cuánto, columnas, medias de referencia)."""
    datos = construir_dataset_pujas(huella)
    if datos.empty or datos['orden'].nunique() < MIN_SUBASTAS_MODELO:
        return None

    X_a = _matriz(datos, FEATURES_PUJA_A)
    clasificador = GradientBoostingClassifier(n_estimators=120, max_depth=3,
                                              learning_rate=0.05, random_state=42)
    clasificador.fit(X_a, datos['pujo'])

    positivos = datos[datos['pujo'] == 1].dropna(subset=['sobrepuja'])
    regresor, cols_b = None, None
    if len(positivos) >= 20:
        X_b = _matriz(positivos, FEATURES_PUJA_B)
        cols_b = list(X_b.columns)
        # Error absoluto y no cuadrático: se está midiendo con el error medio,
        # y minimizar esa misma métrica fue lo que mejor funcionó (12,08 puntos
        # frente a 13,23 del bosque que había antes).
        regresor = GradientBoostingRegressor(loss='absolute_error', n_estimators=250,
                                             max_depth=2, learning_rate=0.05,
                                             random_state=42)
        regresor.fit(X_b, positivos['sobrepuja'])

    return {'clf': clasificador, 'cols_a': list(X_a.columns),
            'reg': regresor, 'cols_b': cols_b,
            'sobrepuja_media': float(positivos['sobrepuja'].median()) if len(positivos) else 0.15}


@st.cache_data(show_spinner=False, persist="disk")
def validar_modelos_puja(huella=None):
    """Comprueba cuánto acierta el predictor, hacia atrás en el tiempo.

    Cada subasta se predice usando SOLO las anteriores, que es la situación real
    de adelantarse a una puja. Se salta de tres en tres para que la comprobación
    no eternice: la cifra apenas cambia y el tiempo se divide por tres."""
    try:
        from sklearn.metrics import roc_auc_score
        datos = construir_dataset_pujas(huella)
        if datos.empty or datos['orden'].nunique() < MIN_SUBASTAS_MODELO + 10:
            return None

        ordenes = sorted(datos['orden'].unique())
        reales, probs, sobre_real, sobre_pred, tasas = [], [], [], [], []
        for corte in ordenes[MIN_SUBASTAS_MODELO::3]:
            train = datos[datos['orden'] < corte]
            test = datos[datos['orden'] == corte]
            if train['pujo'].sum() < 15 or test.empty:
                continue
            X = _matriz(train, FEATURES_PUJA_A)
            Xt = _matriz(test, FEATURES_PUJA_A, list(X.columns))
            clf = GradientBoostingClassifier(n_estimators=120, max_depth=3,
                                             learning_rate=0.05, random_state=42)
            clf.fit(X, train['pujo'])
            p = clf.predict_proba(Xt)[:, 1]
            reales += list(test['pujo']); probs += list(p); tasas += list(test['tasa_previa'])

            positivos = train[train['pujo'] == 1].dropna(subset=['sobrepuja'])
            testpos = test[test['pujo'] == 1].dropna(subset=['sobrepuja'])
            if len(positivos) >= 20 and not testpos.empty:
                Xb = _matriz(positivos, FEATURES_PUJA_B)
                Xbt = _matriz(testpos, FEATURES_PUJA_B, list(Xb.columns))
                reg = GradientBoostingRegressor(loss='absolute_error', n_estimators=250,
                                                max_depth=2, learning_rate=0.05, random_state=42)
                reg.fit(Xb, positivos['sobrepuja'])
                sobre_pred += list(np.maximum(0, reg.predict(Xbt)))
                sobre_real += list(testpos['sobrepuja'])

        if len(reales) < 50 or len(set(reales)) < 2:
            return None
        mediana = float(np.median(sobre_real)) if sobre_real else 0.0
        return {
            'subastas': len(set(ordenes[MIN_SUBASTAS_MODELO::3])),
            'decisiones': len(reales),
            'auc': float(roc_auc_score(reales, probs)),
            'auc_base': float(roc_auc_score(reales, tasas)),
            'mae': float(np.mean(np.abs(np.array(sobre_real) - np.array(sobre_pred)))) if sobre_pred else float('nan'),
            'mae_base': float(np.mean(np.abs(np.array(sobre_real) - mediana))) if sobre_real else float('nan'),
        }
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def perfiles_de_puja(huella=None):
    """Cómo puja cada mánager, sacado de TODAS sus pujas (ganadas y perdidas).

    {'_liga': sobrepujas de la liga, manager: {'sobrepujas', 'pujas',
    'subastas', 'ganadas', 'tasa'}}. Las sobrepujas van en tanto por uno sobre
    el valor de mercado del día (0,15 = un 15% por encima)."""
    datos = construir_dataset_pujas(huella)
    if datos.empty:
        return {'_liga': np.array([])}
    perfiles = {'_liga': np.sort(datos.loc[datos['pujo'] == 1, 'sobrepuja'].dropna().to_numpy())}
    subastas = datos['orden'].nunique()
    ganadores = datos.drop_duplicates('orden')['ganador'].value_counts().to_dict()
    for manager, grupo in datos.groupby('manager'):
        suyas = grupo[grupo['pujo'] == 1]
        perfiles[manager] = {
            'sobrepujas': np.sort(suyas['sobrepuja'].dropna().to_numpy()),
            'pujas': int(len(suyas)),
            'subastas': int(subastas),
            'ganadas': int(ganadores.get(manager, 0)),
            'tasa': len(suyas) / max(1, subastas),
        }
    return perfiles


def _cdf_sobrepuja(perfil, liga, rejilla):
    """F(s): probabilidad de que su puja quede por debajo de s, encogida a la liga."""
    def ecdf(v):
        return (np.searchsorted(v, rejilla, side='right') / len(v)) if len(v) else (rejilla >= 0).astype(float)
    F_liga = ecdf(liga)
    suyas = perfil.get('sobrepujas', np.array([])) if perfil else np.array([])
    n = len(suyas)
    if not n:
        return F_liga
    return (n * ecdf(suyas) + K_SOBREPUJA_PERSONAL * F_liga) / (n + K_SOBREPUJA_PERSONAL)


def _cuantil_de_cdf(rejilla, F, q):
    i = int(np.searchsorted(F, q, side='left'))
    return float(rejilla[min(i, len(rejilla) - 1)])


def _tendencia_7_dias(nombre, valor_hoy):
    fechas, fotos = _fotos_del_historico(_huella_excel(resolver_excel_path()))
    if not fechas or not valor_hoy:
        return 0.0
    antes = _foto_anterior(fechas, fotos, fechas[-1] - pd.Timedelta(days=6))
    if antes and nombre in antes and antes[nombre][2]:
        return float(np.clip(valor_hoy / antes[nombre][2] - 1, -0.5, 2.0))
    return 0.0


REJILLA_SOBREPUJA = np.round(np.arange(0.0, 2.0001, 0.0025), 4)


def predecir_amenazas(jugador_nombre, equipo=None):
    """Quién pujará por este jugador, cuánto suele ofrecer cada uno y cuánto
    hay que pujar para ganar con cada probabilidad.

    Devuelve (rivales que pasan el listón, fila del jugador). En .attrs van
    'curva' (pujas en €, probabilidad de ganar con cada una), 'p_nadie',
    'todos' (todos los rivales con su probabilidad) y 'mas_probable'."""
    candidatos = db['mercado'][db['mercado']['Jugador'] == jugador_nombre]
    if equipo is not None:
        exactos = candidatos[candidatos['Equipo'] == equipo]
        if not exactos.empty:
            candidatos = exactos
    if candidatos.empty:
        return pd.DataFrame(), pd.Series(dtype=object)
    jugador = candidatos.iloc[0]

    # Si ya tiene dueño no está en subasta: no hay pujas que predecir.
    estado = str(jugador.get('Estado', '')).strip().lower()
    if estado and estado not in ('libre', 'nan', 'none'):
        return pd.DataFrame(), jugador

    valor = _a_float(jugador.get('Valor Actual (€)'), 0.0) or 1.0
    huella = _huella_pujas(db.get('contabilidad'))
    modelos = entrenar_modelos_puja(huella)
    if not modelos:
        return pd.DataFrame(), jugador
    datos = construir_dataset_pujas(huella)
    perfiles = perfiles_de_puja(huella)
    pos_jug = _pos_principal(jugador.get('Posición'))
    subastas_totales = max(1, datos['orden'].nunique()) if not datos.empty else 1

    # Historial de cada mánager hasta HOY, que es lo que sabremos en la próxima
    # subasta: cuántas veces ha pujado, cuántas ganó y cuánto suele sobrepujar.
    historial = {}
    if not datos.empty:
        for manager, grupo in datos.groupby('manager'):
            pujadas = grupo[grupo['pujo'] == 1]
            historial[manager] = {
                'pujas_previas': len(pujadas),
                'tasa_previa': len(pujadas) / subastas_totales,
                'victorias_previas': float(perfiles.get(manager, {}).get('ganadas', 0)),
                'sobrepuja_previa': float(pujadas['sobrepuja'].mean()) if len(pujadas) else np.nan,
            }

    nombre_j = str(jugador.get('Jugador')).strip()
    tend7 = _tendencia_7_dias(nombre_j, valor)
    filas = []
    for _, m in db['participantes'].dropna(subset=['Persona']).iterrows():
        nombre = str(m['Persona']).strip()
        # Tú no compites contigo mismo.
        if nombre == MI_EQUIPO:
            continue
        plantilla = db['plantillas'][db['plantillas']['Participante'] == nombre]
        saldo = _a_float(m.get('Balance Total (€)'), 0.0) or 0.0
        h = historial.get(nombre, {'pujas_previas': 0, 'tasa_previa': 0.0,
                                   'victorias_previas': 0, 'sobrepuja_previa': np.nan})
        filas.append({
            'manager': nombre, 'pos': pos_jug, 'valor': valor,
            'log_valor': np.log10(max(1.0, valor)),
            'pts_asof': _a_float(jugador.get('Puntos'), 0.0) or 0.0,
            'media_asof': _a_float(jugador.get('Media Puntos'), 0.0) or 0.0,
            'tend7': tend7,
            'plantilla': len(plantilla),
            'en_posicion': int(sum(1 for _, j in plantilla.iterrows()
                                   if _pos_principal(j.get('Posición')) == pos_jug)),
            'saldo': saldo,
            'saldo_sobre_valor': saldo / valor,
            'le_llega': 1 if saldo >= valor else 0,
            **h,
        })

    hoy = pd.DataFrame(filas)
    if hoy.empty:
        return pd.DataFrame(), jugador

    # Etapa A: probabilidad de que cada uno entre en la puja.
    X_a = _matriz(hoy, FEATURES_PUJA_A, modelos['cols_a'])
    hoy['Prob'] = modelos['clf'].predict_proba(X_a)[:, 1] * 100

    # 💰 Nadie puede ofrecer más de lo que puede reunir, y quien no llega ni al
    # valor de mercado ni siquiera puede entrar en la subasta.
    techos = techos_de_la_liga(_huella_excel(resolver_excel_path()))
    hoy['Techo'] = [techos[n] if n in techos else techo_de_puja(n) for n in hoy['manager']]
    hoy.loc[hoy['Techo'] < valor, 'Prob'] = 0.0

    # Cuánto ofrecería cada uno si entra: su distribución de sobrepujas,
    # recortada por su techo (por encima de su techo no te puede ganar).
    rejilla = REJILLA_SOBREPUJA
    pujas_rejilla = valor * (1 + rejilla)
    liga = perfiles.get('_liga', np.array([]))
    p_ganar = np.ones_like(rejilla)
    tipicas, bajas, altas = [], [], []
    for _, fila in hoy.iterrows():
        F = _cdf_sobrepuja(perfiles.get(fila['manager']), liga, rejilla)
        F = np.where(pujas_rejilla >= fila['Techo'], 1.0, F)
        p = fila['Prob'] / 100
        p_ganar *= (1 - p + p * F)
        tope = fila['Techo']
        tipicas.append(min(tope, valor * (1 + _cuantil_de_cdf(rejilla, F, 0.50))))
        bajas.append(min(tope, valor * (1 + _cuantil_de_cdf(rejilla, F, 0.25))))
        altas.append(min(tope, valor * (1 + _cuantil_de_cdf(rejilla, F, 0.75))))
    hoy['Puja'] = np.round(tipicas, -3)
    hoy['Puja_baja'] = np.round(bajas, -3)
    hoy['Puja_alta'] = np.round(altas, -3)
    hoy['Sobrepuja_pct'] = (hoy['Puja'] / valor - 1) * 100
    hoy['Saldo'] = hoy['saldo']

    def _perfil(n, clave, defecto=0):
        return perfiles.get(n, {}).get(clave, defecto)
    hoy['Tasa'] = [100 * _perfil(n, 'tasa', 0.0) for n in hoy['manager']]
    hoy['Pujas'] = [_perfil(n, 'pujas') for n in hoy['manager']]
    hoy['Ganadas'] = [_perfil(n, 'ganadas') for n in hoy['manager']]
    hoy['Sobre_mediana'] = [float(np.median(_perfil(n, 'sobrepujas', np.array([]))) * 100)
                            if len(_perfil(n, 'sobrepujas', np.array([]))) else np.nan
                            for n in hoy['manager']]

    todos = hoy.rename(columns={'manager': 'Manager'}).sort_values('Prob', ascending=False)
    todos['Score'] = todos['Prob']
    todos['Razon'] = ''
    elegidos = todos[todos['Prob'] >= UMBRAL_PROB_PUJA * 100].head(5).copy()
    columnas = ['Manager', 'Score', 'Prob', 'Puja', 'Puja_baja', 'Puja_alta', 'Razon', 'Saldo',
                'Sobrepuja_pct', 'Techo', 'Tasa', 'Pujas', 'Ganadas', 'Sobre_mediana']
    resultado = elegidos[columnas].sort_values('Prob', ascending=False)
    resultado.attrs['curva'] = (pujas_rejilla, p_ganar)
    resultado.attrs['p_nadie'] = float(np.prod(1 - todos['Prob'].to_numpy() / 100))
    resultado.attrs['todos'] = todos[columnas].reset_index(drop=True)
    activos = todos[todos['Prob'] > 0]
    if not activos.empty:
        mejor = activos.iloc[0]
        resultado.attrs['mas_probable'] = (mejor['Manager'], float(mejor['Prob']), float(mejor['Puja']))
    return resultado, jugador


def pujas_para_ganar(amenazas, valor):
    """[(nombre, puja, prob. de ganar)] para los objetivos de OBJETIVOS_PUJA."""
    curva = amenazas.attrs.get('curva') if amenazas is not None else None
    if not curva:
        return [(n, valor, 1.0) for n, _ in OBJETIVOS_PUJA]
    pujas, prob = curva
    salida = []
    for nombre, objetivo in OBJETIVOS_PUJA:
        i = int(np.searchsorted(prob, objetivo, side='left'))
        i = min(i, len(pujas) - 1)
        # Se redondea hacia arriba a los mil euros, como se puja en Biwenger.
        puja = float(np.ceil(pujas[i] / 1000) * 1000)
        salida.append((nombre, puja, float(prob[i])))
    return salida


FORMACIONES_VALIDAS = [(3, 4, 3), (3, 5, 2), (4, 3, 3), (4, 4, 2), (4, 5, 1), (5, 3, 2), (5, 4, 1)]


def calcular_mejor_once(plantilla):
    """Mejor once posible de una plantilla, maximizando puntos esperados.

    Estaba escrito dentro de ui_rival y solo se podía usar con el mánager que
    estuvieras mirando. Sacándolo aquí se puede calcular también el tuyo y
    compararlos, que es justo lo que uno quiere saber en esta pestaña.

    Devuelve (formación, once por líneas, lista plana de titulares).
    """
    vacio = {'POR': [], 'DEF': [], 'MED': [], 'DEL': []}
    if plantilla is None or plantilla.empty:
        return "Formación", vacio, []

    plant_sorted = plantilla.sort_values(by='Valor Actual (€)', ascending=False)
    players = plant_sorted[plant_sorted['Lesion'] != 'si'].to_dict('records')
    if not players:
        return "Formación", vacio, []

    def get_pos_weight(pos):
        if pos == 'Portero': return 1.0004
        if pos == 'Defensa': return 1.0003
        if pos == 'Centrocampista': return 1.0002
        if pos == 'Delantero': return 1.0001
        return 1.0

    # 🔮 OBJETIVO DEL OPTIMIZADOR: PUNTOS ESPERADOS
    # Antes se maximizaba el valor de mercado del once (ajustado por posición,
    # fixture y localía). El precio es un proxy razonable de calidad, pero no
    # es rendimiento: un jugador caro en mala racha seguía ganando el puesto.
    # Ahora se maximiza lo que se espera que puntúe cada uno en su próximo
    # partido — media casa/fuera corregida por muestra, dificultad del rival y
    # racha del equipo — y el precio solo entra por la puerta de atrás, como
    # prior, cuando el jugador no tiene partidos suficientes.
    #
    # Se calcula UNA vez por jugador (antes los pesos se recalculaban dentro
    # de cada estado de la recursión, miles de veces por formación).
    xpts = [puntos_esperados_jugador(p) for p in players]
    for p, xp in zip(players, xpts):
        p['_xPts'] = round(xp, 2)   # métrica interna: no se muestra en pantalla

    # Bonus por hueco cubierto: alinear a alguien siempre compensa (un hueco
    # vacío son -4 puntos en Biwenger), así que el optimizador prioriza el
    # once completo y solo después maximiza puntos.
    BONUS_HUECO = 1000.0

    best_weighted_value = -1
    best_form = "Formación"
    best_xi = dict(vacio)

    for (d, m, f) in FORMACIONES_VALIDAS:
        memo = {}

        def solve_xi(idx, p_req, d_req, m_req, f_req):
            if idx == len(players):
                return 0, {'Portero': [], 'Defensa': [], 'Centrocampista': [], 'Delantero': []}
            state = (idx, p_req, d_req, m_req, f_req)
            if state in memo:
                return memo[state]

            max_val, assign_skip = solve_xi(idx + 1, p_req, d_req, m_req, f_req)
            best_assign = {k: v[:] for k, v in assign_skip.items()}

            player = players[idx]
            pos_list = [pos.strip() for pos in str(player['Posición']).split('/')]

            for pos in pos_list:
                np_req, nd_req, nm_req, nf_req = p_req, d_req, m_req, f_req
                if pos == 'Portero' and p_req > 0: np_req -= 1
                elif pos == 'Defensa' and d_req > 0: nd_req -= 1
                elif pos == 'Centrocampista' and m_req > 0: nm_req -= 1
                elif pos == 'Delantero' and f_req > 0: nf_req -= 1
                else: continue

                val, assign = solve_xi(idx + 1, np_req, nd_req, nm_req, nf_req)
                cand_val = val + BONUS_HUECO + xpts[idx] * get_pos_weight(pos)
                if cand_val > max_val:
                    max_val = cand_val
                    best_assign = {k: v[:] for k, v in assign.items()}
                    best_assign[pos].append(player)
            memo[state] = (max_val, best_assign)
            return memo[state]

        val, assign = solve_xi(0, 1, d, m, f)
        if val > best_weighted_value:
            best_weighted_value = val
            best_form = f"{d}-{m}-{f}"
            best_xi = {'POR': assign['Portero'], 'DEF': assign['Defensa'],
                       'MED': assign['Centrocampista'], 'DEL': assign['Delantero']}

    titulares = best_xi['POR'] + best_xi['DEF'] + best_xi['MED'] + best_xi['DEL']
    return best_form, best_xi, titulares


@st.cache_data(show_spinner=False)
def resumen_onces_liga(huella=None):
    """Valor y media de puntos del mejor once de CADA mánager.

    Sirve para dos cosas: que las estrellas signifiquen algo (comparando con la
    liga en vez de con umbrales fijos en euros) y para poder enfrentarte con
    cualquier rival sin saltar de pestaña."""
    plantillas = db.get('plantillas')
    if plantillas is None or plantillas.empty:
        return {}
    resumen = {}
    for persona, grupo in plantillas.dropna(subset=['Jugador', 'Participante']).groupby('Participante'):
        _, _, titulares = calcular_mejor_once(grupo.copy())
        if not titulares:
            continue
        valor = sum(_a_float(p.get('Valor Actual (€)'), 0.0) or 0.0 for p in titulares)
        medias = [_a_float(p.get('Media Puntos'), None) for p in titulares
                  if (_a_float(p.get('PJ'), 0.0) or 0.0) > 0]
        medias = [m for m in medias if m is not None]
        resumen[persona] = {
            'valor': valor,
            'media': (sum(medias) / len(medias)) if medias else None,
            'titulares': len(titulares),
            # Suma de puntos esperados del once: es lo que sostiene la valoración
            # por estrellas. calcular_mejor_once ya lo deja calculado en cada
            # jugador, así que no hay que recorrer nada dos veces.
            'xpts': sum(_a_float(p.get('_xPts'), 0.0) or 0.0 for p in titulares),
            # Valor de TODA la plantilla, no solo del once: es el músculo
            # económico real, y premia tener fondo de armario.
            'valor_plantilla': float(pd.to_numeric(grupo['Valor Actual (€)'], errors='coerce').fillna(0).sum()),
        }
    return resumen


# Reparto de la valoración por estrellas. Manda el rendimiento, pero el músculo
# económico cuenta: normalmente van de la mano, y quien tiene una plantilla cara
# aguanta mejor una lesión o una mala racha aunque hoy no lo esté demostrando.
# Revisado el 24/09/2026 reconstruyendo las plantillas de cada jornada (3 a 7,
# 49 onces): el orden por puntos esperados acierta el de los puntos reales de
# su once con +0,44; mezclado 75/25 con el valor de la plantilla, +0,42; el
# valor solo, +0,21. El dinero no añadía nada que no dijeran ya los puntos.
PESO_RENDIMIENTO_ESTRELLAS = 1.0


def indices_valoracion(resumen):
    """Índice de 0 a 1 por mánager: 75% rendimiento esperado del once y 25%
    valor de toda su plantilla.

    Se mezclan PERCENTILES, no las magnitudes: unos son puntos y otros euros, y
    sumarlos directamente dejaría que los millones aplastasen a los puntos. Así
    cada componente aporta "en qué puesto de la liga estás", que sí es
    comparable."""
    if not resumen:
        return {}

    def percentiles(clave):
        valores = sorted(float(d.get(clave) or 0) for d in resumen.values())
        if len(valores) < 2 or valores[0] == valores[-1]:
            return {persona: 0.5 for persona in resumen}
        return {
            persona: sum(1 for v in valores if v < float(d.get(clave) or 0)) / (len(valores) - 1)
            for persona, d in resumen.items()
        }

    pct_rend = percentiles('xpts')
    pct_valor = percentiles('valor_plantilla')
    return {
        persona: (PESO_RENDIMIENTO_ESTRELLAS * pct_rend[persona]
                  + (1 - PESO_RENDIMIENTO_ESTRELLAS) * pct_valor[persona])
        for persona in resumen
    }


def estrellas_relativas(valor_xi, valores_liga):
    """Estrellas por puesto en la liga, de 1 a 5 en pasos de media.

    Dos correcciones encadenadas:

     1. Antes eran umbrales fijos en euros (55 M€ = cinco estrellas) y los diez
        onces de esta liga caben entre 44 M y 64 M: nadie bajaba de cuatro
        estrellas y siete de diez tenían cuatro y media o cinco. Una escala en
        la que todos sacan sobresaliente no dice nada, así que pasó a ser
        relativa: el mejor de la liga saca cinco y el peor una.

     2. Pero seguía midiendo DINERO. Con los datos de la jornada 1 ya chirriaba:
        Ciudad Algeciras era 2º en valoración con la peor media de titulares de
        la liga (3,83), y La Caleta último con 6,00 de media. La valoración
        decía quién tiene la plantilla más cara, no quién va a puntuar.

    Ahora se ordena por PUNTOS ESPERADOS del once. Y eso arregla el problema sin
    esperar a tener muchas jornadas: los puntos esperados ya se apoyan en el
    precio mientras no hay partidos, así que hoy el orden se parece al de antes
    y se va desplazando solo hacia el rendimiento conforme llegan datos."""
    valores = sorted(v for v in valores_liga if v is not None)
    if len(valores) < 2:
        return "⭐⭐⭐", None
    puesto = sum(1 for v in valores if v < valor_xi)
    percentil = puesto / (len(valores) - 1)
    llenas = int(round(percentil * 8)) / 2 + 1          # de 1 a 5 estrellas
    enteras = int(llenas)
    media = llenas - enteras >= 0.5
    estrellas = "⭐" * enteras + ("✨" if media else "")
    # El puesto se cuenta por cuántos están POR ENCIMA, no por cuántos quedan
    # debajo: con un empate, restar los de abajo daba 5º a dos mánagers que en
    # realidad son 4º empatados (solo tres por delante).
    posicion = 1 + sum(1 for v in valores if v > valor_xi)
    return estrellas, posicion


# --- 🔝 AVISOS SOBRE LOS DATOS ---
# Antes aquí había un logo, un título de 2,1 rem y la fecha de lectura: media
# pantalla ocupada antes de enseñar un solo dato, en todas las secciones. El
# nombre y la fecha viven ahora en el menú, y la página entera es para lo que
# viniste a ver. Lo que se queda son los avisos, que piden acción.
# Se avisa en vez de arreglarlo en silencio: el duplicado está en el Excel y
# conviene que lo borre allí, o volverá a aparecer en cada lectura.
if db.get('filas_duplicadas_plantillas'):
    st.warning(f"La hoja Plantillas tiene {db['filas_duplicadas_plantillas']} fila/s "
               "repetida/s (el mismo jugador dos veces con el mismo mánager). La app las "
               "ignora para no duplicar jugadores en el once ni en los totales.")
_fechas_mal = 0
try:
    _f = pd.to_datetime(db['contabilidad'].get('Fecha Fichaje'), errors='coerce')
    _fechas_mal = int(((_f.notna()) & (_f < pd.Timestamp('2000-01-01'))).sum())
except Exception:
    pass
if _fechas_mal:
    st.warning(f"Hay {_fechas_mal} movimiento/s con una fecha imposible en Contabilidad "
               "(anteriores al año 2000). Se ignoran para "
               "los cálculos, pero conviene corregirlas.")

# 🧮 MERCADO SIN VALORES. Con el Excel pasaba cuando nadie recalculaba las
# fórmulas; con la base de datos solo puede pasar si el bot no ha traído el
# mercado (Biwenger_Export vacío). Mejor decirlo que enseñar la liga a cero.
try:
    _valores = pd.to_numeric(db['mercado'].get('Valor Actual (€)'), errors='coerce')
    _sin_calcular = bool(len(_valores)) and float(_valores.fillna(0).abs().sum()) == 0
except Exception:
    _sin_calcular = False
if _sin_calcular:
    st.error("No hay precios del mercado: la tabla Biwenger_Export está vacía o sin "
             "valores. Pulsa el botón de actualizar (las flechas en círculo) para que "
             "el bot los traiga de Biwenger.")

if db.get('filas_incompletas_contabilidad'):
    _filas = db['filas_incompletas_contabilidad']
    _donde = ", ".join(str(f) for f in _filas[:6]) + ("…" if len(_filas) > 6 else "")
    st.warning(f"Hay {len(_filas)} fila/s de Contabilidad con datos pero sin mánager o sin "
               f"tipo de operación (fila/s {_donde}). No se cuentan como "
               "movimientos: complétalas o bórralas.")

if db.get('filas_duplicadas_mercado'):
    st.warning(f"El mercado tiene {db['filas_duplicadas_mercado']} fila/s repetida/s del "
               "mismo jugador en Biwenger_Export. La app las ignora.")

# ==========================================
# 🧭 EL MENÚ
# ==========================================
# Antes eran once pestañas en una sola fila. Once nombres seguidos son un muro
# donde cuesta encontrar nada, y además Streamlit ejecuta el contenido de TODAS
# las pestañas en cada vuelta, mires la que mires: el Histórico se pintaba
# entero aunque estuvieras en el Mercado.
#
# Ahora el Resumen es la pantalla de inicio y el resto vive en el menú de la
# izquierda, que se pliega con la flecha de su esquina. Solo se dibuja la
# sección que estés viendo.
PARTIDOS_TRAMO_CLASIFICACION = 3

CSS_TITULO_SECCION = """
<style>
.ts-titulo { display:flex; align-items:center; gap:14px; margin:6px 0 14px 0; }
.ts-titulo::before { content:""; flex:1; height:1px;
                     background:linear-gradient(90deg, transparent, rgba(231,197,101,0.45)); }
.ts-titulo::after { content:""; flex:1; height:1px;
                    background:linear-gradient(90deg, rgba(231,197,101,0.45), transparent); }
.ts-titulo span { font-family:'Fraunces', Georgia, serif; font-size:1.25rem; font-weight:600;
                  letter-spacing:0.08em; text-transform:uppercase; color:#e7c565; padding:5px 18px;
                  border-radius:10px; background:rgba(231,197,101,0.08);
                  border:1px solid rgba(231,197,101,0.35); }
</style>
"""

SECCIONES = ["Resumen", "Participantes", "Movimientos", "Plantillas", "Mercado", "Scouting",
             "Rivales", "Comparar", "Calendario", "Histórico"]
# La clasificación vive ahora dentro de Calendario (24/09/2026).
SECCIONES_FUSIONADAS = {"Clasificación": "Calendario"}
# El Resumen es el inicio y tiene su propio botón (la casa), así que no repite
# sitio dentro del menú.
SECCIONES_MENU = [_s for _s in SECCIONES if _s != "Resumen"]


def _clave_menu(nombre):
    """Clave sin tildes para el botón de una sección.

    Streamlit convierte la clave del widget en una clase CSS (st-key-...), y
    las tildes no sobreviven a esa conversión: "Clasificación" e "Histórico" se
    quedaban sin la regla de estilo y salían con el marco por defecto mientras
    las otras ocho iban planas."""
    return "menu_" + re.sub(r'[^A-Za-z0-9]+', '_', _sin_tildes(nombre))


def _ir_a_seccion(nombre):
    # Solo si de verdad cambia de sección: pulsar la que ya estás viendo no
    # merece una transición.
    if st.session_state.get('seccion') != nombre:
        st.session_state['cambio_de_seccion'] = nombre
    st.session_state['seccion'] = nombre
    # Elegir una sección CIERRA el menú. Con el desplegable de Streamlit había
    # que volver a pulsar para plegarlo, y eso son dos clics para una decisión.
    st.session_state['menu_abierto'] = False


# 🔄 ACTUALIZAR AHORA
# El bot de las 8:30 deja la app al día por la mañana, pero durante el día pasan
# cosas: ventas entre mánagers, lesiones, sanciones, puntos de los partidos. El
# botón de las flechas lanza el bot en modo rápido (python bot_diario.py
# --rapido), que trae solo eso y se salta lo que no cambia hasta mañana. Al
# terminar, la app se recarga sola con el Excel nuevo.
TIEMPO_MAXIMO_ACTUALIZAR = 600      # segundos


def actualizar_ahora():
    """Lanza el bot en modo rápido y devuelve (tipo, mensaje) para enseñar."""
    import sys
    carpeta = os.path.dirname(os.path.abspath(__file__))
    ruta_bot = os.path.join(carpeta, "bot_diario.py")
    if not os.path.exists(ruta_bot):
        return 'error', "No encuentro bot_diario.py en la carpeta de la app."
    # UTF-8 a la fuerza: en Windows, con la salida capturada, Python escribe en
    # la codificación antigua y el primer nombre con emoji ("NIKE FC (MUNDIAL
    # 🏅)") tumbaría el bot a mitad.
    entorno = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    inicio = time.time()
    try:
        proceso = subprocess.run([sys.executable, ruta_bot, "--rapido"], cwd=carpeta, env=entorno,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 timeout=TIEMPO_MAXIMO_ACTUALIZAR)
    except subprocess.TimeoutExpired:
        return 'error', "La actualización tardaba demasiado y se ha cortado."
    except Exception as error:
        return 'error', f"No se ha podido lanzar la actualización ({error})."
    salida = proceso.stdout or ""
    if proceso.returncode == 2:
        return 'aviso', "No se ha podido escribir en la base de datos. Vuelve a pulsar en un momento."
    if proceso.returncode == 3:
        return 'aviso', "Ya hay una actualización en marcha. Espera un poco y vuelve a pulsar."
    if proceso.returncode != 0:
        errores = [re.sub(r"^ERROR \([^)]*\):\s*", "", linea.split("] ", 1)[-1])
                   for linea in salida.splitlines() if "ERROR" in linea]
        return 'error', "No se ha podido actualizar: " + (errores[-1] if errores
                                                          else f"el bot terminó con el código {proceso.returncode}.")
    nuevos = re.search(r"Movimientos nuevos en Contabilidad: (\d+)", salida)
    n = int(nuevos.group(1)) if nuevos else 0
    detalle = (f"{n} movimiento{'s' if n != 1 else ''} nuevo{'s' if n != 1 else ''}" if n
               else "sin movimientos nuevos")
    return 'bien', f"Actualizado a las {datetime.now():%H:%M} ({time.time() - inicio:.0f} s) · {detalle}."


def _pedir_actualizacion():
    st.session_state['actualizar_pedido'] = True
    st.session_state['menu_abierto'] = False


def _alternar_menu():
    st.session_state['menu_abierto'] = not st.session_state.get('menu_abierto', False)


if st.session_state.get('seccion') in SECCIONES_FUSIONADAS:
    st.session_state['seccion'] = SECCIONES_FUSIONADAS[st.session_state['seccion']]
if st.session_state.get('seccion') not in SECCIONES:
    st.session_state['seccion'] = SECCIONES[0]
_pagina = st.session_state['seccion']

# Streamlit pone a cada widget una clase con su clave (st-key-...), que es la
# única manera de estilar un botón concreto: un <div> suelto no envuelve nada,
# porque cada bloque va en su propio contenedor y el navegador lo cierra solo.
# Si una versión no pusiera esas clases, los botones se quedan con su aspecto
# de siempre y no se rompe nada.
_CSS_MENU = ("<style>.st-key-menu_inicio button, .st-key-menu_abrir button { "
             "border:1px solid rgba(255,255,255,0.14) !important; "
             "background:rgba(255,255,255,0.03) !important; font-weight:600 !important; }"
             + ", ".join(f".st-key-{_clave_menu(_s)} button" for _s in SECCIONES_MENU)
             + " { border:1px solid transparent !important; background:transparent !important; "
               "font-weight:500 !important; }"
             + ", ".join(f".st-key-{_clave_menu(_s)} button:hover" for _s in SECCIONES_MENU)
             + " { border-color:rgba(255,255,255,0.14) !important; "
               "background:rgba(255,255,255,0.05) !important; }"
             ".st-key-menu_actualizar button { border:1px solid rgba(96,165,250,0.35) !important; "
             "background:rgba(96,165,250,0.08) !important; color:#60a5fa !important; }"
             ".st-key-menu_actualizar button * { color:#60a5fa !important; }"
             ".st-key-menu_actualizar [data-testid='stIconMaterial'] { font-size:1.35rem !important; }"
             "</style>")
st.markdown(_CSS_MENU, unsafe_allow_html=True)

# 🧭 El menú vive EN LA PÁGINA, no en la barra lateral de Streamlit: la barra se
# pliega y hay que dar con su flecha para recuperarla, o no aparece siquiera si
# la sesión venía plegada de antes. Aquí el abierto/cerrado lo guarda la propia
# app, así que se comporta igual siempre.
# Las flechas van en su propia fila, encima de la casa. Metidas en la misma
# columna que la casa, esa columna medía dos botones de alto y el rótulo de la
# sección se quedaba descolgado, más abajo que el Menú.
with st.columns([0.4, 1.1, 6])[0]:
    try:
        st.button("", key="menu_actualizar", icon=":material/sync:", use_container_width=True,
                  help="Actualizar compras, ventas, lesiones y puntos", on_click=_pedir_actualizacion)
    except TypeError:      # Streamlit sin iconos en los botones: el emoji hace de icono
        st.button("🔄", key="menu_actualizar", use_container_width=True,
                  help="Actualizar compras, ventas, lesiones y puntos", on_click=_pedir_actualizacion)
try:
    _col_casa, _col_menu, _col_donde = st.columns([0.4, 1.1, 6], vertical_alignment="center")
except TypeError:          # Streamlit antiguo: sin alineación vertical de columnas
    _col_casa, _col_menu, _col_donde = st.columns([0.4, 1.1, 6])
with _col_casa:
    st.button("🏠", key="menu_inicio", use_container_width=True, help="Volver al inicio",
              type="primary" if _pagina == "Resumen" else "secondary",
              on_click=_ir_a_seccion, args=("Resumen",))
with _col_menu:
    st.button("☰  Menú", key="menu_abrir", use_container_width=True, on_click=_alternar_menu)
with _col_donde:
    st.markdown(f"<div style='color:#8b93a7; font-size:0.74rem; letter-spacing:0.14em; "
                f"text-transform:uppercase; display:flex; align-items:center; min-height:40px;'>"
                f"{_pagina}</div>", unsafe_allow_html=True)

if st.session_state.pop('actualizar_pedido', False):
    with st.spinner("Actualizando con Biwenger…"):
        st.session_state['actualizacion_resultado'] = actualizar_ahora()
    # Otra vuelta entera: la base de datos ha cambiado, su huella también, y la
    # app la relee sola con los datos nuevos.
    st.rerun()
_resultado_actualizacion = st.session_state.pop('actualizacion_resultado', None)
if _resultado_actualizacion:
    _tipo_act, _texto_act = _resultado_actualizacion
    {'bien': st.success, 'aviso': st.warning}.get(_tipo_act, st.error)(_texto_act)

if st.session_state.get('menu_abierto'):
    try:
        _caja_menu = st.container(border=True)
    except TypeError:          # Streamlit antiguo: contenedor sin marco
        _caja_menu = st.container()
    with _caja_menu:
        _columnas = st.columns(4)
        for _i, _opcion in enumerate(SECCIONES_MENU):
            _columnas[_i % 4].button(_opcion,
                                     key=_clave_menu(_opcion), use_container_width=True,
                                     type="primary" if _pagina == _opcion else "secondary",
                                     on_click=_ir_a_seccion, args=(_opcion,))
        st.markdown(f"<div style='color:#6f7789; font-size:0.7rem; margin-top:8px;'>"
                    f"Última lectura: {db['timestamp']}</div>", unsafe_allow_html=True)
        # 👤 Cambiar el equipo desde el que se ve la app
        _nombres = sorted(_participantes_de_la_liga(), key=str.casefold)
        if MI_EQUIPO in _nombres:
            _otro = st.selectbox("Ves la app como", _nombres, index=_nombres.index(MI_EQUIPO),
                                 key="menu_mi_equipo")
            if _otro != MI_EQUIPO:
                _elegir_equipo(_otro)
                st.rerun()
        # 📤 Los datos en un Excel, para consultarlos o guardarlos aparte. Es una
        # foto: la app no lee de él. Se genera solo al pedirlo (tarda unos
        # segundos con todo el histórico) y se guarda en caché hasta que cambien
        # los datos.
        if st.button("📤 Preparar una copia en Excel", key="menu_exportar"):
            st.session_state['exportar_pedido'] = True
        if st.session_state.get('exportar_pedido'):
            with st.spinner("Preparando el Excel…"):
                _excel = excel_exportado(_huella_excel(resolver_excel_path()))
            st.download_button("Descargar biwenger.xlsx", data=_excel,
                               file_name=f"biwenger_{datetime.now():%Y%m%d}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument."
                                    "spreadsheetml.sheet", key="menu_descargar")

# La pestaña Resumen se pinta con ui_resumen(), más abajo: usa funciones que
# se definen después de este punto.


# ==========================================
# 👥 PESTAÑA: PARTICIPANTES
# ==========================================


# ==========================================
# 📅 PESTAÑA: CALENDARIO (OPTIMIZADA)
# ==========================================
DIAS_SEMANA_CAL = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
ANCHO_FECHA_CAL = 250      # px; el mismo hueco a la derecha para que el partido quede centrado


def color_dificultad(valor):
    """Verde para un partido fácil, rojo para uno duro."""
    if valor is None or pd.isna(valor):
        return '#6b7280'
    c1, c2, c3, c4 = cortes_color_dificultad()
    if valor < c1: return '#22c55e'
    if valor < c2: return '#84cc16'
    if valor < c3: return '#eab308'
    if valor < c4: return '#f97316'
    return '#ef4444'


@st.fragment
def ui_calendario():
    # Se reutiliza el calendario ya preparado al arrancar en vez de volver a
    # construirlo aquí: era el mismo cálculo por tercera vez en cada recarga.
    df_cal = df_cal_global
    if df_cal is None or df_cal.empty:
        st.warning("No hay calendario en la base de datos (tabla ClasificacionCalendario).")
        return

    j_actual = jornada_actual(df_cal)
    max_jornada = int(df_cal['Jornada'].max())
    jornadas = list(range(1, max_jornada + 1))
    equipos_cal = sorted(set(df_cal['Local'].dropna()) | set(df_cal['Visitante'].dropna()))

    # 📆 Jornada que sale por defecto: la del PRÓXIMO PARTIDO POR JUGAR, no la
    # siguiente a la última con resultados. No son lo mismo: si la jornada 1 se
    # reparte entre el sábado y el miércoles, en cuanto metes los resultados del
    # sábado la app saltaba a la jornada 2 y dejaba de enseñarte los partidos de
    # la 1 que todavía estaban por jugarse, que son los más cercanos.
    pendientes_con_fecha = df_cal[(df_cal['Estado'] == 'Pendiente') & df_cal['Fecha'].notna()]
    if not pendientes_con_fecha.empty:
        jornada_defecto = int(pendientes_con_fecha.sort_values('Fecha').iloc[0]['Jornada'])
    elif j_actual:
        jornada_defecto = min(j_actual + 1, max_jornada)
    else:
        jornada_defecto = 1
    indice_jornada = jornadas.index(jornada_defecto) if jornada_defecto in jornadas else 0

    with st.container(border=True):
        c_izq, c_mid, c_der = st.columns([1, 1, 1])
        # 🛡️ Filtro por equipo: era la consulta más natural de un calendario
        # ("¿cuándo juega el Betis?", "¿qué tramo le viene?") y había que ir
        # jornada por jornada entre 38 jornadas y 380 partidos.
        equipo_cal = c_izq.selectbox("Equipo", ["Todos"] + equipos_cal, key="cal_equipo")
        jornada_sel = c_mid.selectbox(
            "Jornada", jornadas,
            index=indice_jornada,
            format_func=lambda x: f"Jornada {x}",
            disabled=(equipo_cal != "Todos"),
            help="Al elegir un equipo se muestran todos sus partidos, así que este selector se desactiva.",
            key="cal_jornada",
        )
        managers_cal = sorted(db['plantillas']['Participante'].dropna().unique().tolist())
        indice_mio = managers_cal.index(MI_EQUIPO) if MI_EQUIPO in managers_cal else 0
        # 👕 Marcar en qué partidos te juegas algo: es un calendario de fantasy y
        # no señalaba dónde tienes jugadores.
        manager_cal = c_der.selectbox("Marcar jugadores de", managers_cal,
                                      index=indice_mio, key="cal_manager")

    plantilla_cal = db['plantillas'][db['plantillas']['Participante'] == manager_cal]
    jugadores_por_equipo = {}
    for _, jugador in plantilla_cal.dropna(subset=['Jugador', 'Equipo']).iterrows():
        jugadores_por_equipo.setdefault(jugador['Equipo'], []).append(
            (str(jugador['Jugador']), str(jugador.get('Lesion', 'no')).strip().lower() == 'si')
        )

    if equipo_cal != "Todos":
        df_j = df_cal[(df_cal['Local'] == equipo_cal) | (df_cal['Visitante'] == equipo_cal)].copy()
    else:
        df_j = df_cal[df_cal['Jornada'] == jornada_sel].copy()

    # Una jornada puede repartirse en dos semanas, así que se ordena por
    # fecha real y no por el orden en que estén las filas en el Excel.
    # Por día y, dentro del día, por hora; los que aún no tienen hora van al
    # final de su día y los que no tienen ni fecha, al final de todo.
    df_j['_orden_hora'] = df_j['Hora'].where(df_j['Hora'].map(lambda h: isinstance(h, str)), '99:99')
    df_j['_orden_hora'] = df_j['_orden_hora'].map(lambda h: h.zfill(5))
    df_j = df_j.sort_values(['Fecha', '_orden_hora', 'Jornada', 'Local'], na_position='last')

    # 🔜 El siguiente partido que se juega en TODA la liga (no solo en esta
    # jornada): si hay aplazados, puede que no sea de la jornada más baja.
    hoy = pd.Timestamp(datetime.now().date())
    pendientes_cal = df_cal[(df_cal['Estado'] == 'Pendiente') & df_cal['Fecha'].notna()]
    pendientes_cal = pendientes_cal[pendientes_cal['Fecha'] >= hoy]
    fecha_proxima = pendientes_cal['Fecha'].min() if not pendientes_cal.empty else pd.NaT

    # ⚡ Escudos como clases CSS, una vez cada uno: al filtrar por un equipo
    # salían 38 partidos con su escudo repetido 38 veces dentro del HTML.
    css_escudos_cal, con_imagen_cal = _css_escudos_tramo(set(df_j['Local']) | set(df_j['Visitante']))

    def bloque_equipo(nombre, rival, es_casa, alinear_derecha):
        """Nombre + escudo + chip de dificultad y de jugadores propios."""
        dif = dificultad_enfrentamiento(rival, es_casa, tabla_clasif_global,
                                        valores_equipos_global, puntos_equipos_global)
        valor_dif = dif['dificultad'] if dif else None
        color_dif = color_dificultad(valor_dif)
        chip_dif = (
            f'<span title="Dificultad de este partido para el {nombre}: {valor_dif:.0f} de 100" '
            f'style="background:{color_dif}22; border:1px solid {color_dif}; color:{color_dif}; '
            f'border-radius:6px; padding:1px 6px; font-size:0.68rem; font-weight:800;">'
            f'{valor_dif:.0f}</span>' if valor_dif is not None else ''
        )

        # Los jugadores propios ya no van en un chip 👕 con el nombre escondido
        # en el ratón: se escriben a la derecha de la fila (jugadores_del_partido).
        chips = f'<div style="display:flex; gap:4px; align-items:center;">{chip_dif}</div>'
        nombre_html = f'<span style="font-weight:700; color:#eee;">{nombre}</span>'
        escudo = _escudo_tramo(nombre, con_imagen_cal, 34)
        if alinear_derecha:
            return (f'<div style="display:flex; align-items:center; gap:10px; flex:1; justify-content:flex-end;">'
                    f'{chips}{nombre_html}{escudo}</div>')
        return (f'<div style="display:flex; align-items:center; gap:10px; flex:1;">'
                f'{escudo}{nombre_html}{chips}</div>')

    def jugadores_del_partido(local, visitante):
        """Los jugadores del mánager elegido en este partido, escritos, a la
        derecha de la fila: una línea por equipo con su escudo pequeño delante.
        Los lesionados, tachados en rojo."""
        lineas = []
        for equipo in (local, visitante):
            mios = jugadores_por_equipo.get(equipo, [])
            if not mios:
                continue
            nombres = " · ".join(
                f"<span class='cal-mio-les' title='Lesionado'>{n}</span>" if les else n
                for n, les in mios)
            lineas.append(f"<div class='cal-mios-linea'>{_escudo_tramo(equipo, con_imagen_cal, 16)}"
                          f"<span>{nombres}</span></div>")
        return "".join(lineas)

    filas_html = ""
    for _, p in df_j.iterrows():
        finalizado = p['Estado'] == 'Finalizado'

        fecha = p['Fecha']
        hora = p.get('Hora')
        if not isinstance(hora, str) or not hora:
            hora = None      # pandas guarda el hueco como NaN, que se pintaba «nan»
        if pd.notna(fecha):
            fecha_txt = f"{DIAS_SEMANA_CAL[fecha.weekday()]} {fecha.strftime('%d/%m')}"
            hora_txt = hora if hora else "Hora sin determinar"
        else:
            fecha_txt, hora_txt = "Sin determinar", None
        es_proximo = (not finalizado) and pd.notna(fecha) and pd.notna(fecha_proxima) and fecha == fecha_proxima
        if es_proximo:
            col_fecha, peso_fecha, etiqueta_fecha = '#ffd966', '900', f"🔜 {fecha_txt}"
        elif finalizado:
            col_fecha, peso_fecha, etiqueta_fecha = '#6b7280', '600', fecha_txt
        else:
            col_fecha, peso_fecha, etiqueta_fecha = '#9aa3b2', '700', fecha_txt
        # Con un equipo elegido se ven todas sus jornadas, así que hace falta
        # saber de cuál es cada partido.
        if equipo_cal != "Todos":
            etiqueta_fecha = f"J{int(p['Jornada'])} · {etiqueta_fecha}"
        if hora_txt:
            estilo_hora = ('color:#e5e7eb; font-weight:700;' if hora else
                           'color:#6b7280; font-weight:500; font-style:italic;')
            etiqueta_fecha += (f' <span style="color:#4b5563; margin:0 4px;">·</span>'
                               f'<span style="{estilo_hora}">{hora_txt}</span>')
        fecha_html = (
            f'<div style="width:{ANCHO_FECHA_CAL}px; flex:none; color:{col_fecha}; font-weight:{peso_fecha}; '
            f'font-size:0.82rem; white-space:nowrap;">{etiqueta_fecha}</div>'
        )
        if finalizado:
            badge = (f'<div style="background: rgba(74,222,128,0.15); border: 1px solid #4ade80; '
                     f'color: #4ade80; font-weight: 900; font-size: 1.1rem; padding: 6px 18px; '
                     f'border-radius: 8px; min-width: 70px; text-align:center;">{p["Resultado"]}</div>')
        else:
            badge = ('<div style="background: rgba(255,217,102,0.12); border: 1px solid #ffd966; '
                     'color: #ffd966; font-weight: 700; font-size: 0.85rem; padding: 6px 14px; '
                     'border-radius: 8px; min-width: 70px; text-align:center;">Pendiente</div>')

        borde = 'rgba(255,217,102,0.55)' if es_proximo else 'rgba(255,255,255,0.06)'
        fondo = 'rgba(46,42,30,0.8)' if es_proximo else 'rgba(30,30,46,0.75)'
        fila = (
            f'<div style="display:flex; align-items:center; justify-content:space-between; background: {fondo}; '
            f'backdrop-filter: blur(4px); border: 1px solid {borde}; border-radius: 10px; '
            'padding: 10px 18px; margin-bottom: 10px; box-shadow: 0 3px 8px rgba(0,0,0,0.35);">'
            f'{fecha_html}'
            f'{bloque_equipo(p["Local"], p["Visitante"], True, alinear_derecha=True)}'
            f'<div style="width:120px; display:flex; justify-content:center;">{badge}</div>'
            f'{bloque_equipo(p["Visitante"], p["Local"], False, alinear_derecha=False)}'
            f'<div class="cal-mios">{jugadores_del_partido(p["Local"], p["Visitante"])}</div>'
            '</div>'
        )
        filas_html += fila

    css_mios = (f"<style>.cal-mios {{ width:{ANCHO_FECHA_CAL}px; flex:none; display:flex; flex-direction:column; "
                "align-items:flex-end; gap:4px; }"
                ".cal-mios-linea { display:flex; align-items:center; justify-content:flex-end; gap:6px; "
                "color:#93c5fd; font-size:0.78rem; font-weight:600; line-height:1.25; text-align:right; }"
                ".cal-mios-linea > span { white-space:normal; }"
                ".cal-mio-les { color:#f87171; text-decoration:line-through; }</style>")
    st.markdown(CSS_TRAMO + css_escudos_cal + css_mios + f'<div>{filas_html}</div>', unsafe_allow_html=True)


CSS_TRAMO = """
<style>
.tramo-lista { display:flex; flex-direction:column; gap:8px; margin:10px 0 6px 0; overflow-x:auto; }
.tramo-fila { display:grid; grid-template-columns:240px 150px auto minmax(0, 1fr);
              align-items:center; gap:22px; min-width:820px; padding:10px 18px;
              background:rgba(255,255,255,0.025); border:1px solid rgba(255,255,255,0.06);
              border-left:3px solid transparent; border-radius:10px; }
.tramo-fila.tramo-mia { border-left-color:#e7c565; }
.tramo-equipo { display:flex; align-items:center; gap:12px; }
.tramo-nombre { font-weight:600; color:#f2f4f8; font-size:0.98rem; }
.tramo-etiqueta { font-size:0.76rem; font-weight:600; margin-top:2px; }
.tramo-dif { display:flex; align-items:center; gap:12px; }
.tramo-num { font-family:'Fraunces', Georgia, serif; font-size:1.55rem; font-weight:600; min-width:34px;
             text-align:right; font-variant-numeric:tabular-nums; }
.tramo-barra { flex:1; height:6px; border-radius:4px; background:rgba(255,255,255,0.07); }
.tramo-barra span { display:block; height:100%; border-radius:4px; }
.tramo-partidos { display:flex; gap:8px; flex-wrap:wrap; }
.tramo-ficha { width:58px; padding:6px 0 5px 0; border:1px solid; border-radius:8px; display:flex;
               flex-direction:column; align-items:center; gap:2px; }
.tramo-lugar { font-size:0.66rem; color:#c3cbd9; font-weight:600; }
.tramo-nivel { font-size:0.62rem; font-weight:600; }
.tramo-gente { display:flex; flex-direction:column; gap:7px; padding-left:8px;
               border-left:1px solid rgba(255,255,255,0.06); min-height:44px; justify-content:center; }
.tramo-linea { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.tramo-rot { color:#6f7789; font-size:0.66rem; letter-spacing:0.1em; text-transform:uppercase;
             width:46px; flex:none; }
.tramo-libre { display:inline-flex; align-items:center; gap:6px; background:rgba(255,255,255,0.05);
               border:1px solid rgba(255,255,255,0.10); border-radius:999px; padding:2px 10px 2px 10px;
               font-size:0.76rem; color:#dfe5ee; white-space:nowrap; }
.tramo-libre-pos { color:#8b93a7; font-size:0.66rem; font-weight:700; }
.tramo-libre-precio { color:#93c5fd; font-weight:600; }
.tramo-chip { background:rgba(231,197,101,0.10); color:#e7c565; border:1px solid rgba(231,197,101,0.35);
              border-radius:999px; padding:2px 10px; font-size:0.74rem; font-weight:600; white-space:nowrap; }
.esc-tramo { display:inline-block; background-size:contain; background-repeat:no-repeat;
             background-position:center; vertical-align:middle; flex:none; }
.esc-tramo-letra { display:inline-flex; align-items:center; justify-content:center; border-radius:50%;
                   background:rgba(255,255,255,0.08); color:#c3cbd9; font-weight:700; flex:none; }
</style>
"""


def _slug_tramo(equipo):
    return re.sub(r'[^a-z0-9]+', '-', _sin_tildes(str(equipo))).strip('-')


def _css_escudos_tramo(equipos):
    """Cada escudo una sola vez, como clase CSS. Con veinte equipos y hasta seis
    rivales por fila, meter la imagen en cada ficha multiplicaba por siete el
    peso de la página."""
    reglas, con_imagen = [], set()
    for equipo in sorted(e for e in equipos if e):
        url = url_imagen(f"equipo/{equipo}.png", f"equipo/{equipo}.jpg")
        if url:
            reglas.append(f".esc-tramo-{_slug_tramo(equipo)} {{ background-image:url('{url}'); }}")
            con_imagen.add(equipo)
    return ("<style>" + "\n".join(reglas) + "</style>") if reglas else "", con_imagen


def _escudo_tramo(equipo, con_imagen, tamano):
    if equipo in con_imagen:
        return (f"<span class='esc-tramo esc-tramo-{_slug_tramo(equipo)}' "
                f"style='width:{tamano}px; height:{tamano}px;'></span>")
    return (f"<span class='esc-tramo-letra' style='width:{tamano}px; height:{tamano}px; "
            f"font-size:{int(tamano * 0.45)}px;'>{(str(equipo) or '?')[:1].upper()}</span>")


@st.cache_data(show_spinner=False)
def _tramos_de_todos(huella=None, cuantos=3):
    """⚡ El tramo de los veinte equipos para `cuantos` partidos, una vez por
    versión de los datos y no en cada clic."""
    if df_cal_global is None or df_cal_global.empty:
        return {}
    equipos = set(df_cal_global['Local'].dropna()) | set(df_cal_global['Visitante'].dropna())
    return {e: t for e in equipos if (t := tramo_de_calendario(e, cuantos, df_cal_global))}








def _ficha_partido_tramo(partido, con_imagen):
    """Un partido del tramo: escudo del rival, casa o fuera y lo difícil que es,
    del color de la dificultad. Es la misma ficha que la de los próximos
    partidos del comparador, para que se lea igual en toda la app."""
    dificultad = partido['dificultad']
    color = color_dificultad(dificultad)
    c1, c2, c3, c4 = cortes_color_dificultad()
    nivel = "fácil" if dificultad < c2 else "igualado" if dificultad < c3 else "difícil"
    lugar = "en casa" if partido['es_casa'] else "fuera"
    cuando = (f" · {pd.Timestamp(partido['fecha']):%d/%m}" if partido.get('fecha') is not None
              else " · aún sin fecha")
    ayuda = (f"J{partido['jornada']} · {partido['rival']} ({lugar}) · {nivel}{cuando}").replace("'", "&#39;")
    estilo_borde = "dashed" if partido.get('fecha') is None else "solid"
    return (f"<div class='tramo-ficha' title='{ayuda}' style='border-color:{color}; "
            f"border-style:{estilo_borde}; background:{color}1a;'>"
            f"{_escudo_tramo(partido['rival'], con_imagen, 24)}"
            f"<div class='tramo-lugar'>{'Casa' if partido['es_casa'] else 'Fuera'}</div>"
            f"<div class='tramo-nivel' style='color:{color};'>{nivel}</div></div>")




CSS_CLASIFICACION = """
<style>
.cl-marco { border:1px solid rgba(255,255,255,0.08); border-radius:14px; overflow-x:auto;
            background:linear-gradient(180deg, rgba(255,255,255,0.025), rgba(255,255,255,0.01)); }
.cl-tabla { width:100%; min-width:1000px; border-collapse:collapse; table-layout:fixed;
            font-variant-numeric:tabular-nums; }
.cl-tabla th { color:#8b93a7; font-size:0.68rem; font-weight:600; letter-spacing:0.12em;
               text-transform:uppercase; text-align:center; padding:12px 8px;
               border-bottom:1px solid rgba(255,255,255,0.08); white-space:nowrap; }
.cl-tabla td { text-align:center; padding:0 8px; height:44px; color:#d6dbe4; font-size:0.9rem;
               border-bottom:1px solid rgba(255,255,255,0.045); white-space:nowrap; }
.cl-tabla tr:last-child td { border-bottom:none; }
.cl-tabla tbody tr:hover td { background:rgba(255,255,255,0.035); }
.cl-tabla th.cl-izq, .cl-tabla td.cl-izq { text-align:left; }
.cl-pos { display:inline-flex; align-items:center; justify-content:center; width:28px; height:28px;
          border-radius:8px; font-weight:700; font-size:0.85rem; color:#c3cbd9;
          background:rgba(255,255,255,0.05); }
.cl-equipo { display:flex; align-items:center; gap:10px; font-weight:600; color:#f2f4f8; }
.cl-pts { font-family:'Fraunces', Georgia, serif; font-size:1.1rem; font-weight:600; color:#f2f4f8; }
.cl-sec { color:#9aa3b2; }
.cl-prox { display:inline-flex; align-items:center; gap:6px; font-size:0.84rem; }
.cl-prox img { width:18px !important; height:18px !important; }
.cl-tramo { display:inline-flex; align-items:center; gap:12px; }
.cl-rivales { display:inline-flex; align-items:center; gap:11px; padding-left:12px;
              border-left:1px solid rgba(255,255,255,0.10); }
.cl-rival { display:inline-flex; align-items:center; gap:3px; height:20px; }
.cl-rival-lugar { font-size:0.72rem; line-height:1; }
.cl-lugar { font-size:0.95rem; line-height:1; }
.cl-pill { display:inline-block; min-width:62px; padding:3px 10px; border-radius:999px; font-size:0.8rem;
           font-weight:700; border:1px solid; }
.cl-leyenda { display:flex; justify-content:center; flex-wrap:wrap; gap:8px 22px; margin-top:12px;
              font-size:0.8rem; color:#9aa3b2; }
.cl-leyenda span { display:inline-flex; align-items:center; gap:7px; }
.cl-punto { width:10px; height:10px; border-radius:3px; display:inline-block; }
</style>
"""

ZONAS_CLASIFICACION = [   # (color, nombre, cómo se reconoce)
    ('#e7c565', 'Campeón'),
    ('#60a5fa', 'Champions League'),
    ('#fb923c', 'Europa League'),
    ('#4ade80', 'Conference League'),
    ('#f87171', 'Descenso'),
]


def _zona_clasificacion(pos, total):
    if pos == 1:
        return ZONAS_CLASIFICACION[0][0]
    if pos in (2, 3, 4):
        return ZONAS_CLASIFICACION[1][0]
    if pos == 5:
        return ZONAS_CLASIFICACION[2][0]
    if pos == 6:
        return ZONAS_CLASIFICACION[3][0]
    if pos > total - 3:
        return ZONAS_CLASIFICACION[4][0]
    return None


def _pill_color(texto, valor):
    if valor is None or pd.isna(valor):
        return "<span class='cl-sec'>—</span>"
    c = color_dificultad(valor)
    return f"<span class='cl-pill' style='color:{c}; border-color:{c}66; background:{c}1a;'>{texto}</span>"


COLOR_TRAMO = {'Cómodo': '#22c55e', 'Normal': '#eab308', 'Duro': '#ef4444'}


def _pill_tramo(texto):
    c = COLOR_TRAMO.get(texto)
    if not c:
        return "<span class='cl-sec'>—</span>"
    return f"<span class='cl-pill' style='color:{c}; border-color:{c}66; background:{c}1a;'>{texto}</span>"


def html_clasificacion(base, con_zonas, medias_tramo, tramos=None):
    """La clasificación como tabla propia: números centrados, escudos, la zona
    europea o de descenso como una raya de color a la izquierda (no la fila
    entera pintada) y la dificultad en pastillas del color de siempre."""
    total = len(base)
    fixtures = {e: get_fixture_equipo(e) for e in base['Equipo']}
    # ⚡ Cada escudo UNA vez, como clase CSS, aunque salga en tres columnas: con
    # la imagen metida en cada celda eran ~100 copias y 2 MB por clic cuando
    # las imágenes no se sirven como archivos.
    css_escudos, con_imagen = _css_escudos_tramo(set(base['Equipo']) | {
        q['rival'] for t in (tramos or {}).values() if t for q in t.get('partidos', [])} | {
        f['rival'] for f in fixtures.values() if f})

    tramos = tramos or {}
    # Anchos fijos: "Próximo" ya no se come media tabla y "Próx. tramo" gana
    # sitio para los escudos de los tres rivales que vienen.
    anchos = (4, 17, 5, 4, 4, 4, 4, 4, 4, 5, 16, 9, 20)
    columnas = "<colgroup>" + "".join(f"<col style='width:{a}%'>" for a in anchos) + "</colgroup>"
    cabecera = ("<tr><th>#</th><th class='cl-izq'>Equipo</th><th>Pts</th><th>PJ</th><th>PG</th>"
                "<th>PE</th><th>PP</th><th>GF</th><th>GC</th><th>DG</th><th>Próximo</th>"
                "<th>Dif.</th><th>Próx. tramo</th></tr>")
    filas = []
    for i, (_, f) in enumerate(base.iterrows()):
        pos = int(f['Pos'])
        zona = _zona_clasificacion(pos, total) if con_zonas else None
        estilo_fila = (f" style='box-shadow:inset 3px 0 0 {zona}; background:{zona}0d;'" if zona else "")
        estilo_pos = (f" style='color:{zona}; background:{zona}22;'" if zona else "")
        dg = int(f['DG'])
        color_dg = '#4ade80' if dg > 0 else ('#f87171' if dg < 0 else '#9aa3b2')
        fix = fixtures.get(f['Equipo'])
        if fix:
            lugar = ("<span class='cl-lugar' title='En casa'>🏠</span>" if fix['es_casa']
                     else "<span class='cl-lugar' title='Fuera'>✈️</span>")
            proximo = (f"<span class='cl-prox'>{lugar}"
                       f"{_escudo_tramo(fix['rival'], con_imagen, 18)}{fix['rival']}</span>")
            dif = _pill_color(f"{fix['dificultad']:.0f}/100", fix['dificultad'])
        else:
            proximo, dif = "<span class='cl-sec'>—</span>", "<span class='cl-sec'>—</span>"
        tramo = _pill_tramo(f['Próx. tramo'])
        rivales = (tramos.get(f['Equipo']) or {}).get('partidos', [])
        if rivales:
            escudos = "".join(
                f"<span class='cl-rival' title=\"{p['rival']} ({'casa' if p.get('es_casa') else 'fuera'})\">"
                f"<span class='cl-rival-lugar'>{'🏠' if p.get('es_casa') else '✈️'}</span>"
                f"{_escudo_tramo(p['rival'], con_imagen, 20)}</span>" for p in rivales)
            tramo = f"<span class='cl-tramo'>{tramo}<span class='cl-rivales'>{escudos}</span></span>"
        filas.append(
            f"<tr{estilo_fila}><td><span class='cl-pos'{estilo_pos}>{pos}</span></td>"
            f"<td class='cl-izq'><span class='cl-equipo'>{_escudo_tramo(f['Equipo'], con_imagen, 24)}"
            f"{f['Equipo']}</span></td>"
            f"<td><span class='cl-pts'>{int(f['Pts'])}</span></td>"
            + "".join(f"<td class='cl-sec'>{int(f[c])}</td>" for c in ('PJ', 'PG', 'PE', 'PP', 'GF', 'GC'))
            + f"<td style='color:{color_dg}; font-weight:600;'>{dg:+d}</td>".replace('+0', '0')
            + f"<td>{proximo}</td><td>{dif}</td><td>{tramo}</td></tr>")
    leyenda = ""
    if con_zonas:
        leyenda = ("<div class='cl-leyenda'>" + "".join(
            f"<span><i class='cl-punto' style='background:{c};'></i>{n}</span>"
            for c, n in ZONAS_CLASIFICACION) + "</div>")
    return (CSS_CLASIFICACION + CSS_TRAMO + css_escudos + "<div class='cl-marco'><table class='cl-tabla'>" + columnas +
            f"<thead>{cabecera}</thead><tbody>{''.join(filas)}</tbody></table></div>{leyenda}")


# ==========================================
# 🏆 PESTAÑA: CALENDARIO (jornadas + clasificación)
# ==========================================
if _pagina == "Calendario":
    st.markdown("<div class='animate-fade-in'>", unsafe_allow_html=True)
    st.markdown(CSS_TITULO_SECCION + "<div class='ts-titulo'><span>Jornadas</span></div>",
                unsafe_allow_html=True)
    ui_calendario()
    st.markdown("<div class='ts-titulo' style='margin-top:26px;'><span>Clasificación</span></div>",
                unsafe_allow_html=True)

    # Calendario y clasificación ya calculados al arrancar: aquí se rehacían
    # enteros en cada recarga, y eran el mismo dato por tercera vez.
    df_cal = df_cal_global
    if df_cal is None or df_cal.empty:
        st.warning("No hay calendario en la base de datos (tabla ClasificacionCalendario).")
    else:
        tabla_clas = tabla_clasif_global
        j_actual = jornada_actual(df_cal)

        # ⚠️ Sin resultados, calcular_clasificacion NO devuelve un DataFrame vacío:
        # devuelve los 20 equipos a cero. Con el `if tabla_clas.empty` de antes, el
        # aviso de "todavía no hay resultados" no salía nunca y lo que se veía era
        # una tabla entera de ceros.
        hay_resultados = (not tabla_clas.empty) and int(tabla_clas['PJ'].sum()) > 0

        # Barra fina y centrada: solo el selector de tabla, sin recuadro ni rótulo.
        if hay_resultados:
            st.markdown("<style>.st-key-clas_vista [role='radiogroup'] { justify-content:center; }"
                        "</style>", unsafe_allow_html=True)
            vista_clas = st.radio("Tabla", ["General", "En casa", "Fuera"], horizontal=True,
                                  key="clas_vista", label_visibility="collapsed")
        else:
            vista_clas = "General"
            st.caption("La liga no ha empezado: los equipos van ordenados por el valor de su plantilla.")

        # 🗓️ Próximo tramo (3 partidos): sustituye al bloque "El tramo que viene"
        # que había debajo de las jornadas.
        tramos_clas = _tramos_de_todos(_huella_excel(resolver_excel_path()), PARTIDOS_TRAMO_CLASIFICACION)

        def texto_tramo(equipo):
            tramo = tramos_clas.get(equipo)
            if not tramo:
                return "—", None
            return tramo['etiqueta'].replace('Tramo ', '').capitalize(), tramo['media']

        def texto_proximo(equipo):
            fix = get_fixture_equipo(equipo)
            if not fix:
                return "—", None
            return f"{'🏠' if fix['es_casa'] else '✈️'} {fix['rival']}", fix['dificultad']

        if not hay_resultados:
            # 📋 Vista útil mientras no ruede el balón: hasta ahora la pestaña se
            # quedaba en un aviso y nada más.
            filas_previa = []
            for equipo in sorted(set(df_cal['Local'].dropna()) | set(df_cal['Visitante'].dropna())):
                proximo, dif = texto_proximo(equipo)
                filas_previa.append({
                    'Equipo': equipo,
                    'Valor plantilla': valores_equipos_global.get(equipo, 0),
                    'Puntos fantasy': puntos_equipos_global.get(equipo, 0),
                    'Próximo': proximo,
                    'Dificultad': dif,
                    'Próx. tramo': texto_tramo(equipo)[0],
                })
            previa = pd.DataFrame(filas_previa).sort_values('Valor plantilla', ascending=False)
            previa.insert(0, 'Pos', range(1, len(previa) + 1))
            estilo_previa = (previa.style
                             .format({'Valor plantilla': formato_euro,
                                      'Puntos fantasy': lambda v: f"{int(v)}",
                                      'Dificultad': lambda v: '—' if pd.isna(v) else f"{v:.0f}"})
                             .set_table_styles(ESTILO_CABECERA))
            st.dataframe(estilo_previa, use_container_width=True, hide_index=True,
                         height=38 * (len(previa) + 1) + 8)
            st.caption("En cuanto el bot traiga los primeros resultados, esta pestaña pasa a ser "
                       "la clasificación de verdad, con sus tablas de casa y fuera.")
        else:
            # 🏠✈️ Las tablas de casa y fuera ya estaban calculadas (14 columnas de
            # desglose) y no se veían en ninguna parte, siendo justo la tabla que
            # se arregló en el Excel el primer día. Cada vista se reordena con sus
            # propios puntos: no es la general filtrada, es la clasificación que
            # habría si solo contaran los partidos de esa condición.
            sufijo = {'General': '', 'En casa': '_Casa', 'Fuera': '_Fuera'}[vista_clas]
            base = tabla_clas.copy()
            if sufijo:
                for col in ('Pts', 'PJ', 'PG', 'PE', 'PP', 'GF', 'GC'):
                    base[col] = base[f'{col}{sufijo}']
                base['DG'] = base['GF'] - base['GC']
                base = base.sort_values(['Pts', 'DG', 'GF', 'Equipo'],
                                        ascending=[False, False, False, True]).reset_index(drop=True)
                base['Pos'] = range(1, len(base) + 1)

            proximos = [texto_proximo(e) for e in base['Equipo']]
            base['Próximo'] = [p for p, _ in proximos]
            base['Dif.'] = [d for _, d in proximos]
            tramos_fila = [texto_tramo(e) for e in base['Equipo']]
            base['Próx. tramo'] = [t for t, _ in tramos_fila]
            medias_tramo = [m for _, m in tramos_fila]

            st.markdown(html_clasificacion(base, vista_clas == "General", medias_tramo, tramos_clas),
                        unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)
# ==========================================
# 👥 PESTAÑA: PARTICIPANTES
# ==========================================
def resumen_participantes():
    """Une lo que sabe la hoja de Participantes (dinero) con lo que sabe la de
    Plantillas (jugadores, lesionados, posiciones, puntos).

    Antes esta pestaña era solo dinero: nueve columnas de euros y ni una palabra
    de cuántas fichas tiene cada uno. Y ahí está lo interesante — un rival con
    once sanos y un solo portero no puede pelear una puja igual que uno con
    veintiuno."""
    part = db['participantes'].dropna(subset=['Persona']).copy()
    if part.empty:
        return part

    plantillas = db['plantillas'].dropna(subset=['Jugador'])
    filas = []
    for persona in part['Persona']:
        equipo = plantillas[plantillas['Participante'] == persona]
        sanos = equipo[equipo['Lesion'] != 'si']
        pos = sanos['Posición'].astype(str)
        por = int(pos.str.contains('Portero').sum())
        defe = int(pos.str.contains('Defensa').sum())
        med = int(pos.str.contains('Centrocampista').sum())
        dele = int(pos.str.contains('Delantero').sum())

        # ⚠️ ¿Puede alinear un once legal con los que tiene sanos? Las formaciones
        # de Biwenger siempre piden 1 portero, 3 defensas, 3 medios y 1 delantero
        # como mínimo.
        pegas = []
        if por == 0: pegas.append('sin portero')
        if defe < 3: pegas.append('faltan defensas')
        if med < 3: pegas.append('faltan medios')
        if dele < 1: pegas.append('sin delantero')
        if len(sanos) < 11: pegas.append(f'solo {len(sanos)} sanos')

        filas.append({
            'Persona': persona,
            'Jugadores': len(equipo),
            'Lesionados': int((equipo['Lesion'] == 'si').sum()),
            'Plantilla': f"{por}-{defe}-{med}-{dele}",
            'Puntos Plantilla': float(pd.to_numeric(equipo['Puntos'], errors='coerce').fillna(0).sum()),
            '_pegas': pegas,
        })

    resumen = part.merge(pd.DataFrame(filas), on='Persona', how='left')

    # 🚩 Situación de cada mánager: quién está obligado a vender (saldo en rojo)
    # y quién no puede hacerlo sin quedarse sin equipo.
    situaciones = []
    for _, fila in resumen.iterrows():
        persona = str(fila['Persona']).strip()
        saldo = _a_float(fila.get('Balance Total (€)'), 0.0) or 0.0
        vendibles = jugadores_vendibles(persona)
        puede_vender = (not vendibles.empty) and float(pd.to_numeric(
            vendibles.get('Valor Actual (€)'), errors='coerce').fillna(0).sum()) > 0
        if saldo < 0:
            situaciones.append('Obligado a vender')
        elif not puede_vender:
            situaciones.append('Sin margen')
        else:
            situaciones.append('')
    resumen['Situación'] = situaciones

    # Por defecto manda la clasificación de la liga (columna Puntos, que él
    # rellena a mano jornada a jornada). Si aún no hay puntos, el patrimonio.
    if 'Puntos' in resumen.columns and pd.to_numeric(resumen['Puntos'], errors='coerce').fillna(0).abs().sum() > 0:
        resumen = resumen.sort_values('Puntos', ascending=False)
    else:
        resumen = resumen.sort_values('Patrimonio Total (€)', ascending=False)
    resumen = resumen.reset_index(drop=True)
    resumen.insert(0, 'Puesto', range(1, len(resumen) + 1))
    # ⭐ Marca tu propia fila: entre diez colores pastel no había forma de
    # localizarte de un vistazo.
    resumen['Persona'] = resumen['Persona'].apply(
        lambda n: f"⭐ {n}" if n == MI_EQUIPO else n
    )
    return resumen


CSS_PARTICIPANTES = """
<style>
.pa-cab { display:flex; align-items:center; gap:16px; margin:6px 0 18px 0; }
.pa-cab::before { content:''; flex:1; height:1px; background:linear-gradient(90deg, transparent, rgba(231,197,101,0.4)); }
.pa-cab::after { content:''; flex:1; height:1px; background:linear-gradient(90deg, rgba(231,197,101,0.4), transparent); }
.pa-cab span { color:#e7c565; font-size:0.74rem; font-weight:700; letter-spacing:0.26em; text-transform:uppercase; }
.st-key-participantes_orden { display:flex; justify-content:center; width:100% !important; }
.st-key-participantes_orden > div { width:auto !important; }
.pa-grid { display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); grid-auto-rows:1fr; gap:14px; margin-top:10px; }
@media (max-width: 1400px) { .pa-grid { grid-template-columns:repeat(4, minmax(0, 1fr)); } }
@media (max-width: 1100px) { .pa-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
.pa-card { position:relative; overflow:hidden; display:flex; flex-direction:column; gap:12px; padding:18px 18px 16px;
           border-radius:18px; background:linear-gradient(180deg, #1c202a, #14171e);
           border:1px solid rgba(255,255,255,0.08); box-shadow:0 10px 26px rgba(0,0,0,0.3); }
.pa-card::before { content:''; position:absolute; top:0; left:0; right:0; height:4px; background:var(--c); }
.pa-card.mio { border-color:rgba(231,197,101,0.6); box-shadow:0 0 0 1px rgba(231,197,101,0.25), 0 12px 30px rgba(231,197,101,0.10); }
.pa-cabeza { display:flex; align-items:center; gap:10px; }
.pa-puesto { width:34px; height:34px; border-radius:50%; flex:none; display:flex; align-items:center; justify-content:center;
             background:var(--c); color:#0b0e14; font-weight:900; font-size:0.9rem; font-family:'Inter', sans-serif !important; }
.pa-nombre { min-width:0; }
.pa-nombre b { display:block; color:#fff; font-size:1rem; font-weight:800; white-space:nowrap; overflow:hidden;
               text-overflow:ellipsis; font-family:'Inter', sans-serif !important; }
.pa-nombre span { color:#8b93a7; font-size:0.7rem; }
.pa-principal { container-type:inline-size; display:flex; flex-direction:column; align-items:center; gap:6px;
                padding:12px 10px; border-radius:12px; text-align:center;
                background:rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.06); }
.pa-principal .rot { color:#8b93a7; font-size:0.6rem; font-weight:700; letter-spacing:0.16em; text-transform:uppercase;
                     white-space:nowrap; }
.pa-principal .val { color:#f4f6fa; font-size:1.55rem; font-weight:800; line-height:1.05; font-variant-numeric:tabular-nums;
                     font-family:'Inter', sans-serif !important; white-space:nowrap; }
@container (max-width: 250px) { .pa-principal .val { font-size:1.3rem; } }
@container (max-width: 210px) { .pa-principal .val { font-size:1.1rem; } }
.pa-principal .val small { font-size:0.7rem; color:#8b93a7; font-weight:600; margin-left:3px; }
.pa-filas { display:flex; flex-direction:column; gap:7px; }
.pa-fila { display:flex; align-items:baseline; justify-content:space-between; gap:8px; font-size:0.78rem; }
.pa-fila span { color:#8b93a7; white-space:nowrap; }
.pa-fila b { color:#e5e9f0; font-weight:700; font-variant-numeric:tabular-nums; white-space:nowrap;
             font-family:'Inter', sans-serif !important; }
.pa-barra { height:5px; border-radius:3px; background:rgba(255,255,255,0.07); overflow:hidden; margin-top:-2px; }
.pa-barra i { display:block; height:100%; border-radius:3px; background:var(--c); }
.pa-lineas { display:flex; gap:4px; flex-wrap:wrap; }
.pa-lineas span { background:rgba(255,255,255,0.06); border-radius:999px; padding:2px 8px; font-size:0.66rem; color:#aab3c2; }
.pa-lineas span b { color:#f4f6fa; margin-left:3px; font-family:'Inter', sans-serif !important; }
.pa-pie { margin-top:auto; display:flex; flex-wrap:wrap; gap:6px; }
.pa-tag { border-radius:999px; padding:3px 10px; font-size:0.66rem; font-weight:700; white-space:nowrap; }
.pa-tag.rojo { background:rgba(248,113,113,0.12); color:#fca5a5; border:1px solid rgba(248,113,113,0.3); }
.pa-tag.ambar { background:rgba(251,191,36,0.10); color:#fcd34d; border:1px solid rgba(251,191,36,0.3); }
.pa-tag.gris { background:rgba(255,255,255,0.05); color:#c3cbd9; border:1px solid rgba(255,255,255,0.1); }
</style>
"""

# Solo tres órdenes: la clasificación (por defecto), el valor y la subida del día.
ORDENES_PARTICIPANTES = {
    "Puntos de liga": ('Puntos', False),
    "Valor de equipo": ('Valor de Equipo (€)', False),
    "Variación diaria": ('Variación Diaria (€)', False),
}


def ficha_participante_html(fila, orden, maximos, delante):
    nombre = str(fila['Persona']).replace('⭐ ', '')
    color = COLORES_MANAGERS.get(nombre, '#8b93a7')
    es_mio = nombre == MI_EQUIPO
    puntos = int(_a_float(fila.get('Puntos'), 0) or 0)
    valor = _a_float(fila.get('Valor de Equipo (€)'), 0.0) or 0.0
    var = _a_float(fila.get('Variación Diaria (€)'), 0.0) or 0.0
    saldo = _a_float(fila.get('Balance Total (€)'), 0.0) or 0.0
    patrimonio = _a_float(fila.get('Patrimonio Total (€)'), 0.0) or 0.0
    color_var = '#4ade80' if var > 0 else '#f87171' if var < 0 else '#8b93a7'

    # La cifra grande es la del orden elegido.
    if orden == "Valor de equipo":
        rot, val = "Valor de equipo", formato_euro(valor)
    elif orden == "Variación diaria":
        rot, val = "Variación de hoy", f"<span style='color:{color_var};'>{formato_tendencia(var) if var else '0 €'}</span>"
    else:
        rot, val = "Puntos de liga", f"{puntos}<small>pts</small>"
    # La distancia, con el que tiene justo delante en la clasificación.
    if delante is None:
        distancia = "líder de la liga"
    elif delante[1] == puntos:
        distancia = f"empatado con {delante[0]}"
    else:
        distancia = f"a {delante[1] - puntos} puntos de {delante[0]}"

    lineas = str(fila.get('Plantilla') or '').split('-')
    chips_lineas = "".join(f"<span>{r}<b>{n}</b></span>" for r, n in zip(('POR', 'DEF', 'MED', 'DEL'), lineas)
                           if len(lineas) == 4)
    lesionados = int(fila.get('Lesionados') or 0)

    tags = []
    situacion = str(fila.get('Situación') or '').strip()
    if situacion == 'Obligado a vender':
        tags.append("<span class='pa-tag rojo'>Tendrá que vender</span>")
    elif situacion == 'Sin margen':
        tags.append("<span class='pa-tag ambar'>Sin margen para vender</span>")
    pegas = fila.get('_pegas') or []
    if pegas:
        tags.append(f"<span class='pa-tag rojo'>⚠️ {', '.join(pegas).capitalize()}</span>")
    perfil = str(fila.get('Perfil de Fichajes') or '').strip()
    if perfil:
        tags.append(f"<span class='pa-tag gris' title='{perfil}'>{perfil.split(':')[0]}</span>")

    def fila_dato(rotulo, valor_html):
        return f"<div class='pa-fila'><span>{rotulo}</span><b>{valor_html}</b></div>"

    ancho_valor = valor / maximos['valor'] * 100 if maximos['valor'] else 0
    ancho_puntos = puntos / maximos['puntos'] * 100 if maximos.get('puntos') else 0
    hoy_html = f"<span style='color:{color_var};'>{formato_tendencia(var) if var else '0 €'}</span>"
    # La fila que repetiría la cifra grande se cambia por los puntos de liga.
    if orden == "Valor de equipo":
        primera = (fila_dato("Puntos de liga", f"{puntos} pts")
                   + f"<div class='pa-barra'><i style='width:{ancho_puntos:.0f}%;'></i></div>"
                   + fila_dato("Hoy", hoy_html))
    else:
        primera = (fila_dato("Valor de equipo", formato_euro(valor))
                   + f"<div class='pa-barra'><i style='width:{ancho_valor:.0f}%;'></i></div>"
                   + (fila_dato("Puntos de liga", f"{puntos} pts") if orden == "Variación diaria"
                      else fila_dato("Hoy", hoy_html)))
    return (f"<div class='pa-card{' mio' if es_mio else ''}' style='--c:{color};'>"
            f"<div class='pa-cabeza'><div class='pa-puesto'>{fila['Puesto']}</div>"
            f"<div class='pa-nombre'><b>{'★ ' if es_mio else ''}{nombre}</b><span>{distancia}</span></div></div>"
            f"<div class='pa-principal'><span class='rot'>{rot}</span><span class='val'>{val}</span></div>"
            "<div class='pa-filas'>"
            + primera
            + fila_dato("Saldo", f"<span style='color:{'#f87171' if saldo < 0 else '#e5e9f0'};'>{formato_euro(saldo)}</span>")
            + fila_dato("Patrimonio", formato_euro(patrimonio))
            + fila_dato("Plantilla", f"{int(fila.get('Jugadores') or 0)} jugadores"
                        + (f" · <span style='color:#f87171;'>{lesionados} 🚑</span>" if lesionados else ""))
            + "</div>"
            f"<div class='pa-lineas'>{chips_lineas}</div>"
            f"<div class='pa-pie'>{''.join(tags)}</div></div>")


def ui_participantes():
    resumen = resumen_participantes()
    if resumen.empty:
        st.warning("No hay participantes en la base de datos.")
        return
    st.markdown(CSS_PARTICIPANTES + "<div class='pa-cab'><span>Participantes</span></div>", unsafe_allow_html=True)
    if st.session_state.get('participantes_orden') not in ORDENES_PARTICIPANTES:
        st.session_state.pop('participantes_orden', None)
    orden = _selector_pildoras("Ordenar por", list(ORDENES_PARTICIPANTES), "participantes_orden")
    columna, asc = ORDENES_PARTICIPANTES[orden]
    if columna in resumen.columns:
        resumen = (resumen.assign(_o=pd.to_numeric(resumen[columna], errors='coerce'))
                   .sort_values('_o', ascending=asc).reset_index(drop=True))
        resumen['Puesto'] = range(1, len(resumen) + 1)
    maximos = {'valor': float(pd.to_numeric(resumen['Valor de Equipo (€)'], errors='coerce').max() or 0),
               'puntos': float(pd.to_numeric(resumen['Puntos'], errors='coerce').max() or 0)}
    clasificacion = sorted(((str(f['Persona']).replace('⭐ ', ''), int(_a_float(f.get('Puntos'), 0) or 0))
                           for _, f in resumen.iterrows()), key=lambda x: -x[1])
    delante_de = {n: (clasificacion[i - 1] if i else None) for i, (n, _) in enumerate(clasificacion)}
    fichas = "".join(ficha_participante_html(f, orden, maximos, delante_de.get(str(f['Persona']).replace('⭐ ', '')))
                     for _, f in resumen.iterrows())
    st.markdown(CSS_PARTICIPANTES + f"<div class='pa-grid'>{fichas}</div>", unsafe_allow_html=True)


# La pestaña Participantes se pinta más abajo, junto a Mercado.


# ==========================================
# 📒 PESTAÑA: AUDITORÍA CONTABLE (OPTIMIZADA)
# ==========================================
# --- 🧾 TARJETAS DE MOVIMIENTO (pestaña Movimientos) ---
# Reaprovechan la carta de jugador de siempre cambiándole dos números: donde va
# el valor de mercado va el IMPORTE pagado o cobrado, y donde va la variación
# diaria va la SOBREPUJA. Debajo, una pastilla con el tipo de operación, con el
# mismo estilo que el badge de próximo rival (que se apaga: en un movimiento
# pasado no pinta nada el partido que viene).
ESTILO_MOVIMIENTO = {
    'Compra': ('#0f2f4d', '#60a5fa', '🛒'),
    'Venta':  ('#4d3a0f', '#fbbf24', '💸'),
    'Abono':  ('#0f4d2b', '#22c55e', '💶'),
}
ALTO_CARTA_MOV = 196   # alto aproximado de la carta, para que el abono cuadre


def _bloque_abono_html(importe):
    """Un abono no tiene jugador detrás, así que en vez de carta lleva un bloque
    del mismo tamaño con el icono del euro."""
    return (
        f'<div style="width:125px; height:{ALTO_CARTA_MOV}px; box-sizing:border-box; '
        'border-radius:8px; background: linear-gradient(180deg, #14532d 0%, #111 100%); '
        'border:2px solid #22c55e; box-shadow:0 4px 8px rgba(0,0,0,0.8); display:flex; '
        'flex-direction:column; align-items:center; justify-content:center; gap:8px;">'
        '<div style="font-size:2.6rem; line-height:1;">💶</div>'
        '<div style="color:#86efac; font-weight:900; letter-spacing:1px; '
        'text-transform:uppercase; font-size:0.8rem;">Abono</div>'
        f'<div style="color:#eee; font-weight:800; font-size:0.95rem;">{formato_euro(importe)}</div>'
        '</div>'
    )


def carta_movimiento_html(fila, mostrar_persona=True):
    """Una tarjeta por movimiento: carta (o bloque de abono) + pastilla del tipo."""
    tipo = str(fila.get('Tipo de Operación', '')).strip()
    color_fondo, color_borde, icono = ESTILO_MOVIMIENTO.get(tipo, ('#374151', '#9ca3af', '📄'))
    importe = fila.get('Importe (€)')
    jugador = fila.get('Jugador')
    sin_jugador = pd.isna(jugador) or str(jugador).strip() in ('', '—', 'Ingreso / Premio')

    if tipo == 'Abono' or sin_jugador:
        contenido = _bloque_abono_html(importe)
        pie_titulo = 'Abono'
    else:
        # Datos del jugador si sigue en el mercado; si ya no está (vendido a la
        # nada, cambio de liga...), se construye una ficha mínima con lo que
        # guardó la Contabilidad ese día.
        coincide = db['mercado'][db['mercado']['Jugador'] == jugador]
        datos = dict(coincide.iloc[0]) if not coincide.empty else {
            'Jugador': jugador,
            'Equipo': fila.get('Equipo') if pd.notna(fila.get('Equipo')) else 'Desconocido',
            'Posición': fila.get('Posición') if pd.notna(fila.get('Posición')) else 'Centrocampista',
            'Puntos': 0, 'Media Puntos': 0,
        }
        datos['Valor Actual (€)'] = importe
        datos['Variación Diaria (€)'] = fila.get('Sobrepuja (€)')
        pos_principal = str(datos.get('Posición', 'Centrocampista')).split('/')[0].strip()
        tipo_pos = ('POR' if pos_principal == 'Portero' else 'DEF' if pos_principal == 'Defensa'
                    else 'MED' if pos_principal == 'Centrocampista' else 'DEL')
        contenido = generar_carta_html(datos, tipo_pos, mostrar_proximo_rival=False,
                                       variacion_invertida=True)
        pie_titulo = tipo or 'Movimiento'

    # 💬 El valor de mercado del día del fichaje va en el tooltip. La sobrepuja,
    # solo en las compras: en una venta no existe.
    valor_mercado = fila.get('Valor Mercado (€)')
    if pd.notna(valor_mercado):
        ayuda = f"Valor de mercado ese día: {formato_euro(valor_mercado)}"
        sobrepuja = fila.get('Sobrepuja (€)')
        if tipo == 'Compra' and pd.notna(sobrepuja):
            ayuda += f" · Sobrepuja: {formato_euro(sobrepuja)}"
    else:
        ayuda = "Sin valor de mercado registrado para este movimiento"

    persona = fila.get('Persona')
    persona_txt = str(persona) if pd.notna(persona) else '—'
    persona_html = (
        f'<div style="color:#9aa3b2; font-size:0.7rem; font-weight:700; text-align:center; '
        f'max-width:132px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{persona_txt}</div>'
    ) if mostrar_persona else ''

    return (
        f'<div title="{ayuda}" style="display:flex; flex-direction:column; align-items:center; '
        'gap:7px; width:132px; flex:none;">'
        f'{contenido}'
        f'<div style="display:flex; align-items:center; gap:4px; background:{color_fondo}; '
        f'border:1px solid {color_borde}; border-radius:12px; padding:3px 9px; '
        'box-shadow:0 2px 4px rgba(0,0,0,0.6); white-space:nowrap;">'
        f'<span style="font-size:0.75rem; line-height:1;">{icono}</span>'
        f'<span style="color:#eee; font-size:0.7rem; font-weight:800; text-transform:uppercase; '
        f'letter-spacing:0.5px;">{pie_titulo}</span></div>'
        f'{persona_html}'
        '</div>'
    )


PODIO_ESTILOS = [
    # (medalla, color, escala de la carta, alto del cajón, margen sobre la medalla)
    ('🥇', '#ffd700', 1.12, 70, 45),
    ('🥈', '#c0c0c0', 0.95, 40, 15),
    ('🥉', '#cd7f32', 0.85, 25, 10),
]
ORDEN_PODIO = [1, 0, 2]   # plata, oro, bronce: el primero va en el centro


CSS_MOVIMIENTOS = """
<style>
.mv-cab { display:flex; align-items:center; gap:16px; margin:6px 0 20px 0; }
.mv-cab::before { content:''; flex:1; height:1px; background:linear-gradient(90deg, transparent, rgba(231,197,101,0.4)); }
.mv-cab::after { content:''; flex:1; height:1px; background:linear-gradient(90deg, rgba(231,197,101,0.4), transparent); }
.mv-cab span { color:#e7c565; font-size:0.74rem; font-weight:700; letter-spacing:0.26em; text-transform:uppercase; }
.st-key-mov_tipo { display:flex; justify-content:center; }
.st-key-mov_tipo > div { width:auto !important; }
.mv-cuenta { text-align:center; color:#7d8699; font-size:0.78rem; margin:10px 0 2px 0; }

/* Movimientos: ocho por fila */
.mv-grid { display:grid; grid-template-columns:repeat(8, minmax(0, 1fr)); gap:14px; margin-top:8px; }
.mv-tile { container-type:inline-size; display:flex; flex-direction:column; align-items:center; gap:9px;
           padding:22px 6px 14px; border-radius:16px; background:linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.012));
           border:1px solid rgba(255,255,255,0.07); border-top:3px solid var(--c); }
.mv-carta { display:flex; justify-content:center; zoom:1.25; }
@container (max-width: 205px) { .mv-carta { zoom:1.12; } }
@container (max-width: 180px) { .mv-carta { zoom:1.0; } }
@container (max-width: 155px) { .mv-carta { zoom:0.85; } }
.mv-tipo { display:flex; align-items:center; gap:5px; border-radius:999px; padding:3px 10px; font-size:0.64rem;
           font-weight:800; letter-spacing:0.08em; text-transform:uppercase; color:#eef2f7; }
.mv-quien { display:flex; align-items:center; gap:6px; color:#e5e9f0; font-size:0.82rem; font-weight:700;
            max-width:100%; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.mv-quien i { width:8px; height:8px; border-radius:50%; flex:none; }
.mv-fecha { color:#7d8699; font-size:0.72rem; }

/* Subastas disputadas: línea de tiempo por días, la más reciente arriba */
.mv-dia { display:flex; align-items:center; gap:12px; margin:22px 0 10px 0; }
.mv-dia b { color:#f4f6fa; font-size:0.78rem; font-weight:800; letter-spacing:0.14em; text-transform:uppercase;
            font-family:'Inter', sans-serif !important; }
.mv-dia span { color:#7d8699; font-size:0.72rem; }
.mv-dia::before { content:''; width:12px; height:12px; border-radius:50%; background:#e7c565;
                  box-shadow:0 0 0 4px rgba(231,197,101,0.18); flex:none; }
.mv-dia::after { content:''; flex:1; height:1px; background:rgba(255,255,255,0.08); }
.mv-linea { margin-left:5px; padding-left:22px; border-left:2px solid rgba(231,197,101,0.18);
            display:flex; flex-direction:column; gap:10px; }
.mv-sub { position:relative; display:grid; grid-template-columns:54px minmax(220px, 280px) minmax(0, 1fr) 150px;
          align-items:center; gap:18px; padding:14px 18px; border-radius:16px;
          background:linear-gradient(90deg, #1f2430, #181b23); border:1px solid rgba(255,255,255,0.07); }
.mv-sub::before { content:''; position:absolute; left:-29px; top:50%; width:10px; height:10px; margin-top:-5px;
                  border-radius:50%; background:#11141b; border:2px solid rgba(231,197,101,0.55); }
.mv-sub.mia { border-color:rgba(231,197,101,0.45); background:linear-gradient(90deg, rgba(231,197,101,0.08), #181b23); }
.mv-sub.ultima { border-color:rgba(74,222,128,0.45); }
.mv-num { display:flex; flex-direction:column; align-items:center; gap:4px; }
.mv-num b { width:38px; height:38px; border-radius:50%; display:flex; align-items:center; justify-content:center;
            background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12); color:#f4f6fa;
            font-size:0.9rem; font-weight:800; font-family:'Inter', sans-serif !important; }
.mv-num span { font-size:0.54rem; font-weight:800; letter-spacing:0.12em; text-transform:uppercase; color:#86efac; }
.mv-jug { display:flex; align-items:center; gap:12px; min-width:0; }
.mv-jug img, .mv-jug .ini { width:52px; height:52px; border-radius:50%; object-fit:cover; flex:none;
                            border:2px solid rgba(255,255,255,0.14); background:#11141b; }
.mv-jug .ini { display:flex; align-items:center; justify-content:center; font-weight:800; color:#0b0e14; }
.mv-jug-nombre { color:#fff; font-weight:800; font-size:1rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mv-jug-meta { color:#8b93a7; font-size:0.72rem; margin-top:3px; }
.mv-escalera { display:flex; align-items:stretch; gap:8px; flex-wrap:wrap; }
.mv-oferta { display:flex; flex-direction:column; justify-content:center; gap:2px; min-width:140px; padding:8px 12px;
             border-radius:12px; background:rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.08);
             border-left:3px solid var(--c); }
.mv-oferta .q { color:#c3cbd9; font-size:0.72rem; font-weight:700; white-space:nowrap; }
.mv-oferta .c { color:#f4f6fa; font-size:0.95rem; font-weight:800; font-variant-numeric:tabular-nums;
                font-family:'Inter', sans-serif !important; white-space:nowrap; }
.mv-oferta .d { color:#fca5a5; font-size:0.66rem; font-weight:600; white-space:nowrap; }
.mv-oferta.gana { background:linear-gradient(180deg, rgba(231,197,101,0.18), rgba(231,197,101,0.05));
                  border-color:rgba(231,197,101,0.5); border-left-color:#e7c565; min-width:170px; }
.mv-oferta.gana .q { color:#e7c565; }
.mv-oferta.gana .c { font-size:1.08rem; }
.mv-oferta.gana .d { color:#e7c565; opacity:0.8; }
.mv-resumen { text-align:right; }
.mv-resumen b { display:block; color:#f4f6fa; font-size:1rem; font-weight:800; font-family:'Inter', sans-serif !important; }
.mv-resumen span { color:#7d8699; font-size:0.66rem; }
</style>
"""


def _fecha_mov(fila):
    fecha = pd.to_datetime(fila.get('Fecha Fichaje'), errors='coerce')
    return fecha if pd.notna(fecha) and fecha.year > 2000 else None


def _tile_movimiento(fila):
    tipo = str(fila.get('Tipo de Operación', '')).strip()
    fondo, borde, icono = ESTILO_MOVIMIENTO.get(tipo, ('#374151', '#9ca3af', '📄'))
    tarjeta = carta_movimiento_html(fila, mostrar_persona=False)
    # La carta de siempre, sin su pastilla (va aquí abajo, con el mánager y el día).
    persona = str(fila.get('Persona')) if pd.notna(fila.get('Persona')) else '—'
    color_m = COLORES_MANAGERS.get(persona, '#8b93a7')
    fecha = _fecha_mov(fila)
    return (f"<div class='mv-tile' style='--c:{borde};'><div class='mv-carta'>{tarjeta}</div>"
            f"<div class='mv-quien' title='{persona}'><i style='background:{color_m};'></i>{persona}</div>"
            + (f"<div class='mv-fecha'>{fecha:%d/%m/%Y}</div>" if fecha is not None else "")
            + "</div>")


def _subastas_disputadas(df_conta, manager=None, busqueda=""):
    """Cada compra en la que pujó más de uno: el ganador y los que se quedaron
    fuera, de la más reciente a la más antigua."""
    subastas = []
    for _, fila in df_conta.iloc[::-1].iterrows():
        if fila.get('Tipo de Operación') != 'Compra':
            continue
        perdidas = []
        for i in range(1, 10):
            quien, cuanto = fila.get(f'Manager {i}'), fila.get(f'Subasta perdida {i}')
            if pd.notna(quien) and str(quien).strip():
                perdidas.append((str(quien).strip(), _a_float(cuanto, None)))
        if not perdidas:
            continue
        ganador = str(fila.get('Persona')).strip()
        if manager and manager != ganador and manager not in [q for q, _ in perdidas]:
            continue
        jugador = str(fila.get('Jugador') or '').strip()
        if busqueda and busqueda.lower() not in jugador.lower() \
                and busqueda.lower() not in str(fila.get('Equipo') or '').lower():
            continue
        subastas.append({'fila': fila, 'ganador': ganador, 'importe': _a_float(fila.get('Importe (€)'), None),
                         'perdidas': sorted(perdidas, key=lambda x: -(x[1] or 0))})
    return subastas


def _tarjeta_subasta(sub, numero):
    """Una subasta en la línea de tiempo: su número (1 = la última), el jugador
    y las pujas de mayor a menor, con el ganador en dorado."""
    fila = sub['fila']
    jugador = str(fila.get('Jugador') or '').strip()
    equipo = str(fila.get('Equipo') or '').strip()
    pos = _pos_principal(fila.get('Posición'))
    color_pos = COLOR_POSICION.get(pos, '#6b7280')
    url = url_imagen(f"caras/{jugador}.png", f"caras/{jugador}.jpg")
    cara = (f"<img src='{url}' style='border-color:{color_pos};'>" if url else
            f"<div class='ini' style='background:{color_pos};'>{''.join(p[0] for p in jugador.split()[:2]).upper()}</div>")
    valor = _a_float(fila.get('Valor Mercado (€)'), None)
    meta = " · ".join(x for x in (equipo, ABREVIA_POSICION.get(pos, ''),
                                  f"valía {formato_euro(valor)}" if valor else "") if x)
    importe = sub['importe']
    ofertas = [f"<div class='mv-oferta gana' style='--c:#e7c565;'><div class='q'>🏆 {sub['ganador']}</div>"
               f"<div class='c'>{formato_euro(importe) if importe else '—'}</div>"
               + (f"<div class='d'>{(importe / valor - 1) * 100:+.0f}% sobre su valor</div>" if importe and valor else "")
               + "</div>"]
    for quien, cuanto in sub['perdidas']:
        color_m = COLORES_MANAGERS.get(quien, '#8b93a7')
        ofertas.append(f"<div class='mv-oferta' style='--c:{color_m};'><div class='q'>{quien}</div>"
                       f"<div class='c'>{formato_euro(cuanto) if cuanto else '—'}</div>"
                       + (f"<div class='d'>a {formato_euro(importe - cuanto)}</div>" if cuanto and importe else "")
                       + "</div>")
    segunda = sub['perdidas'][0][1] if sub['perdidas'] else None
    margen = (f"<b>{formato_euro(importe - segunda)}</b><span>de margen sobre el 2º</span>"
              if importe and segunda else f"<b>{len(sub['perdidas']) + 1}</b><span>pujas</span>")
    mia = MI_EQUIPO == sub['ganador'] or MI_EQUIPO in [q for q, _ in sub['perdidas']]
    clases = "mv-sub" + (" mia" if mia else "") + (" ultima" if numero == 1 else "")
    return (f"<div class='{clases}'><div class='mv-num'><b>{numero}</b>"
            + ("<span>Última</span>" if numero == 1 else "") + "</div>"
            f"<div class='mv-jug'>{cara}<div style='min-width:0;'><div class='mv-jug-nombre'>{jugador}</div>"
            f"<div class='mv-jug-meta'>{meta}</div></div></div>"
            f"<div class='mv-escalera'>{''.join(ofertas)}</div>"
            f"<div class='mv-resumen'>{margen}</div></div>")


def _linea_de_tiempo_subastas(subastas):
    """Agrupadas por día, de la más reciente a la más antigua."""
    hoy = pd.Timestamp.now().normalize()
    bloques, dia_actual, numero = [], None, 0
    for sub in subastas:
        numero += 1
        fecha = _fecha_mov(sub['fila'])
        dia = fecha.normalize() if fecha is not None else None
        if dia != dia_actual or numero == 1:
            if bloques:
                bloques.append("</div>")
            if dia is None:
                rotulo, detalle = "Sin fecha", ""
            else:
                dias = (hoy - dia).days
                rotulo = "Hoy" if dias == 0 else "Ayer" if dias == 1 else f"{DIAS_SEMANA_CAL[dia.weekday()]}"
                detalle = f"{dia:%d/%m/%Y}"
            bloques.append(f"<div class='mv-dia'><b>{rotulo}</b><span>{detalle}</span></div><div class='mv-linea'>")
            dia_actual = dia
        bloques.append(_tarjeta_subasta(sub, numero))
    if bloques:
        bloques.append("</div>")
    return "".join(bloques)


def _pagina_movimientos(pagina):
    st.session_state['mov_pagina'] = pagina


@st.fragment
def ui_auditoria():
    df_compras = db['contabilidad'][db['contabilidad']['Tipo de Operación'] == 'Compra'].copy()
    df_compras['_sobrepuja'] = pd.to_numeric(df_compras['Sobrepuja (€)'], errors='coerce')
    mercado_hoy = db['mercado'].dropna(subset=['Jugador']).copy()
    mercado_hoy['_k'] = (mercado_hoy['Jugador'].astype(str).str.strip() + '||'
                         + mercado_hoy['Equipo'].astype(str).str.strip())
    valores_hoy = mercado_hoy.drop_duplicates('_k').set_index('_k')['Valor Actual (€)'].to_dict()
    df_compras['_valor_hoy'] = pd.to_numeric(
        (df_compras['Jugador'].astype(str).str.strip() + '||' + df_compras['Equipo'].astype(str).str.strip())
        .map(valores_hoy), errors='coerce')
    df_compras['_plusvalia'] = df_compras['_valor_hoy'] - pd.to_numeric(df_compras['Importe (€)'], errors='coerce')

    # 🎛️ Filtros en una línea: mánager, tipo en botones y buscador.
    st.markdown(CSS_MOVIMIENTOS + "<div class='mv-cab'><span>Movimientos</span></div>", unsafe_allow_html=True)
    managers = sorted(db['contabilidad']['Persona'].dropna().astype(str).unique().tolist())
    try:
        c_man, c_tipo, c_bus = st.columns([1.1, 1.6, 1.3], vertical_alignment="center")
    except TypeError:
        c_man, c_tipo, c_bus = st.columns([1.1, 1.6, 1.3])
    manager_filtro = c_man.selectbox("Mánager", ["Todos los mánagers"] + managers, key="mov_manager",
                                     label_visibility="collapsed")
    with c_tipo:
        tipo_filtro = _selector_pildoras("Tipo", ["Todas", "Compras", "Ventas", "Abonos"], "mov_tipo")
    busqueda = c_bus.text_input("Buscar", placeholder="🔍  Buscar jugador o equipo", key="auditoria_busqueda",
                                label_visibility="collapsed")
    manager = None if manager_filtro == "Todos los mánagers" else manager_filtro
    tipo = {"Compras": "Compra", "Ventas": "Venta", "Abonos": "Abono"}.get(tipo_filtro)

    df = db['contabilidad'].copy()
    df['Jugador'] = df['Jugador'].fillna('Ingreso / Premio')
    if manager:
        df = df[df['Persona'] == manager]
    if tipo:
        df = df[df['Tipo de Operación'] == tipo]
    if busqueda:
        texto = busqueda.strip()
        df = df[df['Jugador'].astype(str).str.contains(texto, case=False, na=False, regex=False)
                | df['Equipo'].astype(str).str.contains(texto, case=False, na=False, regex=False)]

    # 🃏 Los movimientos: una sola fila de ocho, del más reciente al más antiguo.
    movimientos = df.iloc[::-1].to_dict('records')
    total = len(movimientos)
    if total == 0:
        st.markdown("<div class='mv-cuenta' style='margin:30px 0;'>Ningún movimiento con esos filtros.</div>",
                    unsafe_allow_html=True)
    else:
        por_pagina = 8
        paginas = max(1, -(-total // por_pagina))
        firma = (manager, tipo, busqueda)
        if st.session_state.get('mov_firma') != firma:
            st.session_state['mov_firma'] = firma
            st.session_state['mov_pagina'] = 1
        pagina = min(max(1, int(st.session_state.get('mov_pagina', 1))), paginas)
        trozo = movimientos[(pagina - 1) * por_pagina: pagina * por_pagina]
        st.markdown(CSS_MOVIMIENTOS + f"<div class='mv-grid'>{''.join(_tile_movimiento(m) for m in trozo)}</div>"
                    f"<div class='mv-cuenta'>{(pagina - 1) * por_pagina + 1} – {min(pagina * por_pagina, total)} "
                    f"de {total} · del más reciente al más antiguo</div>", unsafe_allow_html=True)
        if paginas > 1:
            ventana = list(range(max(1, pagina - 2), min(paginas, pagina + 2) + 1))
            botones = ([("«", 1), ("‹", max(1, pagina - 1))] + [(str(p), p) for p in ventana]
                       + [("›", min(paginas, pagina + 1)), ("»", paginas)])
            columnas = st.columns([4] + [0.55] * len(botones) + [4])
            for col, (texto, destino) in zip(columnas[1:-1], botones):
                col.button(texto, key=f"mov_pag_{texto}_{destino}", use_container_width=True,
                           type="primary" if texto == str(pagina) else "secondary",
                           disabled=(destino == pagina and not texto.isdigit()),
                           on_click=_pagina_movimientos, args=(destino,))

    # ⚔️ Subastas disputadas (antes, "pujas perdidas" en una tabla).
    if any(f'Manager {i}' in db['contabilidad'].columns for i in range(1, 10)):
        subastas = _subastas_disputadas(db['contabilidad'], manager, busqueda.strip() if busqueda else "")
        st.markdown(CSS_MOVIMIENTOS + "<div class='mv-cab' style='margin-top:44px;'><span>Subastas disputadas</span></div>",
                    unsafe_allow_html=True)
        if not subastas:
            st.markdown("<div class='mv-cuenta'>Ninguna subasta con más de un pujador con esos filtros.</div>",
                        unsafe_allow_html=True)
            return
        cuantas = int(st.session_state.get('mov_subastas_ver', 8))
        st.markdown(CSS_MOVIMIENTOS + _linea_de_tiempo_subastas(subastas[:cuantas])
                    + f"<div class='mv-cuenta'>{min(cuantas, len(subastas))} de {len(subastas)} subastas disputadas</div>",
                    unsafe_allow_html=True)
        if cuantas < len(subastas):
            _, c_mas, _ = st.columns([2, 1, 2])
            if c_mas.button("Ver más subastas", key="mov_subastas_mas", use_container_width=True):
                st.session_state['mov_subastas_ver'] = cuantas + 8
                st.rerun(scope="fragment")


# La pestaña Movimientos se pinta más abajo, junto a Mercado.



# ==========================================
# 👕 PESTAÑA: EXPLORADOR DE PLANTILLAS (OPTIMIZADA)
# ==========================================
# El primero de este diccionario es el que sale por defecto en el selector.
ORDENES_PLANTILLA = {
    "Por posición": None,
    "Valor": ('Valor Actual (€)', False),
    "Puntos": ('Puntos', False),
    "Media de puntos": ('Media Puntos', False),
    "Subida de valor": ('Variación Diaria (€)', False),
}
ORDEN_LINEAS = {'Portero': 0, 'Defensa': 1, 'Centrocampista': 2, 'Delantero': 3}

CSS_PLANTILLAS = """
<style>
.pl-cab { display:flex; align-items:center; gap:16px; margin:6px 0 20px 0; }
.pl-cab::before { content:''; flex:1; height:1px; background:linear-gradient(90deg, transparent, rgba(231,197,101,0.4)); }
.pl-cab::after { content:''; flex:1; height:1px; background:linear-gradient(90deg, rgba(231,197,101,0.4), transparent); }
.pl-cab span { color:#e7c565; font-size:0.74rem; font-weight:700; letter-spacing:0.26em; text-transform:uppercase; }

/* Resumen: seis fichas iguales */
.pl-resumen { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); grid-auto-rows:1fr;
              gap:12px; margin:4px 0 26px 0; }
.pl-kpi { position:relative; overflow:hidden; display:flex; flex-direction:column; align-items:center;
          justify-content:center; text-align:center; gap:6px; padding:16px 12px; border-radius:16px;
          background:linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.015));
          border:1px solid rgba(255,255,255,0.08); }
.pl-kpi::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:var(--c, #e7c565); }
.pl-kpi-rot { color:#8b93a7; font-size:0.62rem; font-weight:700; letter-spacing:0.16em; text-transform:uppercase; }
.pl-kpi-val { color:#f4f6fa; font-size:1.6rem; font-weight:800; line-height:1.05; letter-spacing:-0.01em;
              font-variant-numeric:tabular-nums; font-family:'Inter', sans-serif !important; white-space:nowrap; }
.pl-kpi-sub { color:#8b93a7; font-size:0.72rem; }
.pl-kpi-sub b { font-family:'Inter', sans-serif !important; }
.pl-chips { display:flex; gap:4px; flex-wrap:wrap; justify-content:center; }
.pl-chip { background:rgba(255,255,255,0.07); border-radius:999px; padding:2px 8px; font-size:0.68rem; color:#c3cbd9; }
.pl-chip b { color:#f4f6fa; margin-left:3px; font-family:'Inter', sans-serif !important; }

/* Lista de jugadores + escenario con la carta */
.pl-wrap { position:relative; display:grid; grid-template-columns:minmax(0, 1fr) 360px; gap:22px; align-items:start; }
.pl-lista { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:10px; }
.pl-item { display:flex; }
.pl-card { flex:1; display:flex; flex-direction:column; position:relative; border-radius:14px; background:linear-gradient(180deg, #232733, #1c2029);
           border:1px solid rgba(255,255,255,0.07); overflow:hidden; cursor:default; transition:border-color .15s, transform .15s; }
.pl-item:hover .pl-card { border-color:rgba(231,197,101,0.6); transform:translateX(2px); }
.pl-card.bloqueado { border-color:rgba(248,113,113,0.35); }
.pl-aviso { font-size:0.7rem; color:#fecaca; background:rgba(248,113,113,0.10); padding:4px 14px;
            border-bottom:1px solid rgba(248,113,113,0.18); }
.pl-cuerpo { flex:1; display:grid; grid-template-columns:28px 64px minmax(0, 1fr) auto; align-items:center; gap:12px; padding:11px 14px; }
.pl-izq { display:flex; flex-direction:column; align-items:center; gap:9px; }
.pl-pos { width:26px; height:26px; border-radius:50%; display:flex; align-items:center; justify-content:center;
          font-size:0.54rem; font-weight:800; color:#fff; }
.pl-foto { position:relative; width:62px; height:62px; }
.pl-foto img, .pl-foto .pl-ini { width:62px; height:62px; border-radius:50%; object-fit:cover; background:#11141b;
                                 border:2px solid rgba(255,255,255,0.12); }
.pl-foto .pl-ini { display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1.1rem; color:#0b0e14; }
.pl-pts { position:absolute; right:-6px; bottom:-4px; min-width:24px; height:22px; padding:0 5px; border-radius:999px;
          background:#0b0e14; border:2px solid #e5e9f0; color:#fff; font-size:0.7rem; font-weight:800;
          display:flex; align-items:center; justify-content:center; font-family:'Inter', sans-serif !important; }
.pl-est { position:absolute; left:-4px; bottom:-2px; }
.pl-nombre { color:#fff; font-weight:800; font-size:0.98rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.pl-valor { color:#f4f6fa; font-weight:700; font-size:0.84rem; margin-top:2px; font-variant-numeric:tabular-nums; }
.pl-valor span { font-size:0.72rem; margin-left:6px; }
.pl-racha { display:flex; gap:2px; margin-top:6px; }
.pl-racha span { min-width:19px; height:19px; padding:0 3px; border-radius:3px; color:#fff; font-size:0.66rem; font-weight:700;
                 display:flex; align-items:center; justify-content:center; font-family:'Inter', sans-serif !important; }
.pl-rol { font-size:0.6rem; font-weight:800; letter-spacing:0.1em; text-transform:uppercase; border-radius:999px;
          padding:3px 9px; white-space:nowrap; }
.pl-rol.titular { background:rgba(74,222,128,0.12); color:#86efac; border:1px solid rgba(74,222,128,0.3); }
.pl-rol.suplente { background:rgba(255,255,255,0.05); color:#8b93a7; border:1px solid rgba(255,255,255,0.1); }

/* El escenario: un campo de noche con dos focos apuntando a la carta */
.pl-lado { position:relative; align-self:stretch; min-height:470px; }
.pl-foco { position:absolute; top:0; right:0; bottom:0; width:360px; }
.pl-item .pl-foco { display:none; z-index:6; }
.pl-item:hover .pl-foco { display:block; }
.pl-wrap:has(.pl-item:hover) .pl-defecto { visibility:hidden; }
.pl-escena { position:sticky; top:80px; height:470px; border-radius:20px; overflow:hidden;
             display:flex; flex-direction:column; align-items:center; justify-content:flex-end;
             background:radial-gradient(ellipse 70% 32% at 50% 88%, rgba(134,239,172,0.28), transparent 70%),
                        repeating-linear-gradient(0deg, rgba(255,255,255,0.028) 0 22px, rgba(0,0,0,0) 22px 44px),
                        linear-gradient(180deg, #04060a 0%, #07110b 38%, #0d2616 70%, #134021 100%);
             border:1px solid rgba(255,255,255,0.08); box-shadow:0 18px 40px rgba(0,0,0,0.45); }
.pl-luz { position:absolute; top:-30px; width:210px; height:560px; pointer-events:none;
          background:linear-gradient(180deg, rgba(255,250,225,0.42), rgba(255,250,225,0.06) 70%, rgba(255,250,225,0));
          clip-path:polygon(46% 0, 54% 0, 100% 100%, 0 100%); filter:blur(5px); }
.pl-luz.izq { left:-40px; transform:rotate(-24deg); transform-origin:50% 0; }
.pl-luz.der { right:-40px; transform:rotate(24deg); transform-origin:50% 0; }
.pl-lampara { position:absolute; top:10px; width:16px; height:16px; border-radius:50%; background:#fffbe6;
              box-shadow:0 0 18px 8px rgba(255,248,210,0.7); }
.pl-lampara.izq { left:34px; } .pl-lampara.der { right:34px; }
.pl-linea { position:absolute; left:10%; right:10%; bottom:78px; height:2px; background:rgba(255,255,255,0.12); }
.pl-sombra { position:absolute; bottom:86px; width:190px; height:26px; border-radius:50%;
             background:radial-gradient(ellipse, rgba(0,0,0,0.65), transparent 70%); }
.pl-carta { position:relative; z-index:3; zoom:1.45; margin-bottom:62px; }
.pl-pie { position:relative; z-index:3; width:100%; display:flex; justify-content:center; gap:8px; flex-wrap:wrap;
          padding:0 14px 16px; }
.pl-pie span { background:rgba(0,0,0,0.45); border:1px solid rgba(255,255,255,0.12); border-radius:999px;
               padding:3px 10px; font-size:0.7rem; color:#e5e9f0; white-space:nowrap; backdrop-filter:blur(3px); }
.pl-pista { position:absolute; top:44px; left:0; right:0; text-align:center; color:rgba(255,255,255,0.45);
            font-size:0.66rem; letter-spacing:0.14em; text-transform:uppercase; z-index:3; }
@media (max-width: 1100px) {
  .pl-wrap { grid-template-columns:1fr; } .pl-lado, .pl-foco { display:none !important; }
}
@media (max-width: 760px) { .pl-lista { grid-template-columns:1fr; } }
</style>
"""


def _escena_html(fila, pie, pista=""):
    tipo = ABREVIA_POSICION.get(_pos_principal(fila.get('Posición')), 'DEL')
    return ("<div class='pl-escena'><div class='pl-luz izq'></div><div class='pl-luz der'></div>"
            "<div class='pl-lampara izq'></div><div class='pl-lampara der'></div>"
            + (f"<div class='pl-pista'>{pista}</div>" if pista else "")
            + "<div class='pl-linea'></div><div class='pl-sombra'></div>"
            f"<div class='pl-carta'>{generar_carta_html(fila, pos_type=tipo)}</div>"
            f"<div class='pl-pie'>{''.join(f'<span>{p}</span>' for p in pie)}</div></div>")


def _widget_plantilla(fila, titular, dias, pagado):
    nombre = str(fila['Jugador']).strip()
    equipo = str(fila.get('Equipo') or '').strip()
    pos = _pos_principal(fila.get('Posición'))
    color_pos = COLOR_POSICION.get(pos, '#6b7280')
    url = url_imagen(f"caras/{nombre}.png", f"caras/{nombre}.jpg")
    foto = (f"<img src='{url}' style='border-color:{color_pos};'>" if url else
            f"<div class='pl-ini' style='background:{color_pos};'>{''.join(p[0] for p in nombre.split()[:2]).upper()}</div>")
    valor = _a_float(fila.get('Valor Actual (€)'), 0.0) or 0.0
    var = _a_float(fila.get('Variación Diaria (€)'), 0.0) or 0.0
    color_var = '#4ade80' if var > 0 else '#f87171' if var < 0 else '#8b93a7'
    flecha = '▲' if var > 0 else '▼' if var < 0 else '='
    racha = _racha_html(fila).replace("class='mk-racha'", "class='pl-racha'")
    aviso = ""
    if dias:
        aviso = ("<div class='pl-aviso'>🔒 Venta desbloqueada "
                 + ("mañana" if dias == 1 else f"en {dias} días") + "</div>")
    pie = []
    if pagado:
        diferencia = valor - pagado
        pie.append(f"Fichado por {formato_euro(pagado)} · "
                   f"<b style='color:{'#86efac' if diferencia >= 0 else '#fca5a5'};'>"
                   f"{'+' if diferencia >= 0 else '−'}{formato_euro(abs(diferencia))}</b>")
    pie.append("Titular" if titular else "Suplente")
    if dias:
        pie.append(f"🔒 {dias} d")
    tarjeta = (f"<div class='pl-card{' bloqueado' if dias else ''}'>{aviso}<div class='pl-cuerpo'>"
               f"<div class='pl-izq'>{escudo_html(equipo, 24)}"
               f"<div class='pl-pos' style='background:{color_pos};'>{ABREVIA_POSICION.get(pos, pos[:3].upper())}</div></div>"
               f"<div class='pl-foto'>{foto}<div class='pl-pts'>{int(round(_a_float(fila.get('Puntos'), 0.0) or 0))}</div>"
               f"<div class='pl-est'>{_mini_icono_estado(estado_jugador(fila))}</div></div>"
               f"<div style='min-width:0;'><div class='pl-nombre' title='{nombre} · {equipo}'>{nombre}</div>"
               f"<div class='pl-valor'>{formato_euro(valor)}<span style='color:{color_var};'>{flecha} "
               f"{formato_euro(abs(var))}</span></div>{racha}</div>"
               f"<span class='pl-rol {'titular' if titular else 'suplente'}'>{'Titular' if titular else 'Suplente'}</span>"
               "</div></div>")
    return f"<div class='pl-item'>{tarjeta}<div class='pl-foco'>{_escena_html(fila, pie)}</div></div>"


def _resumen_plantilla(manager, plantilla, pagados):
    """Seis fichas: valor, puntos, plantilla, disponibilidad, saldo y lo que se
    ha revalorizado. Con el puesto en la liga donde tiene sentido compararse."""
    todas = db['plantillas'].dropna(subset=['Participante'])
    valor_de = todas.groupby('Participante')['Valor Actual (€)'].apply(
        lambda s: pd.to_numeric(s, errors='coerce').fillna(0).sum())
    # Los puntos de la LIGA (clasificación de mánagers), no la suma de los
    # puntos de sus jugadores, que cuenta también los que hicieron con otro.
    part = db['participantes'].dropna(subset=['Persona'])
    puntos_de = pd.Series(pd.to_numeric(part.get('Puntos'), errors='coerce').fillna(0).values,
                          index=part['Persona'].astype(str).str.strip())
    total = len(valor_de)
    puesto_valor = int((valor_de > valor_de.get(manager, 0)).sum()) + 1
    puesto_puntos = int((puntos_de > puntos_de.get(manager, 0)).sum()) + 1

    valores = pd.to_numeric(plantilla['Valor Actual (€)'], errors='coerce').fillna(0)
    variacion = pd.to_numeric(plantilla['Variación Diaria (€)'], errors='coerce').fillna(0).sum()
    color_var = '#4ade80' if variacion > 0 else '#f87171' if variacion < 0 else '#8b93a7'
    lineas = {k: 0 for k in ORDEN_LINEAS}
    for p in plantilla['Posición'].astype(str):
        lineas[_pos_principal(p)] = lineas.get(_pos_principal(p), 0) + 1
    estados = [estado_jugador(f) for _, f in plantilla.iterrows()]
    bajas = sum(1 for e in estados if e in NO_DISPONIBLE)
    dudas = sum(1 for e in estados if e == 'duda')
    bloqueados = sum(1 for j in plantilla['Jugador'] if dias_para_desbloquear(j, manager))
    saldo = saldo_de(manager)
    revalor = sum(v - pagados[j] for j, v in zip(plantilla['Jugador'].astype(str).str.strip(), valores)
                  if pagados.get(j))

    def kpi(rot, val, sub, color='#e7c565', titulo=''):
        return (f"<div class='pl-kpi' style='--c:{color};' title='{titulo}'><div class='pl-kpi-rot'>{rot}</div>"
                f"<div class='pl-kpi-val'>{val}</div><div class='pl-kpi-sub'>{sub}</div></div>")

    fichas = [
        kpi("Valor de plantilla", formato_euro_corto(valores.sum()),
            f"<b style='color:{color_var};'>{'▲' if variacion > 0 else '▼' if variacion < 0 else '='} "
            f"{formato_euro(abs(variacion))}</b> hoy · {puesto_valor}º de {total}", titulo=formato_euro(valores.sum())),
        kpi("Puntos en la liga", f"{int(puntos_de.get(manager, 0))}", f"{puesto_puntos}º de {len(puntos_de)} en la clasificación", '#0ea5e9'),
        kpi("Plantilla", f"{len(plantilla)}",
            "<div class='pl-chips'>" + "".join(f"<span class='pl-chip'>{ABREVIA_POSICION[k]}<b>{n}</b></span>"
                                              for k, n in lineas.items() if k in ABREVIA_POSICION) + "</div>", '#a78bfa'),
        kpi("Disponibles", f"{len(plantilla) - bajas}",
            "<div class='pl-chips'>"
            + (f"<span class='pl-chip'>🚑<b>{bajas}</b></span>" if bajas else "")
            + (f"<span class='pl-chip'>❗<b>{dudas}</b></span>" if dudas else "")
            + f"<span class='pl-chip'>🔒<b>{bloqueados}</b></span></div>",
            '#f87171' if bajas else '#4ade80'),
        kpi("Saldo", formato_euro_corto(saldo), "tiene que vender" if saldo < 0 else "disponible para fichar",
            '#f87171' if saldo < 0 else '#4ade80', titulo=formato_euro(saldo)),
        kpi("Revalorización", ('+' if revalor >= 0 else '−') + formato_euro_corto(abs(revalor)),
            "sobre lo que se pagó", '#4ade80' if revalor >= 0 else '#f87171'),
    ]
    return f"<div class='pl-resumen'>{''.join(fichas)}</div>"


@st.fragment
def ui_plantillas():
    base = db['plantillas'].dropna(subset=['Jugador']).copy()
    base = base[base['Jugador'].astype(str).str.lower() != 'nan']
    managers = sorted(base['Participante'].dropna().unique().tolist())
    if not managers:
        st.info("No hay plantillas.")
        return

    # Dos filtros y nada más: de quién es la plantilla y en qué orden.
    _, c_man, c_ord, _ = st.columns([1, 1.3, 1.1, 1])
    indice_mio = managers.index(MI_EQUIPO) if MI_EQUIPO in managers else 0
    manager = c_man.selectbox("Mánager", managers, index=indice_mio, key="plantillas_manager")
    if st.session_state.get('plantillas_orden') not in ORDENES_PLANTILLA:
        st.session_state.pop('plantillas_orden', None)
    orden = c_ord.selectbox("Ordenar por", list(ORDENES_PLANTILLA), key="plantillas_orden")

    plantilla = base[base['Participante'] == manager].copy()
    if plantilla.empty:
        st.info("Esta plantilla está vacía.")
        return

    try:
        _, _, titulares = calcular_mejor_once(plantilla.copy())
        en_once = {str(j['Jugador']).strip() for j in titulares}
    except Exception:
        en_once = set()
    compras = db['contabilidad'][(db['contabilidad']['Tipo de Operación'] == 'Compra')
                                 & (db['contabilidad']['Persona'] == manager)]
    pagados = {str(j).strip(): _a_float(i, None) for j, i in zip(compras['Jugador'], compras['Importe (€)'])}

    st.markdown(CSS_PLANTILLAS + f"<div class='pl-cab'><span>Resumen · {manager}</span></div>"
                + _resumen_plantilla(manager, plantilla, pagados), unsafe_allow_html=True)

    if ORDENES_PLANTILLA[orden] is None:
        plantilla = plantilla.assign(
            _l=[ORDEN_LINEAS.get(_pos_principal(p), 9) for p in plantilla['Posición']],
            _v=-pd.to_numeric(plantilla['Valor Actual (€)'], errors='coerce').fillna(0))
        plantilla = plantilla.sort_values(['_l', '_v'])
    else:
        columna, ascendente = ORDENES_PLANTILLA[orden]
        plantilla = plantilla.assign(_o=pd.to_numeric(plantilla[columna], errors='coerce')).sort_values(
            '_o', ascending=ascendente, na_position='last')

    widgets = []
    for _, fila in plantilla.iterrows():
        nombre = str(fila['Jugador']).strip()
        widgets.append(_widget_plantilla(fila, nombre in en_once, dias_para_desbloquear(nombre, manager),
                                         pagados.get(nombre)))
    # En el escenario, mientras no se pase el ratón por nadie, el que más brilla.
    estrella = max((f for _, f in plantilla.iterrows()), key=indice_brillo_jugador)
    defecto = _escena_html(estrella, [], pista="La estrella")
    st.markdown(CSS_PLANTILLAS + "<div class='pl-cab' style='margin-top:10px;'><span>Jugadores</span></div>"
                f"<div class='pl-wrap'><div class='pl-lista'>{''.join(widgets)}</div>"
                f"<div class='pl-lado'><div class='pl-foco pl-defecto'>{defecto}</div></div></div>",
                unsafe_allow_html=True)


# La pestaña Plantillas se pinta más abajo, junto a Mercado: usa la racha de
# partidos, que se define después.



# ==========================================
# 🌍 PESTAÑA: MERCADO GLOBAL (OPTIMIZADA)
# ==========================================
# El primero manda: es el orden por defecto del selector.
ORDENES_MERCADO = {
    "Puntos": ('Puntos', False),
    "Media de puntos": ('Media Puntos', False),
    "Media en casa": ('Media Puntos Casa', False),
    "Media fuera": ('Media Puntos Fuera', False),
    "Subida de valor": ('Variación Diaria (€)', False),
    "Valor de mercado": ('Valor Actual (€)', False),
}
POSICIONES_MERCADO = {"Todas": None, "Porteros": 'Portero', "Defensas": 'Defensa',
                      "Centrocampistas": 'Centrocampista', "Delanteros": 'Delantero'}
COLOR_POSICION = {'Portero': '#eab308', 'Defensa': '#2563eb', 'Centrocampista': '#16a34a', 'Delantero': '#dc2626'}
POR_PAGINA_MERCADO = 12

CSS_MERCADO = """
<style>
.mk-cab { display:flex; align-items:center; gap:16px; margin:6px 0 20px 0; }
.mk-cab::before { content:''; flex:1; height:1px; background:linear-gradient(90deg, transparent, rgba(231,197,101,0.4)); }
.mk-cab::after { content:''; flex:1; height:1px; background:linear-gradient(90deg, rgba(231,197,101,0.4), transparent); }
.mk-cab span { color:#e7c565; font-size:0.74rem; font-weight:700; letter-spacing:0.26em; text-transform:uppercase; }
.mk-resumen { display:flex; justify-content:center; gap:8px; flex-wrap:wrap; margin:4px 0 14px 0; }
.mk-resumen span { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:999px;
                   padding:4px 12px; font-size:0.76rem; color:#aab3c2; }
.mk-resumen b { color:#f4f6fa; font-family:'Inter', sans-serif !important; }

/* Tarjeta de jugador, como la lista de Biwenger */
.mk-grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; }
@media (max-width: 1150px) { .mk-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) { .mk-grid { grid-template-columns:1fr; } }
.mk-card { display:grid; grid-template-columns:30px 76px minmax(0, 1fr) auto; align-items:center; gap:12px;
           padding:13px 15px; border-radius:14px; background:linear-gradient(180deg, #232733, #1c2029);
           border:1px solid rgba(255,255,255,0.07); min-height:104px; }
.mk-card:hover { border-color:rgba(231,197,101,0.45); }
.mk-card.mk-tuyo { border-color:rgba(74,222,128,0.35); }
.mk-izq { display:flex; flex-direction:column; align-items:center; gap:12px; }
.mk-pos { width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center;
          font-size:0.56rem; font-weight:800; color:#fff; letter-spacing:0.02em; }
.mk-foto { position:relative; width:72px; height:72px; }
.mk-foto img, .mk-foto .mk-ini { width:72px; height:72px; border-radius:50%; object-fit:cover;
                                 background:#11141b; border:2px solid rgba(255,255,255,0.12); }
.mk-foto .mk-ini { display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1.3rem; color:#0b0e14; }
.mk-pts { position:absolute; right:-6px; bottom:-4px; min-width:26px; height:24px; padding:0 6px; border-radius:999px;
          background:#0b0e14; border:2px solid #e5e9f0; color:#fff; font-size:0.74rem; font-weight:800;
          display:flex; align-items:center; justify-content:center; font-family:'Inter', sans-serif !important; }
.mk-est { position:absolute; left:-4px; bottom:-2px; }
.mk-centro { min-width:0; }
.mk-nombre { color:#fff; font-weight:800; font-size:1.02rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.mk-valor { color:#f4f6fa; font-weight:700; font-size:0.9rem; margin-top:3px; font-variant-numeric:tabular-nums; }
.mk-var { font-size:0.74rem; font-weight:700; margin-top:1px; font-variant-numeric:tabular-nums; }
.mk-dueno { display:inline-block; margin-top:6px; font-size:0.62rem; font-weight:700; letter-spacing:0.06em;
            text-transform:uppercase; border-radius:999px; padding:2px 8px; white-space:nowrap; }
.mk-der { display:flex; flex-direction:column; align-items:flex-end; gap:9px; }
.mk-racha { display:flex; gap:2px; }
.mk-racha span { min-width:21px; height:21px; padding:0 3px; border-radius:3px; color:#fff; font-size:0.72rem;
                 font-weight:700; display:flex; align-items:center; justify-content:center;
                 font-variant-numeric:tabular-nums; font-family:'Inter', sans-serif !important; }
.mk-cf { display:flex; gap:10px; color:#e5e9f0; font-size:0.78rem; font-weight:600; font-variant-numeric:tabular-nums; }
.mk-rivales { font-size:0.64rem; color:#fca5a5; font-weight:700; }
.st-key-mercado_top_pos, .st-key-mercado_posicion { display:flex; justify-content:center; }
.st-key-mercado_top_pos > div, .st-key-mercado_posicion > div { width:auto !important; }
.st-key-mercado_top_pos [data-testid="stButtonGroup"], .st-key-mercado_top_pos div[data-baseweb="button-group"],
.st-key-mercado_top_pos [role="radiogroup"] { justify-content:center; margin:0 auto; }
div[class*="st-key-mk_top_"] button { border-radius:10px; border:1px solid rgba(231,197,101,0.4);
                                     background:rgba(231,197,101,0.08); color:#e7c565; }
div[class*="st-key-mk_top_"] button:hover { border-color:#e7c565; background:rgba(231,197,101,0.16); color:#f3d98a; }
div[class*="st-key-mk_top_"] button p { font-weight:700; color:inherit; }
.mk-pagina { text-align:center; color:#7d8699; font-size:0.78rem; margin:14px 0 4px 0; }

/* Top 10 de agentes libres: podio para los tres primeros y una fila para el resto */
.mk-podio { display:flex; justify-content:center; align-items:flex-end; gap:34px; margin:26px 0 8px 0; }
.mk-escalon { display:flex; flex-direction:column; align-items:center; margin-bottom:4px; }
.mk-escalon .mk-carta { margin-bottom:16px; }
.mk-peana { width:100%; border-radius:14px 14px 4px 4px; display:flex; flex-direction:column; align-items:center;
            justify-content:center; gap:3px; color:#0b0e14; box-shadow:0 12px 26px rgba(0,0,0,0.35); }
.mk-peana b { font-size:2rem; font-weight:900; line-height:1; font-family:'Inter', sans-serif !important; }
.mk-peana small { font-size:0.68rem; font-weight:700; opacity:0.85; font-family:'Inter', sans-serif !important; }
.mk-peana.oro { height:104px; background:linear-gradient(180deg, #f6dc8b, #c9a23a 60%, #8a6d1f); }
.mk-peana.plata { height:76px; background:linear-gradient(180deg, #eef2f7, #aab4c3 60%, #6b7686); }
.mk-peana.bronce { height:56px; background:linear-gradient(180deg, #f0b27a, #c7803f 60%, #7c4a22); }
.mk-resto { margin:30px 0 8px 0; border-top:1px solid rgba(255,255,255,0.06); }
.mk-puesto { display:flex; flex-direction:column; align-items:center; gap:12px; }
.mk-placa { display:flex; align-items:center; justify-content:center; }
.mk-placa b { width:24px; height:24px; border-radius:50%; background:#e7c565; color:#0b0e14; font-size:0.72rem;
              font-weight:900; display:flex; align-items:center; justify-content:center; font-family:'Inter', sans-serif !important; }
.mk-placa span { color:#aab3c2; font-size:0.7rem; white-space:nowrap; }
</style>
"""


def _racha_html(fila):
    """Sus últimos cinco partidos con los colores de Biwenger; '-' si no jugó.
    El más reciente a la izquierda."""
    partidos = forma_reciente(str(fila['Jugador']).strip(), str(fila.get('Equipo') or '').strip(), n=5)[::-1]
    cajas = []
    for p in partidos:
        titulo = f"J{p['jornada']} · {'vs' if p['es_casa'] else 'en'} {p['rival']}"
        if p['pts'] is None:
            cajas.append(f"<span title='{titulo}' style='background:#374151;'>?</span>")
        elif not p['jugo'] and p['pts'] == 0:
            cajas.append(f"<span title='{titulo} · no jugó' style='background:#4b5563;'>-</span>")
        else:
            cajas.append(f"<span title='{titulo}' style='background:{color_puntos_biwenger(p['pts'])};'>"
                         f"{int(round(p['pts']))}</span>")
    return f"<div class='mk-racha'>{''.join(cajas)}</div>" if cajas else ""


def _tarjeta_mercado(fila):
    nombre = str(fila['Jugador']).strip()
    equipo = str(fila.get('Equipo') or '').strip()
    pos = _pos_principal(fila.get('Posición'))
    color_pos = COLOR_POSICION.get(pos, '#6b7280')
    rotulo_pos = ABREVIA_POSICION.get(pos, pos[:3].upper() or '—')
    url = url_imagen(f"caras/{nombre}.png", f"caras/{nombre}.jpg")
    if url:
        foto = f"<img src='{url}' style='border-color:{color_pos};'>"
    else:
        iniciales = "".join(p[0] for p in nombre.split()[:2]).upper()
        foto = f"<div class='mk-ini' style='background:{color_pos};'>{iniciales}</div>"
    puntos = _a_float(fila.get('Puntos'), 0.0) or 0.0
    valor = _a_float(fila.get('Valor Actual (€)'), 0.0) or 0.0
    var = _a_float(fila.get('Variación Diaria (€)'), 0.0) or 0.0
    color_var = '#4ade80' if var > 0 else '#f87171' if var < 0 else '#8b93a7'
    flecha = '▲' if var > 0 else '▼' if var < 0 else '='
    estado = str(fila.get('Estado') or '').strip()
    if estado.lower() == 'libre':
        dueno = "<span class='mk-dueno' style='background:rgba(74,222,128,0.12); color:#86efac;'>Libre</span>"
    elif estado.lower() == 'tuyo':
        dueno = "<span class='mk-dueno' style='background:rgba(231,197,101,0.16); color:#e7c565;'>Tuyo</span>"
    else:
        dueno = (f"<span class='mk-dueno' style='background:rgba(255,255,255,0.07); color:#c3cbd9;'>{estado}</span>"
                 if estado and estado.lower() not in ('nan', 'none') else "")
    casa = _a_float(fila.get('Media Puntos Casa'), None)
    fuera = _a_float(fila.get('Media Puntos Fuera'), None)
    cf = (f"<div class='mk-cf'><span title='Media en casa'>🏠 {formato_puntos(casa) if casa else '-'}</span>"
          f"<span title='Media fuera'>✈️ {formato_puntos(fuera) if fuera else '-'}</span></div>")
    extra = ""
    return (f"<div class='mk-card{' mk-tuyo' if estado.lower() == 'tuyo' else ''}'>"
            f"<div class='mk-izq'>{escudo_html(equipo, 26)}"
            f"<div class='mk-pos' style='background:{color_pos};'>{rotulo_pos}</div></div>"
            f"<div class='mk-foto'>{foto}<div class='mk-pts'>{int(round(puntos))}</div>"
            f"<div class='mk-est'>{_mini_icono_estado(estado_jugador(fila))}</div></div>"
            f"<div class='mk-centro'><div class='mk-nombre' title='{nombre} · {equipo}'>{nombre}</div>"
            f"<div class='mk-valor'>{formato_euro(valor)}</div>"
            f"<div class='mk-var' style='color:{color_var};'>{flecha} {formato_euro(abs(var))}</div>{dueno}</div>"
            f"<div class='mk-der'>{_racha_html(fila)}{cf}{extra}</div></div>")


def _selector_pildoras(etiqueta, opciones, clave):
    """Botones de pastilla si esta versión de Streamlit los tiene; si no, radio."""
    if hasattr(st, 'segmented_control'):
        valor = st.segmented_control(etiqueta, opciones, default=opciones[0], key=clave,
                                     label_visibility="collapsed")
        return valor or opciones[0]
    return st.radio(etiqueta, opciones, horizontal=True, key=clave, label_visibility="collapsed")


def _cambiar_pagina_mercado(pagina):
    st.session_state['mercado_pagina'] = pagina


@st.fragment
def ui_mercado():
    base = db['mercado'].dropna(subset=['Jugador']).copy()
    if base.empty:
        st.info("No hay datos de mercado.")
        return
    huella = _huella_excel(resolver_excel_path())
    max_valor = float(np.ceil(pd.to_numeric(base['Valor Actual (€)'], errors='coerce').max() / 1e6)) or 1.0

    # 🔎 BARRA DE FILTROS, como la de Biwenger: una línea, sin cajas de más.
    st.markdown(CSS_MERCADO + "<div class='mk-cab'><span>Mercado de jugadores</span></div>", unsafe_allow_html=True)
    c_bus, c_ord, c_eq, c_dueno = st.columns([1.6, 1.1, 1.1, 1.1])
    busqueda = c_bus.text_input("Buscar jugador", "", placeholder="🔍  Buscar jugador", key="mercado_busqueda",
                                label_visibility="collapsed")
    if st.session_state.get('mercado_orden') not in ORDENES_MERCADO:
        st.session_state.pop('mercado_orden', None)      # opción de una versión anterior
    orden = c_ord.selectbox("Ordenar", list(ORDENES_MERCADO), key="mercado_orden", label_visibility="collapsed")
    equipos = sorted(e for e in base['Equipo'].dropna().unique() if e != 'Desconocido' and str(e).lower() != 'nan')
    equipo = c_eq.selectbox("Equipo", ["Todos los equipos"] + equipos, key="mercado_equipo",
                            label_visibility="collapsed")
    managers = sorted(str(m) for m in db['participantes']['Persona'].dropna().unique() if m != MI_EQUIPO)
    dueno = c_dueno.selectbox("Propietario", ["Cualquier propietario", "Libres", "Tuyos"] + managers,
                              key="mercado_dueno", label_visibility="collapsed")
    c_pos, c_precio, c_fis = st.columns([2.3, 1.5, 1.1], vertical_alignment="center")
    with c_pos:
        posicion = _selector_pildoras("Posición", list(POSICIONES_MERCADO), "mercado_posicion")
    precio = c_precio.slider("Precio (M€)", 0.0, max_valor, (0.0, max_valor), step=0.5, key="mercado_precio",
                             format="%.1f M€", label_visibility="collapsed")
    solo_sanos = c_fis.toggle("Ocultar lesionados", key="mercado_sanos")
    if not isinstance(precio, (tuple, list)) or len(precio) != 2:
        precio = (0.0, max_valor)

    datos = base
    if busqueda:
        datos = datos[datos['Jugador'].str.contains(busqueda, case=False, na=False, regex=False)]
    if equipo != "Todos los equipos":
        datos = datos[datos['Equipo'] == equipo]
    estado_txt = datos['Estado'].astype(str).str.strip()
    if dueno == "Libres":
        datos = datos[estado_txt.str.lower() == 'libre']
    elif dueno == "Tuyos":
        datos = datos[estado_txt.str.lower() == 'tuyo']
    elif dueno != "Cualquier propietario":
        datos = datos[estado_txt == dueno]
    if POSICIONES_MERCADO.get(posicion):
        datos = datos[datos['Posición'].astype(str).str.contains(POSICIONES_MERCADO[posicion], regex=False)]
    valores = pd.to_numeric(datos['Valor Actual (€)'], errors='coerce')
    datos = datos[(valores >= precio[0] * 1e6 - 1) & (valores <= precio[1] * 1e6 + 1)]
    if solo_sanos:
        datos = datos[[estado_jugador(f) not in NO_DISPONIBLE for _, f in datos.iterrows()]]

    if datos.empty:
        st.markdown("<div class='mk-pagina' style='margin:30px 0;'>Ningún jugador cumple esos filtros.</div>",
                    unsafe_allow_html=True)
    else:
        valor_num = pd.to_numeric(datos['Valor Actual (€)'], errors='coerce')
        var_num = pd.to_numeric(datos['Variación Diaria (€)'], errors='coerce')
        datos = datos.assign(**{'% Variación': var_num / valor_num.replace(0, np.nan) * 100})
        columna, ascendente = ORDENES_MERCADO[orden]
        clave = (datos[columna].astype(str) if columna == 'Jugador'
                 else pd.to_numeric(datos[columna], errors='coerce'))
        datos = (datos.assign(_orden=clave).sort_values('_orden', ascending=ascendente, na_position='last'))

        # Resumen de lo que hay en pantalla, en una línea.
        libres = int((datos['Estado'].astype(str).str.strip().str.lower() == 'libre').sum())
        st.markdown("<div class='mk-resumen'>"
                    f"<span><b>{len(datos)}</b> jugadores</span><span><b>{libres}</b> libres</span>"
                    f"<span><b>{formato_euro(valor_num.sum())}</b> en valor</span></div>",
                    unsafe_allow_html=True)

        # 📄 Por páginas, doce cada vez: pintar 525 tarjetas con su racha
        # tardaría y no se leería. Al cambiar un filtro se vuelve a la primera.
        firma = (busqueda, orden, equipo, dueno, posicion, precio, solo_sanos)
        if st.session_state.get('mercado_firma') != firma:
            st.session_state['mercado_firma'] = firma
            st.session_state['mercado_pagina'] = 1
        paginas = max(1, int(np.ceil(len(datos) / POR_PAGINA_MERCADO)))
        pagina = min(max(1, int(st.session_state.get('mercado_pagina', 1))), paginas)
        trozo = datos.iloc[(pagina - 1) * POR_PAGINA_MERCADO: pagina * POR_PAGINA_MERCADO]
        tarjetas = []
        for _, fila in trozo.iterrows():
            tarjetas.append(_tarjeta_mercado(fila))
        st.markdown(CSS_MERCADO + f"<div class='mk-grid'>{''.join(tarjetas)}</div>"
                    f"<div class='mk-pagina'>{(pagina - 1) * POR_PAGINA_MERCADO + 1} – "
                    f"{min(pagina * POR_PAGINA_MERCADO, len(datos))} de {len(datos)}</div>",
                    unsafe_allow_html=True)
        if paginas > 1:
            ventana = [p for p in range(max(1, pagina - 2), min(paginas, pagina + 2) + 1)]
            botones = [("«", 1), ("‹", max(1, pagina - 1))] + [(str(p), p) for p in ventana] + \
                      [("›", min(paginas, pagina + 1)), ("»", paginas)]
            columnas = st.columns([4] + [0.55] * len(botones) + [4])
            for col, (texto, destino) in zip(columnas[1:-1], botones):
                col.button(texto, key=f"mk_pag_{texto}_{destino}", use_container_width=True,
                           type="primary" if (texto == str(pagina)) else "secondary",
                           disabled=(destino == pagina and not texto.isdigit()),
                           on_click=_cambiar_pagina_mercado, args=(destino,))

    # 🏆 LOS DIEZ MEJORES AGENTES LIBRES, en podio.
    st.markdown(CSS_MERCADO + "<div class='mk-cab' style='margin-top:46px;'><span>Top 10 agentes libres</span></div>",
                unsafe_allow_html=True)
    pos_top = _selector_pildoras("Posición del top", list(POSICIONES_MERCADO), "mercado_top_pos")
    libres = base[base['Estado'].astype(str).str.strip().str.lower() == 'libre']
    libres = libres[[estado_jugador(f) not in NO_DISPONIBLE for _, f in libres.iterrows()]]
    if POSICIONES_MERCADO.get(pos_top):
        libres = libres[libres['Posición'].astype(str).str.contains(POSICIONES_MERCADO[pos_top], regex=False)]
    if libres.empty:
        st.markdown("<div class='mk-pagina'>No hay agentes libres en esa posición.</div>", unsafe_allow_html=True)
        return
    # El mismo criterio que el brillo de las cartas: calidad por probabilidad
    # de jugar, que es lo que mejor anticipa lo que dará (ver indice_brillo_jugador).
    libres = libres.assign(_brillo=[indice_brillo_jugador(f) for _, f in libres.iterrows()])
    top = libres.sort_values(['_brillo', 'Valor Actual (€)'], ascending=[False, False]).head(10)
    filas = [f for _, f in top.iterrows()]

    def _carta(fila, zoom):
        tipo = ABREVIA_POSICION.get(_pos_principal(fila.get('Posición')), 'DEL')
        return f"<div class='mk-carta' style='zoom:{zoom};'>{generar_carta_html(fila, pos_type=tipo)}</div>"

    # Cada puesto lleva su botón «Subasta», que abre Scouting con el informe
    # de ese jugador.
    repetidos = set(base.loc[base['Estado'].astype(str).str.strip().str.lower() == 'libre', 'Jugador']
                    .astype(str).loc[lambda x: x.duplicated()])

    def _boton_subasta(col, fila, clave):
        if col.button("Subasta", key=clave, use_container_width=True):
            nombre = str(fila['Jugador'])
            st.session_state['scouting_jugador'] = (f"{nombre} ({fila['Equipo']})" if nombre in repetidos
                                                    else nombre)
            _ir_a_seccion("Scouting")
            st.rerun()

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    orden_podio = [(1, 'plata', 1.0), (0, 'oro', 1.14), (2, 'bronce', 1.0)]
    orden_podio = [x for x in orden_podio if x[0] < len(filas)]
    try:
        cols = st.columns([1.2] + [1] * len(orden_podio) + [1.2], gap="large", vertical_alignment="bottom")[1:-1]
    except TypeError:
        cols = st.columns([1.2] + [1] * len(orden_podio) + [1.2])[1:-1]
    for col, (indice, clase, zoom) in zip(cols, orden_podio):
        col.markdown(CSS_MERCADO + f"<div class='mk-escalon'>{_carta(filas[indice], zoom)}"
                     f"<div class='mk-peana {clase}'><b>{indice + 1}</b></div></div>", unsafe_allow_html=True)
        _boton_subasta(col, filas[indice], f"mk_top_{indice}")
    if len(filas) > 3:
        st.markdown("<div class='mk-resto'></div>", unsafe_allow_html=True)
        cols = st.columns(len(filas) - 3)
        for col, (i, fila) in zip(cols, enumerate(filas[3:], start=4)):
            col.markdown(f"<div class='mk-puesto'>{_carta(fila, 0.9)}<div class='mk-placa'><b>{i}</b></div></div>",
                         unsafe_allow_html=True)
            _boton_subasta(col, fila, f"mk_top_{i - 1}")


# La pestaña Mercado se pinta más abajo, junto a Comparar: usa la racha de
# partidos (forma_reciente) y los colores de Biwenger, que se definen después.


# ==========================================
# 🎯 PESTAÑA: SHADOW SCOUTING (OPTIMIZADA)
# ==========================================
@st.fragment
def historial_pujas_jugador(nombre, equipo=None):
    """Todo lo que la Contabilidad sabe de las subastas pasadas de un jugador.

    Cuando un jugador vuelve a estar libre, saber que hace tres semanas Fulano
    llegó a ofrecer 4,8 M€ por él vale más que cualquier predicción. Ahora mismo
    hay 61 jugadores libres que ya pasaron por subasta antes."""
    contabilidad = db.get('contabilidad')
    if contabilidad is None or contabilidad.empty:
        return []
    filas = contabilidad[contabilidad['Jugador'] == nombre]
    if equipo is not None and 'Equipo' in filas.columns:
        exactas = filas[filas['Equipo'] == equipo]
        if not exactas.empty:
            filas = exactas

    historial = []
    for _, fila in filas.iterrows():
        perdedores = []
        for i in range(1, 10):
            postor, oferta = fila.get(f'Manager {i}'), fila.get(f'Subasta perdida {i}')
            if pd.notna(postor) and str(postor).strip():
                perdedores.append((str(postor).strip(), oferta))
        historial.append({
            'tipo': fila.get('Tipo de Operación'),
            'persona': fila.get('Persona'),
            'importe': fila.get('Importe (€)'),
            'valor_mercado': fila.get('Valor Mercado (€)'),
            'sobrepuja': fila.get('Sobrepuja (€)'),
            'perdedores': perdedores,
        })
    return historial


@st.cache_data(show_spinner=False)
def duelos_en_subastas(huella=None, manager=None):
    """Cuántas veces te has cruzado con cada rival en una subasta y cómo acabó.

    Rivales contaba cómo es la plantilla del otro, pero no cómo te ha ido contra
    él en el mercado, que es lo que decide si merece la pena pelear una puja.
    Y el dato lleva ahí desde el principio: cada compra guarda al ganador y a
    todos los que se quedaron sin el jugador.
    """
    manager = manager or MI_EQUIPO
    contabilidad = db.get('contabilidad')
    if contabilidad is None or contabilidad.empty:
        return {}
    compras = contabilidad[contabilidad['Tipo de Operación'] == 'Compra']
    duelos = {}
    for _, fila in compras.iterrows():
        ganador = str(fila['Persona']).strip() if pd.notna(fila['Persona']) else ''
        perdedores = [str(fila.get(f'Manager {i}')).strip() for i in range(1, 10)
                      if pd.notna(fila.get(f'Manager {i}'))]
        participantes = [p for p in ([ganador] + perdedores) if p]
        if manager not in participantes or len(participantes) < 2:
            continue
        for otro in participantes:
            if otro == manager:
                continue
            marcador = duelos.setdefault(otro, {'veces': 0, 'gane': 0, 'perdi': 0})
            marcador['veces'] += 1
            if ganador == manager:
                marcador['gane'] += 1
            elif ganador == otro:
                marcador['perdi'] += 1
    return duelos


# --- 🧩 FICHAJES QUE TE MEJORAN: SOLO SI HAY NECESIDAD DE VERDAD ---
# Revisado el 25/09/2026. Antes se comparaba cada libre con el titular más flojo
# de su posición y salían 39 "mejoras", casi todas de relleno: bastaba con ser
# un poco mejor que el peor de una línea, sin mirar si te lo podías pagar ni qué
# tendrías que vender para ello.
#
# Ahora cada libre se prueba DENTRO de tu plantilla, con la misma máquina que
# decide las ventas (_once_optimo): cuánto sube tu mejor once con él, pagando lo
# que de verdad costará ganar la subasta (la puja justa del predictor) y
# vendiendo, si hace falta, lo que menos daño hace antes de la próxima jornada.
# Lo que cuenta es la mejora NETA: con el fichaje y ya sin los vendidos. Si
# para pagarlo tienes que desmontar el once, no sale.
#
# SI VAS EN NEGATIVO, la comparación es contra el once que te quedaría después
# de cubrir esa deuda, porque esas ventas las vas a hacer igual, fiches o no.
# Comparando con el once de hoy, a cada fichaje se le cargaba entera una deuda
# que no es suya y no salía ninguno.
#
# Y solo se recomienda lo que mueve la aguja: al menos un 2% de la calidad de tu
# once (con tu plantilla de hoy, algo más de un punto por jornada). Por debajo
# es fichar por fichar. Los que se quedan cerca se enseñan aparte, con el
# motivo, para que se vea qué se ha mirado y por qué no pasa.
MEJORA_MINIMA_FICHAJE = 0.02
MEJORA_MINIMA_PARA_PROBAR = 0.005
MAX_FICHAJES_A_PROBAR = 20
LINEAS_ONCE = ('Portero', 'Defensa', 'Centrocampista', 'Delantero')


def _calidad_de_plantilla(filas):
    calidad = np.array([indice_brillo_jugador(f) for f in filas])
    E = _elegibilidad(filas)
    total, once = _once_optimo(calidad, E, np.ones(len(filas), dtype=bool))
    return calidad, E, total, once


@st.cache_data(show_spinner=False)
def nivel_por_lineas(huella=None, manager=None):
    """Cómo está cada línea de tu once frente a las de los otros nueve.

    {línea: (tu puesto de 1 a N, N)}, con la calidad media de los titulares de
    esa línea en el mejor once de cada uno."""
    manager = manager or MI_EQUIPO
    medias = {}
    for persona in db['plantillas']['Participante'].dropna().unique():
        filas = [f.to_dict() for _, f in db['plantillas'][db['plantillas']['Participante'] == persona].iterrows()]
        if not filas:
            continue
        calidad, _, _, once = _calidad_de_plantilla(filas)
        for k, linea in enumerate(LINEAS_ONCE):
            suyos = [calidad[i] for i, puesto in once.items() if puesto == k]
            medias.setdefault(linea, {})[str(persona).strip()] = float(np.mean(suyos)) if suyos else 0.0
    nivel = {}
    for linea, por_persona in medias.items():
        if manager in por_persona:
            orden = sorted(por_persona.values(), reverse=True)
            nivel[linea] = (orden.index(por_persona[manager]) + 1, len(orden))
    return nivel


def saldo_de(persona):
    fila = db['participantes'][db['participantes']['Persona'] == persona]
    return (_a_float(fila.iloc[0].get('Balance Total (€)'), 0.0) or 0.0) if not fila.empty else 0.0


@st.cache_data(show_spinner=False)
def candidatos_que_mejoran(huella=None, manager=None):
    """Libres que suben de verdad la calidad de tu plantilla, ya pagados.

    Devuelve todos los que se han probado, con su 'Veredicto':
      'ficha'        pasa el listón: se recomienda
      'poco'         te lo puedes pagar, pero mejora menos del listón
      'no_compensa'  lo que hay que vender para pagarlo quita más de lo que da
      'no_llega'     no te llega ni vendiendo
    Primero los recomendados por mejora; después el resto, del más cercano al
    más lejano. 'Mejora' va en tanto por uno de la calidad de tu once, 'Puja'
    es la justa, 'Ventas' lo que habría que vender (incluida la deuda, si la
    hay) y 'Sale' quién deja el once."""
    manager = manager or MI_EQUIPO
    plantilla = db['plantillas'][db['plantillas']['Participante'] == manager]
    if plantilla.empty:
        return pd.DataFrame()
    completa = [f.to_dict() for _, f in plantilla.iterrows()]
    calidad, E, _, _ = _calidad_de_plantilla(completa)
    vendible = [vendible_antes_de_jornada(f['Jugador'], manager) for f in completa]
    saldo = saldo_de(manager)

    # 0) Lo que hay que vender SÍ O SÍ para llegar a la jornada en positivo.
    activos_base = np.ones(len(completa), dtype=bool)
    if saldo < 0:
        opciones = _mejores_ventas(completa, vendible, -saldo, max_ventas=6, max_opciones=1)
        if opciones:
            vendidos = {id(v) for v in opciones[0]['jugadores']}
            activos_base = np.array([id(f) not in vendidos for f in completa])
    base, once_base = _once_optimo(calidad, E, activos_base)
    if base <= 0:
        return pd.DataFrame()

    mercado = db['mercado'].dropna(subset=['Jugador'])
    libres = mercado[mercado['Estado'].astype(str).str.strip().str.lower() == 'libre']
    libres = libres[libres['Lesion'].astype(str).str.lower() != 'si']

    # 1) Criba rápida: cuánto subiría tu once si te lo regalaran.
    brutas = []
    activos_con = np.append(activos_base, True)
    for _, jugador in libres.iterrows():
        fila = jugador.to_dict()
        c = np.append(calidad, indice_brillo_jugador(fila))
        total, once_gratis = _once_optimo(c, _elegibilidad(completa + [fila]), activos_con)
        if (total - base) / base >= MEJORA_MINIMA_PARA_PROBAR:
            brutas.append((total - base, fila, once_gratis))
    brutas.sort(key=lambda x: -x[0])
    nuevo = len(completa)

    def _por_quien(once):
        # Por quién entra: el titular de su misma línea que se queda fuera. Si
        # no hay ninguno (entra en otra línea y se recoloca el resto), todos
        # los que dejan el once.
        salen = [i for i in once_base if i not in once]
        misma_linea = [i for i in salen if nuevo in once and once_base[i] == once[nuevo]]
        return [completa[i]['Jugador'] for i in (misma_linea or salen)]

    # 2) Pagándolo: la puja justa y, si no llega el saldo, las ventas que menos
    #    daño hacen con él ya dentro (las de la deuda van incluidas).
    filas = []
    for bruta, fila, once_gratis in brutas[:MAX_FICHAJES_A_PROBAR]:
        valor = _a_float(fila.get('Valor Actual (€)'), 0.0) or 0.0
        try:
            amenazas, _ = predecir_amenazas(fila['Jugador'], fila.get('Equipo'))
            puja = dict((n, p) for n, p, _ in pujas_para_ganar(amenazas, valor)).get('La justa', valor)
        except Exception:
            puja = valor
        con_el = completa + [fila]
        registro = {
            'Jugador': str(fila['Jugador']), 'Equipo': str(fila.get('Equipo')),
            'Posición': _pos_principal(fila.get('Posición')),
            'Valor Actual (€)': valor, 'Puja': puja, 'Bruta': bruta / base,
            # Si no se lo puede pagar, por quién entraría si llegara el dinero.
            'Mejora': np.nan, 'Sale': _por_quien(once_gratis), 'Ventas': [], 'Te quedan (€)': np.nan,
            'Veredicto': 'no_llega', 'Entra': nuevo in once_gratis,
        }
        activos, ventas = np.ones(len(con_el), dtype=bool), []
        if puja > saldo:
            opciones = _mejores_ventas(con_el, vendible + [False], puja - saldo, max_ventas=6, max_opciones=1)
            if not opciones:
                filas.append(registro)
                continue
            ventas = opciones[0]['jugadores']
            vendidos = {id(v) for v in ventas}
            activos = np.array([id(f) not in vendidos for f in con_el])
        c = np.append(calidad, indice_brillo_jugador(fila))
        total, once = _once_optimo(c, _elegibilidad(con_el), activos)
        mejora = (total - base) / base
        ingreso = sum(_a_float(v.get('Valor Actual (€)'), 0.0) or 0.0 for v in ventas)
        registro.update({
            'Mejora': mejora,
            'Sale': _por_quien(once),
            'Ventas': [v['Jugador'] for v in ventas],
            'Te quedan (€)': saldo + ingreso - puja,
            # Redondeado a la décima de punto porcentual, que es como se enseña:
            # si no, un +1,98% salía como "solo +2,0%" con el listón en el 2%.
            'Veredicto': ('ficha' if round(mejora, 3) >= MEJORA_MINIMA_FICHAJE else
                          'poco' if mejora > 0 else 'no_compensa'),
            'Entra': nuevo in once,
        })
        filas.append(registro)
    if not filas:
        return pd.DataFrame()
    marco = pd.DataFrame(filas)
    orden = {'ficha': 0, 'poco': 1, 'no_compensa': 2, 'no_llega': 3}
    marco['_o'] = marco['Veredicto'].map(orden)
    marco['_m'] = marco['Mejora'].fillna(-1.0)
    return (marco.sort_values(['_o', '_m', 'Bruta'], ascending=[True, False, False])
            .drop(columns=['_o', '_m']).reset_index(drop=True))


CSS_SCOUTING = """
<style>
/* La app fuerza Inter en div, span y p; aquí también en b y small, que antes
   salían en serif. Cifras siempre tabulares para que no bailen. */
.sc-cab span, .sc-num, [class^="sc-"] b, [class*=" sc-"] b, [class^="sc-"] small { font-family:'Inter', sans-serif !important; }
.sc-cab { display:flex; align-items:center; gap:16px; margin:6px 0 22px 0; }
.sc-cab::before { content:''; flex:1; height:1px; background:linear-gradient(90deg, transparent, rgba(231,197,101,0.4)); }
.sc-cab::after { content:''; flex:1; height:1px; background:linear-gradient(90deg, rgba(231,197,101,0.4), transparent); }
.sc-cab span { color:#e7c565; font-size:0.74rem; font-weight:700; letter-spacing:0.26em; text-transform:uppercase; }
.sc-titulo { display:flex; align-items:center; justify-content:center; gap:14px; color:#f2f4f8; font-size:0.92rem; font-weight:800; letter-spacing:0.16em; text-transform:uppercase; text-align:center; margin:36px 0 18px 0; }
.sc-titulo::before { content:''; width:34px; height:2px; border-radius:2px; background:linear-gradient(90deg, transparent, #e7c565); }
.sc-titulo::after { content:''; width:34px; height:2px; border-radius:2px; background:linear-gradient(90deg, #e7c565, transparent); }
.sc-num { font-weight:800; color:#f4f6fa; font-variant-numeric:tabular-nums; letter-spacing:-0.01em;
          white-space:nowrap; line-height:1; }
.sc-sub { color:#8b93a7; font-size:0.74rem; }
.sc-etq { color:#7d8699; font-size:0.6rem; font-weight:700; letter-spacing:0.16em; text-transform:uppercase; }
.sc-nota { text-align:center; color:#7d8699; font-size:0.74rem; margin-top:10px; }
.sc-centro { text-align:center; }

/* ---------- Cabecera del jugador ---------- */
.sc-hero { display:grid; grid-template-columns:230px 1.15fr 1fr; max-width:1100px; margin:0 auto;
           border:1px solid rgba(255,255,255,0.08); border-radius:20px; overflow:hidden;
           background:radial-gradient(120% 160% at 0% 0%, rgba(231,197,101,0.08), transparent 50%),
                      linear-gradient(180deg, #161b25, #10141c);
           box-shadow:0 14px 34px rgba(0,0,0,0.35); }
.sc-hero > div { padding:24px 22px; display:flex; flex-direction:column; align-items:center;
                 justify-content:center; text-align:center; }
.sc-hero > div + div { border-left:1px solid rgba(255,255,255,0.06); }
.sc-valor { display:flex; align-items:center; justify-content:center; gap:10px; margin-top:8px; }
.sc-delta { font-size:0.68rem; font-weight:700; padding:3px 8px; border-radius:999px; white-space:nowrap; }
.sc-spark { width:100%; max-width:300px; height:auto; margin-top:14px; display:block; }
.sc-ejes { display:flex; justify-content:space-between; width:100%; max-width:300px; color:#5f6778;
           font-size:0.62rem; margin-top:3px; }
.sc-minis { display:flex; gap:10px; justify-content:center; margin-top:14px; flex-wrap:wrap; }
.sc-mini { background:rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.07); border-radius:12px;
           padding:9px 14px; min-width:118px; }
.sc-mini .sc-num { font-size:1.02rem; margin-top:6px; }
.sc-proximos { display:flex; gap:8px; justify-content:center; flex-wrap:wrap; }
.sc-aviso { max-width:760px; margin:20px auto 0 auto; text-align:center; padding:14px 18px; border-radius:14px;
            background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); color:#e5e9f0; }

/* ---------- Tu puja ---------- */
.sc-pujas { display:flex; gap:16px; justify-content:center; flex-wrap:wrap; }
.sc-puja { width:272px; display:flex; flex-direction:column; align-items:center; gap:8px; padding:18px 16px 16px;
           border-radius:18px; background:linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.012));
           border:1px solid rgba(255,255,255,0.08); }
.sc-puja.sc-top { background:linear-gradient(180deg, rgba(231,197,101,0.17), rgba(231,197,101,0.03));
                  border-color:rgba(231,197,101,0.55);
                  box-shadow:0 0 0 1px rgba(231,197,101,0.12), 0 14px 34px rgba(231,197,101,0.08); }
.sc-puja-nombre { color:#aab3c2; font-size:0.66rem; font-weight:700; letter-spacing:0.2em; text-transform:uppercase; }
.sc-top .sc-puja-nombre { color:#e7c565; }
.sc-sobre { color:#7d8699; font-size:0.72rem; margin-top:-2px; }
.sc-anillo { position:relative; width:78px; height:78px; margin:4px 0; }
.sc-anillo svg { transform:rotate(-90deg); }
.sc-anillo div { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center;
                 justify-content:center; font-weight:800; font-size:1.08rem; color:#f4f6fa; line-height:1; }
.sc-anillo small { font-size:0.52rem; color:#8b93a7; font-weight:700; letter-spacing:0.14em; margin-top:4px; }
.sc-pago { width:100%; border-top:1px solid rgba(255,255,255,0.07); padding-top:11px; margin-top:4px;
           display:flex; flex-direction:column; align-items:center; gap:7px; }
.sc-vende { display:flex; gap:4px; flex-wrap:wrap; justify-content:center; }
.sc-vende span { background:rgba(251,191,36,0.09); color:#fcd34d; border:1px solid rgba(251,191,36,0.22);
                 border-radius:999px; padding:2px 8px; font-size:0.68rem; white-space:nowrap; }
.sc-ok, .sc-ko { border-radius:999px; padding:4px 12px; font-size:0.72rem; font-weight:600; white-space:nowrap; }
.sc-ok { background:rgba(74,222,128,0.10); color:#86efac; border:1px solid rgba(74,222,128,0.28); }
.sc-ko { background:rgba(248,113,113,0.10); color:#fca5a5; border:1px solid rgba(248,113,113,0.28); }

/* ---------- Rivales ---------- */
.sc-rivales { max-width:1040px; margin:0 auto; display:flex; flex-direction:column; gap:8px; }
.sc-rival { display:grid; grid-template-columns:42px minmax(260px, 1.9fr) minmax(150px, 1fr) 150px;
            align-items:center; gap:20px; padding:12px 20px 12px 16px; border-radius:14px;
            background:linear-gradient(90deg, rgba(255,255,255,0.045), rgba(255,255,255,0.015));
            border:1px solid rgba(255,255,255,0.07); border-left:3px solid var(--c); }
.sc-inicial { width:40px; height:40px; border-radius:50%; display:flex; align-items:center; justify-content:center;
              font-weight:800; font-size:0.76rem; color:#0b0e14; background:var(--c); }
.sc-rival-nombre { color:#f4f6fa; font-weight:700; font-size:0.95rem; }
.sc-chips { display:flex; gap:5px; flex-wrap:wrap; margin-top:7px; }
.sc-chip { background:rgba(255,255,255,0.055); border:1px solid rgba(255,255,255,0.05); border-radius:999px;
           padding:2px 9px; font-size:0.68rem; color:#c3cbd9; white-space:nowrap; }
.sc-barra { height:6px; border-radius:4px; background:rgba(255,255,255,0.07); overflow:hidden; margin-top:7px; }
.sc-barra span { display:block; height:100%; border-radius:4px; }

/* ---------- Historial ---------- */
.sc-hist { max-width:1040px; margin:0 auto; display:flex; flex-direction:column; gap:6px; }
.sc-hist-fila { display:flex; align-items:center; justify-content:center; gap:10px; flex-wrap:wrap;
                padding:10px 14px; border-radius:12px; background:rgba(255,255,255,0.025);
                border:1px solid rgba(255,255,255,0.05); color:#e5e9f0; font-size:0.86rem; }

/* ---------- Tu once frente a la liga ---------- */
.sc-lineas { display:flex; gap:12px; justify-content:center; flex-wrap:wrap; }
.sc-linea { width:136px; padding:13px 10px 14px; border-radius:16px; text-align:center;
            background:linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.012));
            border:1px solid rgba(255,255,255,0.08); }
.sc-linea-num { font-size:1.75rem; font-weight:800; line-height:1.05; margin-top:7px; font-variant-numeric:tabular-nums; }
.sc-linea-num small { font-size:0.72rem; color:#7d8699; font-weight:600; margin-left:3px; }
.sc-rango { display:flex; gap:3px; justify-content:center; margin-top:10px; }
.sc-rango span { width:7px; height:7px; border-radius:50%; background:rgba(255,255,255,0.12); }
.sc-deuda { display:flex; justify-content:center; margin-top:16px; }
.sc-deuda span { background:rgba(248,113,113,0.07); border:1px solid rgba(248,113,113,0.25); color:#fecaca;
                 border-radius:999px; padding:7px 16px; font-size:0.78rem; }
.sc-deuda b { color:#f87171; }
.sc-veredicto-general { display:flex; justify-content:center; margin-top:14px; }
.sc-veredicto-general span { background:rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.09);
                             color:#e5e9f0; border-radius:999px; padding:8px 18px; font-size:0.86rem; }

/* ---------- El cambio: entra uno, sale otro ---------- */
.sc-cambio { border-radius:20px; padding:14px; margin-bottom:2px;
             background:linear-gradient(180deg, #171c26, #10141c);
             border:1px solid rgba(255,255,255,0.08); box-shadow:0 10px 26px rgba(0,0,0,0.32); }
.sc-cambio.sc-v-ficha { border-color:rgba(74,222,128,0.30); }
.sc-cambio-cab { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:12px; min-height:26px; }
.sc-pill { font-size:0.72rem; font-weight:700; padding:4px 11px; border-radius:999px; white-space:nowrap; }
.sc-pill.verde { background:rgba(74,222,128,0.12); color:#86efac; border:1px solid rgba(74,222,128,0.32); }
.sc-pill.ambar { background:rgba(251,191,36,0.10); color:#fcd34d; border:1px solid rgba(251,191,36,0.30); }
.sc-pill.rojo { background:rgba(248,113,113,0.10); color:#fca5a5; border:1px solid rgba(248,113,113,0.30); }
.sc-pill.oro { background:rgba(231,197,101,0.12); color:#e7c565; border:1px solid rgba(231,197,101,0.38); }
.sc-campo { position:relative; display:flex; align-items:center; justify-content:space-evenly;
            padding:24px 8px 24px; border-radius:16px;
            background:repeating-linear-gradient(90deg, rgba(255,255,255,0.022) 0 30px, rgba(0,0,0,0) 30px 60px),
                       radial-gradient(ellipse at 50% 50%, rgba(34,197,94,0.20), rgba(34,197,94,0.04) 72%),
                       #0c1510;
            border:1px solid rgba(74,222,128,0.16); container-type:inline-size; }
/* En pantallas más estrechas las cartas se encogen para no pisarse. */
@container (max-width: 400px) { .sc-carta-cambio, .sc-carta-vacia { zoom:0.84; } .sc-campo-icono { transform:scale(0.85); } }
@container (max-width: 330px) { .sc-carta-cambio, .sc-carta-vacia { zoom:0.72; } }
.sc-campo::before { content:''; position:absolute; top:0; bottom:0; left:50%; width:1px; background:rgba(255,255,255,0.09); }
.sc-campo::after { content:''; position:absolute; top:50%; left:50%; width:78px; height:78px; margin:-39px 0 0 -39px;
                   border-radius:50%; border:1px solid rgba(255,255,255,0.09); }
.sc-campo-icono { position:relative; z-index:2; width:40px; height:40px; border-radius:50%; background:#0a100c;
                  border:1px solid rgba(255,255,255,0.14); display:flex; align-items:center; justify-content:center; }
.sc-carta-cambio { position:relative; display:inline-block; z-index:3; }
.sc-sub-badge { position:absolute; bottom:-13px; right:-13px; width:30px; height:30px; border-radius:50%;
                display:flex; align-items:center; justify-content:center; z-index:40;
                border:2px solid #0b0e14; box-shadow:0 3px 8px rgba(0,0,0,0.6); }
.sc-sub-badge.entra { background:#22c55e; }
.sc-sub-badge.sale { background:#ef4444; }
.sc-sub-badge.con-mas { width:auto; padding:0 9px 0 6px; gap:3px; border-radius:999px; right:-18px; }
.sc-sub-badge b { color:#fff; font-size:0.72rem; font-weight:800; }
.sc-carta-vacia { width:125px; height:150px; border-radius:8px; border:2px dashed rgba(255,255,255,0.2);
                  background:rgba(0,0,0,0.25); display:flex; flex-direction:column; align-items:center;
                  justify-content:center; gap:6px; color:#8b93a7; font-size:0.74rem; font-weight:700;
                  text-align:center; padding:0 10px; }
.sc-carta-vacia.hueco { border-color:rgba(248,113,113,0.55); background:rgba(80,10,10,0.35); color:#fca5a5; }
.sc-carta-vacia span { font-size:1.35rem; line-height:1; }
.sc-cambio-datos { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:12px; }
.sc-dato { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:12px;
           padding:9px 10px; text-align:center; }
.sc-dato .sc-num { font-size:1.08rem; margin-top:6px; }
.sc-cambio-pago { margin-top:10px; display:flex; flex-direction:column; align-items:center; gap:6px; min-height:80px;
                  justify-content:flex-start; }
.sc-avatar { width:36px; height:36px; border-radius:50%; object-fit:cover; background:rgba(255,255,255,0.08);
             display:flex; align-items:center; justify-content:center; font-size:0.72rem; color:#c3cbd9;
             font-weight:700; border:1px solid rgba(255,255,255,0.12); }
/* El botón de cada cambio, a juego (Streamlit pone la clave del botón como clase). */
div[class*="st-key-sc_ver_"] button { border-radius:12px; border:1px solid rgba(231,197,101,0.35);
                                      background:rgba(231,197,101,0.06); color:#e7c565; }
div[class*="st-key-sc_ver_"] button:hover { border-color:#e7c565; background:rgba(231,197,101,0.14); color:#f3d98a; }
div[class*="st-key-sc_ver_"] button p { font-weight:600; color:inherit; }

@media (max-width: 900px) {
  .sc-hero { grid-template-columns:1fr; }
  .sc-hero > div + div { border-left:none; border-top:1px solid rgba(255,255,255,0.06); }
  .sc-rival { grid-template-columns:1fr; text-align:center; }
}
</style>
"""

ABREVIA_POSICION = {'Portero': 'POR', 'Defensa': 'DEF', 'Centrocampista': 'MED', 'Delantero': 'DEL'}
COLORES_RIVAL = ['#e7c565', '#60a5fa', '#f472b6', '#34d399', '#f59e0b', '#a78bfa', '#f87171', '#22d3ee', '#fb923c']

# Iconos del cambio, como en las retransmisiones: flecha verde el que entra,
# roja el que sale, y las dos flechas cruzadas en medio del campo.
ICONO_ENTRA = ("<svg viewBox='0 0 24 24' width='15' height='15'><path d='M12 19V6M6 11l6-6 6 6' fill='none' "
               "stroke='#fff' stroke-width='3.2' stroke-linecap='round' stroke-linejoin='round'/></svg>")
ICONO_SALE = ("<svg viewBox='0 0 24 24' width='15' height='15'><path d='M12 5v13M6 13l6 6 6-6' fill='none' "
              "stroke='#fff' stroke-width='3.2' stroke-linecap='round' stroke-linejoin='round'/></svg>")
ICONO_CAMBIO = ("<svg viewBox='0 0 24 24' width='22' height='22'>"
                "<path d='M4 8h15M15 4l4 4-4 4' fill='none' stroke='#4ade80' stroke-width='2.4' "
                "stroke-linecap='round' stroke-linejoin='round'/>"
                "<path d='M20 16H5M9 12l-4 4 4 4' fill='none' stroke='#f87171' stroke-width='2.4' "
                "stroke-linecap='round' stroke-linejoin='round'/></svg>")


def _elegir_en_scouting(etiqueta):
    st.session_state['scouting_jugador'] = etiqueta


def _avatar(nombre, tamano=36):
    """La cara del jugador en pequeño (la misma foto de su carta) o sus iniciales."""
    url = url_imagen(f"caras/{nombre}.png", f"caras/{nombre}.jpg")
    if url:
        return f"<img class='sc-avatar' style='width:{tamano}px; height:{tamano}px;' src='{url}'>"
    iniciales = "".join(p[0] for p in str(nombre).split()[:2]).upper()
    return f"<div class='sc-avatar' style='width:{tamano}px; height:{tamano}px;'>{iniciales}</div>"


def _carta_escalada(fila, escala=1.0):
    tipo = ABREVIA_POSICION.get(_pos_principal(fila.get('Posición')), 'DEL')
    carta = generar_carta_html(fila, pos_type=tipo)
    if escala == 1.0:
        return f"<div style='display:flex; justify-content:center;'>{carta}</div>"
    # La carta mide 149 px de alto; se reserva eso escalado y un poco de aire.
    return (f"<div style='display:flex; justify-content:center; height:{int(160 * escala)}px;'>"
            f"<div style='transform:scale({escala}); transform-origin:top center;'>{carta}</div></div>")


def _historial_valor(nombre, equipo, dias=21):
    """(fechas, valores) del jugador en las últimas semanas, desde el Histórico."""
    try:
        hist = cargar_historico_completo(_huella_excel(resolver_excel_path()))
    except Exception:
        return [], []
    if hist is None or hist.empty:
        return [], []
    filas = hist[hist['Jugador'].astype(str).str.strip() == str(nombre).strip()]
    if equipo is not None and (filas['Equipo'].astype(str).str.strip() == str(equipo).strip()).any():
        filas = filas[filas['Equipo'].astype(str).str.strip() == str(equipo).strip()]
    filas = filas.dropna(subset=['Fecha']).drop_duplicates('Fecha').sort_values('Fecha').tail(dias)
    valores = pd.to_numeric(filas['Valor Actual (€)'], errors='coerce')
    filas, valores = filas[valores.notna()], valores[valores.notna()]
    return list(filas['Fecha']), [float(v) for v in valores]


def _grafica_valor(valores, ancho=300, alto=66):
    """La evolución del valor como área con degradado y el punto de hoy."""
    minimo, maximo = min(valores), max(valores)
    rango = (maximo - minimo) or 1.0
    xs = [i * ancho / (len(valores) - 1) for i in range(len(valores))]
    ys = [alto - 6 - (v - minimo) / rango * (alto - 14) for v in valores]
    linea = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    color = '#4ade80' if valores[-1] >= valores[0] else '#f87171'
    gid = "sc" + uuid.uuid4().hex[:8]
    return (f"<svg class='sc-spark' viewBox='-4 0 {ancho + 8} {alto}'>"
            f"<defs><linearGradient id='{gid}' x1='0' y1='0' x2='0' y2='1'>"
            f"<stop offset='0%' stop-color='{color}' stop-opacity='0.32'/>"
            f"<stop offset='100%' stop-color='{color}' stop-opacity='0'/></linearGradient></defs>"
            f"<polygon points='0,{alto} {linea} {ancho},{alto}' fill='url(#{gid})'/>"
            f"<polyline points='{linea}' fill='none' stroke='{color}' stroke-width='2.2' "
            f"stroke-linejoin='round' stroke-linecap='round'/>"
            f"<circle cx='{xs[-1]:.1f}' cy='{ys[-1]:.1f}' r='6' fill='{color}' fill-opacity='0.2'/>"
            f"<circle cx='{xs[-1]:.1f}' cy='{ys[-1]:.1f}' r='3.2' fill='{color}'/></svg>")


def _bloque_valor(info_jugador):
    """Lo que vale, cómo se mueve y lo que valdrá el día del partido.

    La tendencia es la MEDIANA de sus últimas subidas diarias, no la de ayer
    sola: un salto suelto proyectado varios días es el error más común."""
    nombre, equipo = str(info_jugador.get('Jugador')), info_jugador.get('Equipo')
    valor = _a_float(info_jugador.get('Valor Actual (€)'), 0.0) or 0.0
    fechas, valores = _historial_valor(nombre, equipo)
    grafica, delta, minis = "", "", []
    if len(valores) >= 3:
        cambios = np.diff(valores)
        tendencia = float(np.median(cambios[-5:]))
        grafica = (_grafica_valor(valores) +
                   f"<div class='sc-ejes'><span>{pd.Timestamp(fechas[0]):%d/%m}</span><span>hoy</span></div>")
        if len(valores) >= 8 and valores[-8]:
            pct = valores[-1] / valores[-8] - 1
            color_d = '#4ade80' if pct > 0 else '#f87171' if pct < 0 else '#aab3c2'
            delta = (f"<span class='sc-delta' style='color:{color_d}; background:{color_d}1a; "
                     f"border:1px solid {color_d}40;'>{'▲' if pct > 0 else '▼' if pct < 0 else '='} "
                     f"{abs(pct) * 100:.1f}% en 7 días</span>").replace('.', ',')
        color_t = '#4ade80' if tendencia > 0 else '#f87171' if tendencia < 0 else '#c3cbd9'
        minis.append(f"<div class='sc-mini'><div class='sc-etq'>Al día</div>"
                     f"<div class='sc-num' style='color:{color_t};'>{formato_tendencia(tendencia)}</div></div>")
        tramo = tramo_de_calendario(equipo, 1)
        partido = tramo['partidos'][0] if tramo and tramo.get('partidos') else None
        if partido and partido.get('fecha') is not None:
            dias = max(0, (pd.Timestamp(partido['fecha']).normalize() - pd.Timestamp.now().normalize()).days)
            if dias > 0:
                # La inercia de una subida se agota con los días.
                proyectado = valor + tendencia * dias * (0.75 if dias > 4 else 1.0)
                minis.append(f"<div class='sc-mini'><div class='sc-etq'>El día del partido</div>"
                             f"<div class='sc-num'>{formato_euro(proyectado)}</div></div>")
    return (f"<div><div class='sc-etq'>Valor de mercado</div>"
            f"<div class='sc-valor'><span class='sc-num' style='font-size:2.1rem;' title='{formato_euro(valor)}'>"
            f"{formato_euro(valor)}</span>{delta}</div>"
            f"{grafica}<div class='sc-minis'>{''.join(minis)}</div></div>")


def _bloque_proximos(equipo):
    tramo = tramo_de_calendario(equipo, 3)
    if not tramo:
        return "<div><div class='sc-etq'>Próximos partidos</div><div class='sc-sub' style='margin-top:10px;'>Sin fechas</div></div>"
    css_escudos, con_imagen = _css_escudos_tramo({p['rival'] for p in tramo['partidos']})
    fichas = "".join(_ficha_partido_tramo(p, con_imagen) for p in tramo['partidos'])
    return (CSS_TRAMO + css_escudos + "<div><div class='sc-etq' style='margin-bottom:14px;'>Próximos partidos</div>"
            f"<div class='sc-proximos'>{fichas}</div></div>")


def plan_de_ventas_para_fichar(importe, objetivo):
    """Qué vender de TU plantilla para pagar `importe` por `objetivo`.

    Lo que cuenta es lo que pierde tu once DESPUÉS del fichaje, con todas las
    ventas a la vez: vender a un suplente no te quita puntos, y vender al
    titular al que el fichaje va a sustituir tampoco (ver _mejores_ventas).

    [] si te llega con el saldo, None si no hay manera sin quedarte sin equipo."""
    deuda = importe - saldo_de(MI_EQUIPO)
    if deuda <= 0:
        return []
    plantilla = db['plantillas'][db['plantillas']['Participante'] == MI_EQUIPO]
    completa, vendible = [], []
    for _, mio in plantilla.iterrows():
        completa.append(mio.to_dict())
        vendible.append(vendible_antes_de_jornada(mio['Jugador'], MI_EQUIPO))
    completa.append(dict(objetivo))          # el fichaje cuenta para el once, no se vende
    vendible.append(False)
    opciones = _mejores_ventas(completa, vendible, deuda, max_ventas=6, max_opciones=1)
    if not opciones:
        return None
    return [{'Jugador': f['Jugador'], 'Valor': _a_float(f.get('Valor Actual (€)'), 0.0) or 0.0}
            for f in opciones[0]['jugadores']]


def _chips_ventas(nombres):
    return ("<div class='sc-etq'>Vendes</div><div class='sc-vende'>"
            + "".join(f"<span>{n}</span>" for n in nombres) + "</div>")


def _como_pagar(puja, info_jugador):
    if saldo_de(MI_EQUIPO) >= puja:
        return "<span class='sc-ok'>Con tu saldo</span>"
    ventas = plan_de_ventas_para_fichar(puja, info_jugador)
    if ventas:
        return _chips_ventas([j['Jugador'] for j in ventas])
    return "<span class='sc-ko'>No te llega</span>"


def _anillo(prob, color):
    radio, grosor = 32, 6
    vuelta = 2 * np.pi * radio
    lleno = max(0.0, min(1.0, prob)) * vuelta
    return (f"<div class='sc-anillo'><svg width='78' height='78' viewBox='0 0 78 78'>"
            f"<circle cx='39' cy='39' r='{radio}' fill='none' stroke='rgba(255,255,255,0.08)' stroke-width='{grosor}'/>"
            f"<circle cx='39' cy='39' r='{radio}' fill='none' stroke='{color}' stroke-width='{grosor}' "
            f"stroke-linecap='round' stroke-dasharray='{lleno:.1f} {vuelta:.1f}'/></svg>"
            f"<div>{prob * 100:.0f}%<small>GANAS</small></div></div>")


def _tu_puja_html(amenazas, info_jugador):
    """Las pujas con las que ganas una de cada cuatro, una de cada dos y tres de
    cada cuatro, con la probabilidad REAL de cada una (ver predecir_amenazas).
    Si dos coinciden (por ejemplo, porque basta con pasar el techo del único
    rival), se enseña una sola."""
    valor = _a_float(info_jugador.get('Valor Actual (€)'), 0.0) or 0.0
    opciones = []
    for nombre, puja, prob in pujas_para_ganar(amenazas, valor):
        if opciones and abs(opciones[-1][1] - puja) < 1000:
            opciones[-1] = (nombre, puja, prob)
        else:
            opciones.append((nombre, puja, prob))
    if len(opciones) == 1:
        opciones = [("Al valor de mercado" if opciones[0][1] <= valor + 1000 else opciones[0][0],
                     opciones[0][1], opciones[0][2])]
    destacada = next((n for n, _, _ in opciones if n == "La justa"), opciones[-1][0])
    tarjetas = []
    for nombre, puja, prob in opciones:
        top = nombre == destacada
        color = '#e7c565' if top else '#4ade80' if prob >= 0.7 else '#60a5fa' if prob >= 0.45 else '#94a3b8'
        sobre = (puja / valor - 1) * 100 if valor else 0.0
        sobre_txt = f"{sobre:+.0f}% sobre su valor" if abs(sobre) >= 0.5 else "a su valor de mercado"
        tarjetas.append(
            f"<div class='sc-puja{' sc-top' if top else ''}'><div class='sc-puja-nombre'>{nombre}</div>"
            f"<div class='sc-num' style='font-size:{1.62 if top else 1.4}rem; margin-top:4px;'>{formato_euro(puja)}</div>"
            f"<div class='sc-sobre'>{sobre_txt}</div>"
            f"{_anillo(prob, color)}<div class='sc-pago'>{_como_pagar(puja, info_jugador)}</div></div>")
    return "<div class='sc-titulo'>Pujas recomendadas</div><div class='sc-pujas'>" + "".join(tarjetas) + "</div>"


def _rivales_html(amenazas):
    """Quién puede pujar, cuánto suele ofrecer y cómo se comporta en el mercado."""
    p_nadie = amenazas.attrs.get('p_nadie')
    nota = (f"<div class='sc-nota'>{p_nadie * 100:.0f}% de que no puje ningún rival</div>"
            if p_nadie is not None else "")
    if amenazas.empty:
        mas = amenazas.attrs.get('mas_probable')
        extra = (f" · el más probable, <b>{mas[0]}</b> ({mas[1]:.0f}%)" if mas and mas[1] >= 5 else "")
        return ("<div class='sc-titulo'>Competencia prevista</div>"
                f"<div class='sc-aviso' style='margin-top:0;'>Ningún rival destaca{extra}</div>{nota}")
    filas = []
    for i, (_, f) in enumerate(amenazas.iterrows()):
        prob = float(f['Prob'])
        color_p = '#f87171' if prob >= 50 else '#fbbf24' if prob >= 35 else '#60a5fa'
        color_m = COLORES_RIVAL[i % len(COLORES_RIVAL)]
        inicial = "".join(p[0] for p in str(f['Manager']).split()[:2]).upper()
        chips = [f"puja en el {f['Tasa']:.0f}% de subastas"]
        if f['Pujas']:
            chips.append(f"ganó {int(f['Ganadas'])} de {int(f['Pujas'])}")
        if pd.notna(f.get('Sobre_mediana')):
            chips.append(f"suele pasarse {f['Sobre_mediana']:+.0f}%")
        chips.append(f"llega hasta {formato_euro(f['Techo'])}")
        rango = (f"{formato_euro_corto(f['Puja_baja'])} – {formato_euro_corto(f['Puja_alta'])}"
                 if f['Puja_alta'] - f['Puja_baja'] >= 50_000 else "")
        filas.append(
            f"<div class='sc-rival' style='--c:{color_m};'><div class='sc-inicial'>{inicial}</div>"
            f"<div><div class='sc-rival-nombre'>{f['Manager']}</div>"
            f"<div class='sc-chips'>{''.join(f'<span class=sc-chip>{c}</span>' for c in chips)}</div></div>"
            f"<div class='sc-centro'><div class='sc-etq'>Pujará</div>"
            f"<div class='sc-num' style='font-size:1.15rem; color:{color_p}; margin-top:6px;'>{prob:.0f}%</div>"
            f"<div class='sc-barra'><span style='width:{min(100, prob):.0f}%; background:{color_p};'></span></div></div>"
            f"<div class='sc-centro'><div class='sc-etq'>Su puja</div>"
            f"<div class='sc-num' style='font-size:1.25rem; margin-top:6px;' title='{formato_euro(f['Puja'])}'>"
            f"{formato_euro(f['Puja'])}</div>"
            f"<div class='sc-sub' style='margin-top:5px;'>{rango}</div></div></div>")
    return "<div class='sc-titulo'>Competencia prevista</div><div class='sc-rivales'>" + "".join(filas) + "</div>" + nota


def _historial_subastas_html(historial):
    filas = []
    for suceso in historial:
        if suceso['tipo'] == 'Compra':
            texto = f"<b>{suceso['persona']}</b> lo fichó por <b>{formato_euro(suceso['importe'])}</b>"
            valor = _a_float(suceso.get('valor_mercado'), None)
            importe = _a_float(suceso.get('importe'), None)
            if valor and importe:
                texto += f" <span class='sc-sub'>({(importe / valor - 1) * 100:+.0f}%)</span>"
        else:
            texto = f"<b>{suceso['persona']}</b> lo vendió por <b>{formato_euro(suceso['importe'])}</b>"
        chips = "".join(
            f"<span class='sc-chip'>{postor}" + (f" · {formato_euro(oferta)}" if pd.notna(oferta) else "") + "</span>"
            for postor, oferta in suceso['perdedores'])
        filas.append(f"<div class='sc-hist-fila'><span>{texto}</span>{chips}</div>")
    return "<div class='sc-titulo'>Historial de subastas</div><div class='sc-hist'>" + "".join(filas) + "</div>"


def _niveles_html(nivel):
    """Tu once línea a línea frente a los otros nueve: dónde está la necesidad."""
    tarjetas = []
    for linea in LINEAS_ONCE:
        if linea not in nivel:
            continue
        puesto, total = nivel[linea]
        color = '#f87171' if puesto > total * 0.7 else '#fbbf24' if puesto > total * 0.4 else '#4ade80'
        puntos = "".join(
            f"<span style='background:{color}; box-shadow:0 0 0 3px {color}33;'></span>" if k + 1 == puesto
            else "<span></span>" for k in range(total))
        tarjetas.append(f"<div class='sc-linea' style='border-color:{color}40;'>"
                        f"<div class='sc-etq'>{ABREVIA_POSICION[linea]}</div>"
                        f"<div class='sc-linea-num' style='color:{color};'>{puesto}º<small>de {total}</small></div>"
                        f"<div class='sc-rango'>{puntos}</div></div>")
    return ("<div class='sc-titulo' style='margin-top:4px;'>Tu once frente a la liga</div>"
            f"<div class='sc-lineas'>{''.join(tarjetas)}</div>")


def _carta_con_cambio(fila, entra, tambien=()):
    """La carta de siempre con la flecha del cambio en la esquina. Si con él
    salen más titulares, la flecha lleva cuántos (y sus nombres al pasar por
    encima)."""
    tipo = ABREVIA_POSICION.get(_pos_principal(fila.get('Posición')), 'DEL')
    nombre = str(fila.get('Jugador'))
    titulo = ('Entra ' + nombre) if entra else ('Sale ' + _enumerar([nombre] + list(tambien)))
    mas = f"<b>+{len(tambien)}</b>" if tambien else ""
    return (f"<div class='sc-carta-cambio'>{generar_carta_html(fila, pos_type=tipo)}"
            f"<div class='sc-sub-badge {'entra' if entra else 'sale'}{' con-mas' if tambien else ''}' "
            f"title='{titulo}'>{ICONO_ENTRA if entra else ICONO_SALE}{mas}</div></div>")


def _pill_veredicto(fila):
    veredicto, mejora = fila['Veredicto'], fila['Mejora']
    if veredicto == 'ficha':
        return f"<span class='sc-pill verde'>▲ +{mejora * 100:.1f}% a tu once</span>".replace('.', ',')
    if veredicto == 'poco':
        return f"<span class='sc-pill ambar'>+{mejora * 100:.1f}% · mejora poco</span>".replace('.', ',')
    if veredicto == 'no_compensa':
        return f"<span class='sc-pill rojo'>{mejora * 100:+.1f}% · no compensa</span>".replace('.', ',')
    return "<span class='sc-pill rojo'>No te llega</span>"


def _tarjeta_cambio(fila, completa_entra, mios, mejor_euro=False):
    """Un fichaje como un cambio en el campo: su carta entra (flecha verde) y la
    tuya sale (flecha roja). Debajo, la puja justa, lo que te queda y qué
    vendes para pagarlo."""
    sale = fila['Sale'] if isinstance(fila['Sale'], list) else []
    if sale and sale[0] in mios:
        carta_sale = _carta_con_cambio(mios[sale[0]], False, sale[1:])
    else:
        entra_once = fila.get('Entra')
        entra_once = bool(entra_once) if isinstance(entra_once, (bool, np.bool_)) else False
        carta_sale = ("<div class='sc-carta-vacia hueco'><span>🚷</span>Hueco en tu once</div>" if entra_once
                      else "<div class='sc-carta-vacia'><span>🪑</span>Iría al banquillo</div>")
    cabecera = _pill_veredicto(fila) + ("<span class='sc-pill oro'>Más mejora por euro</span>" if mejor_euro else "")
    if fila['Veredicto'] == 'no_llega':
        datos = (f"<div class='sc-dato'><div class='sc-etq'>Puja justa</div>"
                 f"<div class='sc-num'>{formato_euro(fila['Puja'])}</div></div>"
                 f"<div class='sc-dato'><div class='sc-etq'>Te quedan</div><div class='sc-num' style='color:#fca5a5;'>—</div></div>")
        pago = "<span class='sc-ko'>No te llega ni vendiendo</span>"
    else:
        quedan = fila['Te quedan (€)']
        datos = (f"<div class='sc-dato'><div class='sc-etq'>Puja justa</div>"
                 f"<div class='sc-num' title='{formato_euro(fila['Puja'])}'>{formato_euro(fila['Puja'])}</div></div>"
                 f"<div class='sc-dato'><div class='sc-etq'>Te quedan</div>"
                 f"<div class='sc-num' style='color:{'#86efac' if quedan >= 0 else '#fca5a5'};'>{formato_euro(quedan)}</div></div>")
        pago = _chips_ventas(fila['Ventas']) if fila['Ventas'] else "<span class='sc-ok'>Con tu saldo</span>"
    return (f"<div class='sc-cambio sc-v-{fila['Veredicto'].replace('_', '-')}'>"
            f"<div class='sc-cambio-cab'>{cabecera}</div>"
            f"<div class='sc-campo'>{_carta_con_cambio(completa_entra, True)}"
            f"<div class='sc-campo-icono'>{ICONO_CAMBIO}</div>{carta_sale}</div>"
            f"<div class='sc-cambio-datos'>{datos}</div>"
            f"<div class='sc-cambio-pago'>{pago}</div></div>")


def _columnas_centradas(n):
    """Tres por fila; si la última tiene menos, centradas."""
    reparto = {3: ([1, 1, 1], slice(0, 3)), 2: ([0.5, 1, 1, 0.5], slice(1, 3)), 1: ([1, 1, 1], slice(1, 2))}
    anchos, trozo = reparto[n]
    try:
        return st.columns(anchos, gap="medium")[trozo]
    except TypeError:
        return st.columns(anchos)[trozo]


def _pintar_cambios(filas, mapa_etiquetas):
    recomendadas = filas[filas['Veredicto'] == 'ficha']
    mejor_euro = None
    if len(recomendadas) > 1:
        # El que más mejora por cada euro que pones, si no es ya el primero.
        rinde = recomendadas['Mejora'] / recomendadas['Puja'].clip(lower=1)
        mejor_euro = rinde.idxmax() if rinde.idxmax() != recomendadas.index[0] else None
    mercado = db['mercado'].dropna(subset=['Jugador'])
    ficha_de = {(str(j).strip(), str(e).strip()): i for i, j, e in zip(mercado.index, mercado['Jugador'], mercado['Equipo'])}
    plantilla = db['plantillas'][db['plantillas']['Participante'] == MI_EQUIPO]
    mios = {str(r['Jugador']).strip(): r for r in plantilla.to_dict('records')}
    lista = list(filas.iterrows())
    for inicio in range(0, len(lista), 3):
        trozo = lista[inicio:inicio + 3]
        for (indice, fila), col in zip(trozo, _columnas_centradas(len(trozo))):
            clave = (str(fila['Jugador']).strip(), str(fila['Equipo']).strip())
            completa = mercado.loc[ficha_de[clave]] if clave in ficha_de else fila
            col.markdown(_tarjeta_cambio(fila, completa, mios, indice == mejor_euro), unsafe_allow_html=True)
            etiqueta = mapa_etiquetas.get((str(fila['Jugador']), fila['Equipo']))
            if etiqueta:
                col.button("Ver subasta", key=f"sc_ver_{fila['Jugador']}_{fila['Equipo']}",
                           use_container_width=True, on_click=_elegir_en_scouting, args=(etiqueta,))


def _pintar_fichajes_que_mejoran(candidatos, mapa_etiquetas, maximo=6, cerca=6):
    """Los fichajes recomendados y, si no hay ninguno, los que más se acercan
    con el motivo por el que no pasan: así se ve qué se ha mirado."""
    recomendados = candidatos[candidatos['Veredicto'] == 'ficha']
    if not recomendados.empty:
        st.markdown(CSS_SCOUTING + "<div class='sc-titulo'>Fichajes recomendados</div>", unsafe_allow_html=True)
        _pintar_cambios(recomendados.head(maximo), mapa_etiquetas)
        if len(recomendados) > maximo:
            st.markdown(f"<div class='sc-nota'>y {len(recomendados) - maximo} más que también te mejoran</div>",
                        unsafe_allow_html=True)
        return
    st.markdown(CSS_SCOUTING + "<div class='sc-veredicto-general'><span>Ningún libre sube tu once lo suficiente: "
                "no hace falta fichar</span></div><div class='sc-titulo'>Alternativas más cercanas</div>",
                unsafe_allow_html=True)
    _pintar_cambios(candidatos.head(cerca), mapa_etiquetas)


def ui_scouting():
    catalogo = db['mercado'].dropna(subset=['Jugador']).copy()
    catalogo['_libre'] = catalogo['Estado'].astype(str).str.strip().str.lower() == 'libre'
    solo_libres = st.session_state.get("scouting_solo_libres", True)
    disponibles = catalogo[catalogo['_libre']] if solo_libres else catalogo

    repetidos = set(disponibles['Jugador'][disponibles['Jugador'].duplicated()])
    opciones, mapa_opciones, mapa_etiquetas = [""], {}, {}
    for _, fila in disponibles.sort_values('Jugador').iterrows():
        nombre = str(fila['Jugador'])
        etiqueta = f"{nombre} ({fila['Equipo']})" if nombre in repetidos else nombre
        opciones.append(etiqueta)
        mapa_opciones[etiqueta] = (nombre, fila['Equipo'])
        mapa_etiquetas[(nombre, fila['Equipo'])] = etiqueta

    huella = _huella_excel(resolver_excel_path())
    candidatos = candidatos_que_mejoran(huella, MI_EQUIPO)
    if st.session_state.get('scouting_jugador') not in opciones:
        mejor = ""
        if not candidatos.empty:
            primero = candidatos.iloc[0]
            mejor = mapa_etiquetas.get((str(primero['Jugador']), primero['Equipo']), "")
        if not mejor and not disponibles.empty:
            fila_mejor = max(disponibles.to_dict('records'), key=puntos_esperados_jugador)
            mejor = mapa_etiquetas.get((str(fila_mejor['Jugador']), fila_mejor['Equipo']), "")
        st.session_state['scouting_jugador'] = mejor if mejor in opciones else ""

    # 🏷️ EL INFORME DE LA SUBASTA
    st.markdown(CSS_SCOUTING + "<div class='sc-cab'><span>Informe de subasta</span></div>", unsafe_allow_html=True)
    try:
        _, c_sel, c_lib, _ = st.columns([1, 2.2, 1, 0.6], vertical_alignment="center")
    except TypeError:
        _, c_sel, c_lib, _ = st.columns([1, 2.2, 1, 0.6])
    etiqueta_sel = c_sel.selectbox("Jugador", opciones, key="scouting_jugador", label_visibility="collapsed")
    c_lib.checkbox("Solo agentes libres", value=True, key="scouting_solo_libres")
    seleccion, equipo_sel = mapa_opciones.get(etiqueta_sel, (None, None)) if etiqueta_sel else (None, None)

    if seleccion:
        amenazas, info_jugador = predecir_amenazas(seleccion, equipo_sel)
        if info_jugador is None or (hasattr(info_jugador, 'empty') and info_jugador.empty):
            st.warning("No se han encontrado datos de ese jugador en el mercado.")
        else:
            estado = str(info_jugador.get('Estado', '')).strip()
            tiene_dueno = bool(estado) and estado.lower() not in ('libre', 'nan', 'none', '')
            partes = [CSS_SCOUTING,
                      "<div class='sc-hero'>"
                      f"<div>{_carta_escalada(info_jugador, 1.15)}</div>"
                      f"{_bloque_valor(info_jugador)}{_bloque_proximos(info_jugador.get('Equipo'))}</div>"]
            if tiene_dueno:
                partes.append("<div class='sc-aviso'>" + ("Ya es <b>tuyo</b>." if estado.lower() == 'tuyo' else
                              f"Es de <b>{estado}</b>: no sale a subasta.") + "</div>")
            else:
                partes.append(_tu_puja_html(amenazas, info_jugador))
                partes.append(_rivales_html(amenazas))
            historial = historial_pujas_jugador(seleccion, equipo_sel)
            if historial:
                partes.append(_historial_subastas_html(historial))
            st.markdown("".join(partes), unsafe_allow_html=True)

    # 🔎 LOS FICHAJES QUE TE MEJORAN DE VERDAD
    cabecera = [CSS_SCOUTING, "<div class='sc-cab' style='margin-top:44px;'><span>Refuerzos para tu plantilla</span></div>",
                _niveles_html(nivel_por_lineas(huella, MI_EQUIPO))]
    saldo = saldo_de(MI_EQUIPO)
    if saldo < 0:
        cabecera.append(f"<div class='sc-deuda'><span>Antes de la jornada tienes que recuperar "
                        f"<b>{formato_euro(-saldo)}</b> · ya va incluido en cada fichaje</span></div>")
    st.markdown("".join(cabecera), unsafe_allow_html=True)
    if candidatos.empty:
        st.markdown(CSS_SCOUTING + "<div class='sc-veredicto-general'><span>Ningún libre sube tu once: "
                    "no hace falta fichar</span></div>", unsafe_allow_html=True)
    else:
        _pintar_fichajes_que_mejoran(candidatos, mapa_etiquetas)


if _pagina == "Scouting":
    ui_scouting()


# ==========================================
# 🕵️ PESTAÑA: INTELIGENCIA RIVAL (OPTIMIZADA)
# ==========================================


@st.fragment
@st.cache_data(show_spinner=False)
def _pujas_por_manager(huella=None):
    """Cuántas pujas (ganadas y perdidas) tiene registradas cada mánager."""
    eventos = construir_eventos_puja(db['contabilidad'])
    if eventos is None or len(eventos) == 0:
        return {}
    return eventos['Persona'].value_counts().to_dict()


@st.cache_data(show_spinner=False)
def metricas_liga(huella=None):
    """Todas las medidas de debilidad, calculadas para los diez mánagers.

    Hace falta tenerlas de todos porque un aviso solo vale si ese equipo está
    entre los PEORES de la liga en eso. Con umbrales fijos salían los mismos
    avisos en todos: "Jornada cuesta arriba" en 8 de 10, "Dinero parado" en 7.
    Y hay debilidades que tiene todo el mundo y por eso no dicen nada: en esta
    liga los diez equipos van sin delantero suplente."""
    resultado = {}
    try:
        hist = cargar_historico_completo(huella)
    except Exception:
        hist = None
    fotos = {}
    if hist is not None and not hist.empty:
        h = hist.dropna(subset=['Fecha', 'Jugador']).copy()
        h['Jugador'] = h['Jugador'].astype(str).str.strip()
        ultima = h['Fecha'].max()
        for clave, dias in (('hoy', 0), ('hace7', 7), ('hace14', 14)):
            fechas = h.loc[h['Fecha'] <= ultima - pd.Timedelta(days=dias), 'Fecha']
            if fechas.empty:
                continue
            dia = h[h['Fecha'] == fechas.max()].drop_duplicates('Jugador')
            fotos[clave] = {j: (_a_float(p, None), _a_float(m, None), _a_float(v, None))
                            for j, p, m, v in zip(dia['Jugador'], dia['Puntos'], dia['Media Puntos'],
                                                  dia['Valor Actual (€)'])}
    hoy, hace7, hace14 = fotos.get('hoy', {}), fotos.get('hace7', {}), fotos.get('hace14', {})

    medias = pd.to_numeric(db['mercado']['Media Puntos'], errors='coerce')
    if 'PJ' in db['mercado'].columns:
        medias = medias[pd.to_numeric(db['mercado']['PJ'], errors='coerce').fillna(0) >= MIN_PJ_REFERENCIA]
    medias = medias[medias > 0].dropna()
    media_tipica = float(medias.median()) if not medias.empty else None
    pujas_de = _pujas_por_manager(_huella_pujas(db.get('contabilidad')))
    tramos = {}

    for manager in db['plantillas']['Participante'].dropna().unique():
        plantilla = db['plantillas'][db['plantillas']['Participante'] == manager].copy()
        try:
            _, once, titulares = calcular_mejor_once(plantilla.copy())
        except Exception:
            continue
        valor = lambda p: _a_float(p.get('Valor Actual (€)'), 0.0) or 0.0
        en_once = {str(t['Jugador']).strip() for t in titulares}
        banquillo = [f for _, f in plantilla.iterrows() if str(f['Jugador']).strip() not in en_once]
        valor_total = sum(valor(f) for _, f in plantilla.iterrows())
        valor_banquillo = sum(valor(f) for f in banquillo)

        # Racha de puntos de cada titular en las dos últimas semanas
        mala = []
        for t in titulares:
            nombre = str(t['Jugador']).strip()
            if nombre in hoy and nombre in hace14:
                pj_hoy = _partidos_jugados_dia(hoy[nombre][0], hoy[nombre][1])
                pj_antes = _partidos_jugados_dia(hace14[nombre][0], hace14[nombre][1])
                if pj_hoy is not None and pj_antes is not None and pj_hoy - pj_antes >= 2:
                    media_reciente = (hoy[nombre][0] - hace14[nombre][0]) / (pj_hoy - pj_antes)
                    if media_reciente < 2:
                        mala.append((nombre, media_reciente))

        # Lo que ha ganado o perdido su plantilla en valor en una semana
        cambios = [(str(f['Jugador']).strip(), hoy[j][2] - hace7[j][2])
                   for _, f in plantilla.iterrows() for j in [str(f['Jugador']).strip()]
                   if j in hoy and j in hace7 and hoy[j][2] is not None and hace7[j][2] is not None]

        duros, dificultad_tramo = [], []
        for t in titulares:
            equipo = t.get('Equipo')
            partido = get_fixture_equipo(equipo)
            if partido and partido['dificultad'] >= cortes_color_dificultad()[3]:
                duros.append((partido['dificultad'], t['Jugador'], partido['rival']))
            if equipo not in tramos:
                tramos[equipo] = tramo_de_calendario(equipo, 3)
            if tramos[equipo]:
                dificultad_tramo.append((tramos[equipo]['media'], t['Jugador'], equipo))

        parados = []
        if media_tipica is not None and titulares:
            umbral = sorted(valor(t) for t in titulares)[len(titulares) // 2]
            parados = [(t['Jugador'], _a_float(t.get('Media Puntos'), 0.0) or 0.0, valor(t)) for t in titulares
                       if valor(t) >= umbral and (_a_float(t.get('PJ'), 0.0) or 0.0) >= MIN_PJ_REFERENCIA
                       and (_a_float(t.get('Media Puntos'), None) or 0.0) < media_tipica]

        sanos_banquillo = {_pos_principal(f.get('Posición')) for f in banquillo
                           if str(f.get('Lesion', 'no')).strip().lower() != 'si'}
        patron = patron_mgr[patron_mgr['Persona'] == manager] if not patron_mgr.empty else pd.DataFrame()
        resultado[manager] = {
            'jugadores': len(plantilla),
            'lineas': {linea: (float(np.mean([p.get('_xPts', 0) or 0 for p in jugadores])) if jugadores else None)
                       for linea, jugadores in once.items()},
            'poco': sorted(((probabilidad_de_jugar(t), t['Jugador']) for t in titulares
                            if probabilidad_de_jugar(t) < 0.60), key=lambda x: x[0]),
            'mala': sorted(mala, key=lambda x: x[1]),
            'duros': sorted(duros, reverse=True),
            'tramo': float(np.mean([d for d, _, _ in dificultad_tramo])) if dificultad_tramo else None,
            # Por equipo y no por jugador: tres del Atlético con el mismo
            # calendario son un solo dato, no tres.
            'tramo_equipos': sorted(((d, e, sum(1 for _, _, e2 in dificultad_tramo if e2 == e))
                                     for e, d in {e: d for d, _, e in dificultad_tramo}.items()),
                                    reverse=True)[:3],
            'parados': parados, 'valor_parado': sum(v for _, _, v in parados),
            'media_tipica': media_tipica,
            'banquillo_valor': valor_banquillo,
            'banquillo_cuota': valor_banquillo / valor_total if valor_total else 0.0,
            'banquillo_caros': [f['Jugador'] for f in sorted(banquillo, key=valor, reverse=True)[:3]],
            'variacion_7d': sum(d for _, d in cambios),
            'bajan': sorted((c for c in cambios if c[1] < 0), key=lambda c: c[1])[:3],
            'sin_recambio': [l for l, nombre in (('DEF', 'Defensa'), ('MED', 'Centrocampista'), ('DEL', 'Delantero'))
                             if nombre not in sanos_banquillo],
            'pujas': pujas_de.get(manager, 0),
            'redondeo': float(patron['Prob_Redondeo'].iloc[0]) if len(patron) else None,
        }
    return resultado


NOMBRE_LINEA = {'POR': 'portería', 'DEF': 'defensa', 'MED': 'el medio', 'DEL': 'la delantera'}
LINEA_RECAMBIO = {'DEF': 'defensa', 'MED': 'el medio', 'DEL': 'la delantera'}


def _chip(texto):
    return f"<span class='rv-chip'>{texto}</span>"


def _entre_los_peores(valor, todos, cuantos, mayor_es_peor=True):
    """¿Está este valor entre los `cuantos` peores de la liga? (con empates)"""
    validos = sorted((v for v in todos if v is not None), reverse=mayor_es_peor)
    if valor is None or len(validos) < 4:
        return False
    corte = validos[min(cuantos, len(validos)) - 1]
    return valor >= corte if mayor_es_peor else valor <= corte


@st.cache_data(show_spinner=False)
def equipos_sin_partido_esta_jornada(huella=None):
    """Equipos que no juegan en la jornada que viene: su partido de esa jornada
    está aplazado (fecha a más de 6 días del inicio de la jornada) o no existe."""
    cal = df_cal_global
    if cal is None or cal.empty:
        return set()
    hoy = pd.Timestamp(datetime.now().date())
    pendientes = cal[(cal['Estado'] == 'Pendiente') & cal['Fecha'].notna() & (cal['Fecha'] >= hoy)]
    if pendientes.empty:
        return set()
    jornada = int(pendientes.sort_values('Fecha').iloc[0]['Jornada'])
    de_la_jornada = cal[cal['Jornada'] == jornada]
    con_fecha = de_la_jornada.dropna(subset=['Fecha'])
    if len(con_fecha) < 6:         # sin horarios aún: no se puede afirmar nada
        return set()
    inicio = con_fecha['Fecha'].min()
    fuera = set()
    todos = set(cal['Local'].dropna()) | set(cal['Visitante'].dropna())
    for equipo in todos:
        partido = de_la_jornada[(de_la_jornada['Local'] == equipo) | (de_la_jornada['Visitante'] == equipo)]
        if partido.empty:
            fuera.add(equipo)
            continue
        fecha = partido['Fecha'].iloc[0]
        if pd.notna(fecha) and fecha > inicio + pd.Timedelta(days=6):
            fuera.add(equipo)
    return fuera


def analisis_rival(seleccion, mgr_data, plantilla, best_xi, xi_players, resumen_liga):
    """Lo que hay que saber de un mánager, con forma para pintarlo.

    'flojos'  : [{'grave', 'titulo', 'dato', 'chips', 'nota'}]
    'jornada' : puesto de su once esta jornada.
    'puja'    : cómo puja (solo rivales con cinco pujas o más).

    Se vigilan veinte debilidades. Las que son un problema por sí mismas
    (números rojos, huecos, titulares de baja, partido aplazado) salen siempre
    que se den. El resto solo
    cuando ese equipo está entre los peores de la liga en eso: así cada equipo
    enseña lo suyo y no los mismos avisos que todos."""
    flojos = []
    tuyo = seleccion == MI_EQUIPO
    su = "tu" if tuyo else "su"
    liga = metricas_liga(_huella_excel(resolver_excel_path()))
    m = liga.get(seleccion, {})
    todos = lambda clave: [v.get(clave) for v in liga.values()]

    def aviso(titulo, dato="", chips=(), nota="", grave=False, lista=(), rotulo_lista=""):
        flojos.append({'grave': grave, 'titulo': titulo, 'dato': dato, 'chips': list(chips), 'nota': nota,
                       'lista': list(lista), 'rotulo_lista': rotulo_lista})

    # ── Lo que es un problema siempre ────────────────────────────────────────
    saldo = _a_float(mgr_data.get('Balance Total (€)'), 0.0) or 0.0
    if saldo < 0:
        # En Biwenger, empezar la jornada en negativo es no puntuar. Se dice
        # además con qué venta le duele menos salir: la que menos puntos le
        # quita (ventas que puede hacer hoy, sin candado).
        opciones = buscar_ventas_para_deuda(jugadores_vendibles(seleccion, recortar=False), -saldo,
                                            max_opciones=1)
        lista, rotulo = [], ""
        if opciones:
            # Una fila por venta: nombre, lo que da y, si aún tiene candado,
            # desde cuándo se puede vender. Antes iba todo en etiquetas y una
            # frase larga, y la tarjeta quedaba apelotonada.
            for f in opciones[0]['jugadores']:
                libre = fecha_desbloqueo(f['Jugador'], seleccion)
                lista.append((f['Jugador'], formato_euro(_a_float(f.get('Valor Actual (€)'), 0.0)),
                              f"🔒 {libre:%d/%m}" if libre else ""))
            rotulo = "La venta que menos te quita" if tuyo else "La venta que menos le quita"
        inicio, _ = inicio_proxima_jornada(_huella_excel(resolver_excel_path()))
        plazo = (f"en positivo antes del {DIAS_SEMANA_CAL[inicio.weekday()][:3].lower()} {inicio:%d/%m}"
                 + (f" · {inicio:%H:%M}" if (inicio.hour or inicio.minute) else "")) if inicio else "en positivo antes de la jornada"
        if not opciones:
            plazo += " · ni vendiendo " + ("llegas" if tuyo else "llega")
        aviso("En números rojos", formato_euro(saldo), nota=plazo, grave=True,
              lista=lista, rotulo_lista=rotulo)

    faltan = []
    if not best_xi['POR']:
        faltan.append("portero")
    for clave, minimo, nombre in (('DEF', 3, 'defensa'), ('MED', 3, 'medio')):
        hueco = minimo - len(best_xi[clave])
        if hueco > 0:
            faltan.append(f"{hueco} {nombre}{'s' if hueco > 1 else ''}")
    if not best_xi['DEL']:
        faltan.append("delantero")
    if faltan:
        aviso(f"Huecos en {su} once", chips=[_chip(f) for f in faltan],
              nota="" if tuyo else "pujará por esa posición", grave=True)

    # Bajas y dudas, TODAS en una sola tarjeta: lesionados, sancionados y en
    # duda, sean titulares o suplentes. Antes eran tres tarjetas (titulares de
    # baja, suplentes de baja, dudas en el once) con un nombre cada una. Es
    # grave si alguna baja le quita un titular: un suplente lesionado no le
    # cuesta nada; un titular, sí.
    estados = {str(f['Jugador']): estado_jugador(f) for _, f in plantilla.iterrows()}
    tocados = [j for j, e in estados.items() if e in NO_DISPONIBLE or e == 'duda']
    if tocados:
        _, _, once_sano = calcular_mejor_once(plantilla.assign(Lesion='no'))
        titulares = {str(p['Jugador']) for p in once_sano} | {str(p['Jugador']) for p in xi_players}
        # Primero las bajas de titulares, luego las dudas, luego el resto.
        orden = sorted(tocados, key=lambda j: (0 if (j in titulares and estados[j] != 'duda') else
                                               1 if j in titulares else 2 if estados[j] != 'duda' else 3, j))
        lista = [(f"{_mini_icono_estado(estados[j])}{j}",
                  "<span style='color:#fca5a5; font-weight:600;'>titular</span>" if j in titulares
                  else "<span style='color:#7d8699; font-weight:500;'>suplente</span>", "")
                 for j in orden]
        bajas_titulares = sum(1 for j in tocados if j in titulares and estados[j] != 'duda')
        aviso("Bajas y dudas", str(len(tocados)), lista=lista,
              nota=(f"{bajas_titulares} titular{'es' if bajas_titulares != 1 else ''} de baja"
                    if bajas_titulares else "ningún titular de baja"),
              grave=bajas_titulares > 0)

    # Titulares cuyo equipo no juega esta jornada (partido aplazado): cero
    # puntos seguros si se quedan en el once.
    sin_partido = [str(p['Jugador']) for p in xi_players
                   if p.get('Equipo') in equipos_sin_partido_esta_jornada(_huella_excel(resolver_excel_path()))]
    if sin_partido:
        aviso("Sin partido esta jornada", str(len(sin_partido)),
              chips=[_chip(j) for j in sin_partido[:5]], nota="su partido está aplazado: 0 puntos", grave=True)

    if 0 <= saldo < 1_000_000:
        aviso("Sin margen para pujar", formato_euro(saldo),
              nota=f"{'no puedes' if tuyo else 'no puede'} ir fuerte en una subasta")

    if m.get('poco'):
        aviso("Titulares que juegan poco", str(len(m['poco'])),
              chips=[_chip(f"{n} <span class='rv-chip-sub'>{p:.0%}</span>") for p, n in m['poco'][:3]],
              nota="probabilidad de que jueguen")

    if m.get('mala'):
        aviso("Titulares en mala racha", str(len(m['mala'])),
              chips=[_chip(f"{n} <span class='rv-chip-sub'>{formato_puntos(r)}</span>") for n, r in m['mala'][:3]],
              nota="media en las dos últimas semanas")

    if xi_players:
        valor_once = sum(_a_float(p.get('Valor Actual (€)'), 0.0) or 0.0 for p in xi_players)
        estrella = max(xi_players, key=lambda p: _a_float(p.get('Valor Actual (€)'), 0.0) or 0.0)
        cuota = (_a_float(estrella.get('Valor Actual (€)'), 0.0) or 0.0) / valor_once if valor_once else 0
        if cuota > 0.40:
            aviso(f"Depende de {estrella['Jugador']}", f"{cuota:.0%}", nota=f"del valor de {su} once")
        equipos = [p.get('Equipo') for p in xi_players if pd.notna(p.get('Equipo'))]
        if equipos:
            club, repetidos = Counter(equipos).most_common(1)[0]
            if repetidos / len(equipos) >= 0.45:
                aviso(f"Depende del {club}", f"{repetidos} de {len(equipos)}", nota="titulares de un mismo club")

    if 0 < m.get('jugadores', 99) <= 12:
        aviso("Plantilla corta", f"{m['jugadores']}", nota="jugadores: cualquier baja le deja sin recambio")

    # ── Lo que solo cuenta si está entre los peores de la liga ───────────────
    lineas = {k: v.get('lineas', {}) for k, v in liga.items()}
    peor = None
    for linea, valor in m.get('lineas', {}).items():
        todas = sorted((v[linea] for v in lineas.values() if v.get(linea) is not None), reverse=True)
        if valor is not None and len(todas) >= 5 and todas.index(valor) + 1 == len(todas):
            peor = (linea, len(todas))
    if peor:
        aviso(f"Flojo en {NOMBRE_LINEA[peor[0]]}", f"{peor[1]}º de {peor[1]}",
              nota="la peor de la liga" + ("" if tuyo else "; buscará por ahí"))

    duros = m.get('duros', [])
    if len(duros) >= 3 and _entre_los_peores(len(duros), [len(v.get('duros', [])) for v in liga.values()], 2):
        # Agrupados por rival: cuatro contra el Real Madrid son una etiqueta, y
        # los nombres salen al pasar el ratón.
        por_rival = {}
        for _, nombre, rival in duros:
            por_rival.setdefault(rival, []).append(nombre)
        chips = [f"<span class='rv-chip' title='{', '.join(nombres)}'>vs {rival} "
                 f"<span class='rv-chip-sub'>{len(nombres)}</span></span>"
                 for rival, nombres in sorted(por_rival.items(), key=lambda kv: -len(kv[1]))[:3]]
        aviso("Jornada cuesta arriba", f"{len(duros)} de {len(xi_players)}", chips=chips,
              nota="titulares ante rival duro")

    if (m.get('tramo') or 0) > umbrales_tramo()[1] and _entre_los_peores(m.get('tramo'), todos('tramo'), 2):
        aviso("Le viene un tramo duro", f"{m['tramo']:.0f}",
              chips=[_chip(f"{e} <span class='rv-chip-sub'>{n} titular{'es' if n > 1 else ''}</span>")
                     for _, e, n in m['tramo_equipos']],
              nota="dificultad de sus tres próximos partidos, sobre 100")

    if m.get('valor_parado', 0) > 0 and _entre_los_peores(m['valor_parado'], todos('valor_parado'), 3):
        aviso("Dinero parado", formato_euro(m['valor_parado']),
              chips=[_chip(f"{n} <span class='rv-chip-sub'>{formato_puntos(med)}</span>") for n, med, _ in m['parados'][:3]],
              nota=f"titulares caros por debajo de la media de la liga ({formato_puntos(m['media_tipica'])})")

    if m.get('banquillo_cuota', 0) >= 0.15 and _entre_los_peores(m['banquillo_cuota'], todos('banquillo_cuota'), 2):
        aviso("Banquillo caro", formato_euro(m['banquillo_valor']),
              chips=[_chip(n) for n in m['banquillo_caros']],
              nota=f"el {m['banquillo_cuota']:.0%} del valor, sin puntuar")

    if (m.get('variacion_7d') or 0) <= -1_000_000 and _entre_los_peores(
            m['variacion_7d'], todos('variacion_7d'), 2, mayor_es_peor=False):
        aviso("Plantilla a la baja", formato_euro(m['variacion_7d']),
              chips=[_chip(f"{n} <span class='rv-chip-sub'>{formato_euro(d)}</span>") for n, d in m['bajan']],
              nota="de valor en una semana")

    # Sin recambio en una línea: solo si es raro en la liga. Si les pasa a
    # todos (aquí, a los diez en la delantera), no es una debilidad de nadie.
    for linea in m.get('sin_recambio', []):
        cuantos = sum(1 for v in liga.values() if linea in v.get('sin_recambio', []))
        if cuantos <= 3:
            aviso(f"Sin recambio en {LINEA_RECAMBIO[linea]}",
                  nota="ningún suplente sano en esa línea: una baja y juega con uno menos")

    if not tuyo:
        pujas = m.get('pujas', 0)
        redondeo = m.get('redondeo')
        if pujas >= 5 and redondeo is not None and redondeo >= 0.75:
            aviso("Puja en cifras redondas", f"{redondeo:.0%}", nota="de sus pujas; pásate de la cifra redonda")
        todas_pujas = [v.get('pujas', 0) for v in liga.values()]
        mediana = float(np.median(todas_pujas)) if todas_pujas else 0
        if mediana and pujas < mediana / 2 and _entre_los_peores(pujas, todas_pujas, 2, mayor_es_peor=False):
            aviso("Casi no puja", f"{pujas}", nota=f"pujas en toda la temporada (la liga, {mediana:.0f})")

    jornada = None
    if resumen_liga and seleccion in resumen_liga:
        orden = sorted(resumen_liga, key=lambda n: -(resumen_liga[n].get('xpts') or 0))
        jornada = {'puesto': orden.index(seleccion) + 1, 'total': len(orden)}

    puja = None
    if not tuyo and not patron_mgr.empty:
        fila = patron_mgr[patron_mgr['Persona'] == seleccion]
        pujas = m.get('pujas', 0)
        if not fila.empty and pujas >= 5:
            patron = fila.iloc[0]
            desviacion = _a_float(patron.get('Std_Derroche'), 0.0) or 0.0
            puja = {'sobre': _a_float(patron.get('Perfil_Derroche_Crudo'), 0.0) or 0.0,
                    'forma': ("muy irregular" if desviacion > 0.20 else
                              "muy regular" if desviacion < 0.08 else "regular"),
                    'pujas': pujas}
    return {'flojos': flojos, 'jornada': jornada, 'puja': puja, 'saldo': saldo}


CSS_RIVAL = """
<style>
.rv-titulo { display:flex; align-items:center; justify-content:center; gap:14px; color:#f2f4f8; font-size:0.92rem; font-weight:800; letter-spacing:0.16em; text-transform:uppercase; text-align:center; margin:30px 0 18px 0; }
.rv-titulo::before { content:''; width:34px; height:2px; border-radius:2px; background:linear-gradient(90deg, transparent, #e7c565); }
.rv-titulo::after { content:''; width:34px; height:2px; border-radius:2px; background:linear-gradient(90deg, #e7c565, transparent); }
/* Barra de arriba: cuatro datos en línea, centrados y separados por una raya */
.rv-barra { display:flex; align-items:stretch; justify-content:space-around; flex-wrap:wrap; row-gap:10px; }
.rv-kpi { flex:1; min-width:130px; display:flex; flex-direction:column; align-items:center; justify-content:center;
          gap:5px; padding:0 10px; text-align:center; }
.rv-kpi + .rv-kpi { border-left:1px solid rgba(255,255,255,0.08); }
.rv-kpi-rot { color:#8b93a7; font-size:0.66rem; letter-spacing:0.12em; text-transform:uppercase; }
.rv-kpi-val { font-family:'Fraunces', Georgia, serif; font-size:1.45rem; font-weight:600; color:#f2f4f8;
              line-height:1; font-variant-numeric:tabular-nums; white-space:nowrap; }
.rv-kpi-de { font-family:Inter, sans-serif; font-size:0.78rem; color:#8b93a7; font-weight:500; margin-left:4px; }
.rv-kpi-sub { color:#8b93a7; font-size:0.72rem; }
.rv-lineas { display:flex; gap:4px; flex-wrap:wrap; justify-content:center; }
.rv-linea { background:rgba(255,255,255,0.06); border-radius:5px; padding:1px 6px; font-size:0.7rem;
            color:#aab3c2; white-space:nowrap; }
.rv-linea b { color:#f2f4f8; margin-left:3px; }
.rv-puntos { display:flex; gap:4px; align-items:center; justify-content:center; }
.rv-punto { width:7px; height:7px; border-radius:50%; background:rgba(255,255,255,0.13); }
.rv-punto.activo { width:10px; height:10px; }
/* Alarmas: tarjetas del tamaño de lo que cuentan, centradas. Arriba el
   rótulo con su color, luego la cifra grande y debajo el detalle. */
.rv-alertas { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 280px)); grid-auto-rows:1fr;
               justify-content:center; gap:12px; margin-bottom:26px; }
.rv-alerta { display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center;
             gap:6px; padding:14px 16px 15px; border-radius:16px; position:relative; overflow:hidden;
             background:linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.012));
             border:1px solid rgba(255,255,255,0.08); }
.rv-alerta::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:var(--c); }
.rv-alerta.rv-grave { --c:#f87171; background:linear-gradient(180deg, rgba(248,113,113,0.10), rgba(248,113,113,0.02));
                      border-color:rgba(248,113,113,0.28); }
.rv-alerta.rv-aviso { --c:#fbbf24; }
.rv-alerta.rv-bien { --c:#4ade80; }
.rv-al-titulo { display:flex; align-items:center; gap:7px; color:#c3cbd9; font-size:0.64rem; font-weight:700;
                letter-spacing:0.14em; text-transform:uppercase; line-height:1.3; }
.rv-al-titulo::before { content:''; width:7px; height:7px; border-radius:50%; background:var(--c); flex:none;
                        box-shadow:0 0 0 3px color-mix(in srgb, var(--c) 22%, transparent); }
.rv-al-dato { font-family:'Inter', sans-serif !important; font-size:1.55rem; font-weight:800; line-height:1.1;
              white-space:nowrap; font-variant-numeric:tabular-nums; letter-spacing:-0.01em; }
.rv-grave .rv-al-dato { color:#fca5a5; } .rv-aviso .rv-al-dato { color:#fcd34d; }
.rv-al-nota { color:#8b93a7; font-size:0.72rem; line-height:1.35; max-width:260px; }
.rv-al-l2 { display:flex; gap:5px; flex-wrap:wrap; justify-content:center; margin-top:2px; }
.rv-chip { display:inline-flex; align-items:center; background:rgba(255,255,255,0.07); border-radius:999px;
           padding:2px 9px; font-size:0.72rem; color:#e5e9f0; white-space:nowrap; }
.rv-chip-sub { color:#8b93a7; margin-left:5px; }
.rv-al-lista { width:100%; margin-top:6px; padding-top:9px; border-top:1px solid rgba(255,255,255,0.07); }
.rv-al-rotulo { color:#7d8699; font-size:0.58rem; font-weight:700; letter-spacing:0.14em; text-transform:uppercase;
                margin-bottom:6px; }
.rv-al-fila { display:flex; align-items:center; gap:8px; padding:3px 2px; font-size:0.78rem; color:#e5e9f0; }
.rv-al-fila span:first-child { flex:1; text-align:left; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.rv-al-fila .rv-al-val { color:#f4f6fa; font-weight:700; font-variant-numeric:tabular-nums; }
.rv-al-fila .rv-al-extra { color:#fcd34d; font-size:0.66rem; background:rgba(251,191,36,0.10);
                           border-radius:999px; padding:1px 7px; }
</style>
"""


def _barra_rival(analisis, total_jugadores, porteros, defensas, medios, delanteros):
    """La barra de arriba: su puesto esta jornada, saldo, plantilla y, si es un
    rival, cómo puja. El valor del once no se repite: ya está sobre el campo."""
    kpis = []
    jornada = analisis['jornada']
    if jornada:
        puesto, total = jornada['puesto'], jornada['total']
        color = '#4ade80' if puesto <= 3 else '#f87171' if puesto > total - 3 else '#fcd34d'
        puntos = "".join(f"<span class='rv-punto{' activo' if k == puesto else ''}' "
                         f"style='{f'background:{color};' if k == puesto else ''}'></span>"
                         for k in range(1, total + 1))
        kpis.append(f"<div class='rv-kpi'><div class='rv-kpi-rot'>Esta jornada</div>"
                    f"<div class='rv-kpi-val' style='color:{color};'>{puesto}º<span class='rv-kpi-de'>de {total}</span></div>"
                    f"<div class='rv-puntos'>{puntos}</div></div>")
    saldo = analisis['saldo']
    kpis.append(f"<div class='rv-kpi'><div class='rv-kpi-rot'>Saldo</div>"
                f"<div class='rv-kpi-val' style='color:{'#f87171' if saldo < 0 else '#f2f4f8'};' "
                f"title='{formato_euro(saldo)}'>{formato_euro(saldo)}</div>"
                f"<div class='rv-kpi-sub'>{'tiene que vender' if saldo < 0 else 'disponible'}</div></div>")
    lineas = "".join(f"<span class='rv-linea'>{rot}<b>{n}</b></span>"
                     for rot, n in (('POR', porteros), ('DEF', defensas), ('MED', medios), ('DEL', delanteros)))
    kpis.append(f"<div class='rv-kpi'><div class='rv-kpi-rot'>Plantilla</div>"
                f"<div class='rv-kpi-val'>{total_jugadores}<span class='rv-kpi-de'>jugadores</span></div>"
                f"<div class='rv-lineas'>{lineas}</div></div>")
    puja = analisis['puja']
    if puja:
        kpis.append(f"<div class='rv-kpi'><div class='rv-kpi-rot'>Cómo puja</div>"
                    f"<div class='rv-kpi-val'>{puja['sobre']:+.0%}<span class='rv-kpi-de'>sobre el valor</span></div>"
                    f"<div class='rv-kpi-sub'>{puja['forma']} · {puja['pujas']} pujas</div></div>")
    return f"<div class='rv-barra'>{''.join(kpis)}</div>"


def _tarjeta_alerta(f):
    lista = ""
    if f.get('lista'):
        lista = ("<div class='rv-al-lista'>"
                 + (f"<div class='rv-al-rotulo'>{f['rotulo_lista']}</div>" if f.get('rotulo_lista') else "")
                 + "".join(f"<div class='rv-al-fila'><span>{n}</span>"
                           + (f"<span class='rv-al-extra'>{x}</span>" if x else "")
                           + f"<span class='rv-al-val'>{v}</span></div>" for n, v, x in f['lista'])
                 + "</div>")
    ancha = ""
    return (f"<div class='rv-alerta {'rv-grave' if f['grave'] else 'rv-aviso'}{ancha}'>"
            f"<div class='rv-al-titulo'>{f['titulo']}</div>"
            + (f"<div class='rv-al-dato'>{f['dato']}</div>" if f['dato'] else "")
            + (f"<div class='rv-al-nota'>{f['nota']}</div>" if f['nota'] else "")
            + (f"<div class='rv-al-l2'>{''.join(f['chips'])}</div>" if f['chips'] else "")
            + lista + "</div>")


def _alertas_html(analisis, tuyo):
    titulo = "Puntos débiles"
    flojos = sorted(analisis['flojos'], key=lambda f: not f['grave'])
    if not flojos:
        filas = ("<div class='rv-alerta rv-bien'><div class='rv-al-titulo'>"
                 + ("Sin puntos flojos" if tuyo else "Sin puntos flojos a la vista") + "</div></div>")
    else:
        filas = "".join(_tarjeta_alerta(f) for f in flojos)
    return f"<div class='rv-titulo'>{titulo}</div><div class='rv-alertas'>{filas}</div>"


CSS_TU_CONTRA = """
<style>
.vs { background:linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.012));
      border:1px solid rgba(255,255,255,0.07); border-radius:12px; padding:16px 22px 10px 22px; margin:4px 0 6px 0; }
.vs-cab { display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:14px;
          padding-bottom:12px; margin-bottom:6px; border-bottom:1px solid rgba(255,255,255,0.06); }
.vs-lado { display:flex; flex-direction:column; gap:2px; }
.vs-lado.der { text-align:right; align-items:flex-end; }
.vs-nombre { font-family:'Fraunces', Georgia, serif; font-size:1.2rem; font-weight:600; color:#f2f4f8; }
.vs-sub { color:#8b93a7; font-size:0.72rem; letter-spacing:0.1em; text-transform:uppercase; }
.vs-marcador { text-align:center; }
.vs-marcador-num { font-family:'Fraunces', Georgia, serif; font-size:1.9rem; font-weight:600; line-height:1; }
.vs-marcador-guion { color:#4b5363; margin:0 8px; font-size:1.4rem; }
.vs-marcador-txt { color:#8b93a7; font-size:0.66rem; letter-spacing:0.1em; text-transform:uppercase; margin-top:4px; }
.vs-fila { display:grid; grid-template-columns:96px 1fr 170px 1fr 96px; align-items:center; gap:12px; padding:7px 0; }
.vs-fila + .vs-fila { border-top:1px solid rgba(255,255,255,0.04); }
.vs-val { font-family:'Fraunces', Georgia, serif; font-size:1.08rem; font-weight:600; color:#8b93a7;
          font-variant-numeric:tabular-nums; white-space:nowrap; }
.vs-val.izq { text-align:right; } .vs-val.der { text-align:left; }
.vs-val.gana { color:#f2f4f8; }
.vs-pista { height:7px; border-radius:4px; background:rgba(255,255,255,0.05); overflow:hidden; display:flex; }
.vs-pista.izq { justify-content:flex-end; }
.vs-pista span { display:block; height:100%; border-radius:4px; }
.vs-rotulo { text-align:center; color:#aeb6c4; font-size:0.8rem; line-height:1.2; }
.vs-dif { display:block; font-size:0.7rem; font-weight:600; margin-top:2px; }
</style>
"""
VS_TU, VS_EL, VS_GRIS = '#4ade80', '#f87171', 'rgba(255,255,255,0.14)'


def _html_tu_contra(rival, mio, suyo, orden_jornada, marcador):
    """Tú contra un rival en cuatro duelos: valor del once, media de los
    titulares, puesto esta jornada y subastas en las que os habéis cruzado.
    Cada fila, con el ganador resaltado y la barra de su lado encendida."""
    filas, gano, pierdo = [], 0, 0

    def fila(rotulo, a, b, texto_a, texto_b, dif="", menor_gana=False, dif_neutro=False):
        nonlocal gano, pierdo
        if a is None or b is None:
            return
        gana_a = (a < b) if menor_gana else (a > b)
        gana_b = (b < a) if menor_gana else (b > a)
        gano += gana_a
        pierdo += gana_b
        # Barras: proporcionales a cada valor (o al revés si gana el menor).
        va, vb = (1 / max(a, 1e-9), 1 / max(b, 1e-9)) if menor_gana else (max(a, 0), max(b, 0))
        tope = max(va, vb) or 1
        color_dif = '#8b93a7' if dif_neutro else (VS_TU if gana_a else VS_EL if gana_b else '#8b93a7')
        filas.append(
            f"<div class='vs-fila'>"
            f"<div class='vs-val izq{' gana' if gana_a else ''}'>{texto_a}</div>"
            f"<div class='vs-pista izq'><span style='width:{va / tope * 100:.0f}%; "
            f"background:{VS_TU if gana_a else VS_GRIS};'></span></div>"
            f"<div class='vs-rotulo'>{rotulo}"
            + (f"<span class='vs-dif' style='color:{color_dif};'>{dif}</span>" if dif else "") + "</div>"
            f"<div class='vs-pista'><span style='width:{vb / tope * 100:.0f}%; "
            f"background:{VS_EL if gana_b else VS_GRIS};'></span></div>"
            f"<div class='vs-val der{' gana' if gana_b else ''}'>{texto_b}</div></div>")

    if suyo.get('valor'):
        pct = (mio['valor'] - suyo['valor']) / suyo['valor'] * 100
        fila("Valor del once", mio['valor'], suyo['valor'], formato_euro(mio['valor']),
             formato_euro(suyo['valor']), f"{pct:+.0f}%")
    if mio.get('media') is not None and suyo.get('media') is not None:
        fila("Media de titulares", mio['media'], suyo['media'], formato_puntos(mio['media']),
             formato_puntos(suyo['media']), (f"{mio['media'] - suyo['media']:+.2f}".replace('.', ',') + " pts"))
    if MI_EQUIPO in orden_jornada and rival in orden_jornada:
        pm, ps = orden_jornada.index(MI_EQUIPO) + 1, orden_jornada.index(rival) + 1
        fila("Esta jornada", pm, ps, f"{pm}º", f"{ps}º", f"de {len(orden_jornada)}", menor_gana=True, dif_neutro=True)
    if marcador.get('veces'):
        fila("Subastas ganadas", marcador.get('gane', 0), marcador.get('perdi', 0),
             str(marcador.get('gane', 0)), str(marcador.get('perdi', 0)),
             f"{marcador['veces']} cruce{'s' if marcador['veces'] != 1 else ''}", dif_neutro=True)

    return (CSS_TU_CONTRA + "<div class='vs'><div class='vs-cab'>"
            f"<div class='vs-lado'><span class='vs-sub'>Tú</span><span class='vs-nombre'>{MI_EQUIPO}</span></div>"
            f"<div class='vs-marcador'><span class='vs-marcador-num' style='color:{VS_TU};'>{gano}</span>"
            f"<span class='vs-marcador-guion'>–</span>"
            f"<span class='vs-marcador-num' style='color:{VS_EL};'>{pierdo}</span>"
            f"<div class='vs-marcador-txt'>duelos ganados</div></div>"
            f"<div class='vs-lado der'><span class='vs-sub'>Rival</span><span class='vs-nombre'>{rival}</span></div>"
            f"</div>{''.join(filas)}</div>")


def ui_rival():
    managers = sorted(db['participantes']['Persona'].dropna().tolist())
    if not managers:
        st.info("No hay mánagers en la hoja Participantes.")
        return
    # Siempre hay un mánager elegido (el tuyo al abrir): el hueco en blanco del
    # desplegable no servía para nada.
    if st.session_state.get('rival_manager') not in managers:
        st.session_state['rival_manager'] = MI_EQUIPO if MI_EQUIPO in managers else managers[0]

    # 🧭 Una sola barra arriba: a la izquierda a quién miras y a la derecha lo
    # esencial de su equipo. Antes el desplegable iba solo en una caja enorme,
    # y los datos, en cuatro tarjetas grandes más abajo.
    with st.container(border=True):
        try:
            c_sel, c_barra = st.columns([1, 3.4], vertical_alignment="center")
        except TypeError:          # Streamlit antiguo: sin alineación vertical
            c_sel, c_barra = st.columns([1, 3.4])
        seleccion = c_sel.selectbox("Mánager", managers, key="rival_manager")

    if seleccion:
        st.markdown("<div class='animate-fade-in'>", unsafe_allow_html=True)

        mgr_data = db['participantes'][db['participantes']['Persona'] == seleccion].iloc[0]
        plantilla = db['plantillas'][db['plantillas']['Participante'] == seleccion].copy()

        total_jugadores = len(plantilla)
        comodines = sum(plantilla['Posición'].astype(str).str.contains('/'))

        porteros = sum(plantilla['Posición'].astype(str).str.contains('Portero', case=False, na=False))
        defensas = sum(plantilla['Posición'].astype(str).str.contains('Defensa', case=False, na=False))
        medios = sum(plantilla['Posición'].astype(str).str.contains('Centrocampista', case=False, na=False))
        delanteros = sum(plantilla['Posición'].astype(str).str.contains('Delantero', case=False, na=False))

        plantilla['Pos_Main'] = plantilla['Posición'].apply(lambda x: str(x).split('/')[0].strip())
        val_por = plantilla[plantilla['Pos_Main'] == 'Portero']['Valor Actual (€)'].sum()
        val_def = plantilla[plantilla['Pos_Main'] == 'Defensa']['Valor Actual (€)'].sum()
        val_med = plantilla[plantilla['Pos_Main'] == 'Centrocampista']['Valor Actual (€)'].sum()
        val_del = plantilla[plantilla['Pos_Main'] == 'Delantero']['Valor Actual (€)'].sum()

        best_form, best_xi, xi_players = calcular_mejor_once(plantilla)
        jugadores_sanos = plantilla[plantilla['Lesion'] != 'si']

        resumen_liga = resumen_onces_liga(_huella_excel(resolver_excel_path()))

        best_value = 0
        top_player = None
        messi_pct = 0
        if len(xi_players) > 0:
            best_value = sum(p['Valor Actual (€)'] for p in xi_players)
            top_player = max(xi_players, key=lambda x: x['Valor Actual (€)'])
            messi_pct = (top_player['Valor Actual (€)'] / best_value) * 100

        var_diaria_xi = sum((p.get('Variación Diaria (€)') or 0) if pd.notna(p.get('Variación Diaria (€)')) else 0 for p in xi_players)


        xi_names = [p['Jugador'] for p in xi_players]
        banquillo_df = plantilla[~plantilla['Jugador'].isin(xi_names)].sort_values(by='Valor Actual (€)', ascending=False)
        valor_suplente = banquillo_df['Valor Actual (€)'].sum() if len(banquillo_df) > 0 else 0
        var_diaria_banquillo = banquillo_df['Variación Diaria (€)'].sum() if len(banquillo_df) > 0 else 0

        def _html_variacion(valor, size='0.9em', chip=False):
            if pd.isna(valor) or valor == 0:
                color, texto = '#a0aec0', f'– Se mantiene (0 €)'
            elif valor > 0:
                color, texto = '#22c55e', f'▲ +{formato_euro(valor)}'
            else:
                color, texto = '#ef4444', f'▼ -{formato_euro(abs(valor))}'

            if chip:
                return (
                    f'<div style="display: inline-block; margin-top: 4px; padding: 3px 12px; '
                    f'background: rgba(15,17,23,0.9); border: 1px solid {color}; border-radius: 20px; '
                    f'color: {color}; font-size: {size}; font-weight: 800;">{texto}</div>'
                )
            return f'<div style="color: {color}; font-size: {size}; font-weight: 700; margin-top: 2px;">{texto}</div>'

        # ⚔️ Cómo te mides con él. Es la pestaña de inteligencia rival y no
        # mencionaba tu equipo por ningún lado: lo primero que uno quiere saber
        # aquí es si le gana o le gana él, y había que calcularlo de cabeza
        # saltando entre pestañas.
        # ⚔️ Tú contra él, cara a cara: cuatro duelos con el ganador resaltado,
        # en vez de cuatro frases que había que leer enteras para saber quién
        # iba por delante.
        if seleccion != MI_EQUIPO and MI_EQUIPO in resumen_liga and seleccion in resumen_liga:
            mio, suyo = resumen_liga[MI_EQUIPO], resumen_liga[seleccion]
            orden_jornada = sorted(resumen_liga, key=lambda n: -(resumen_liga[n].get('xpts') or 0))
            marcador = duelos_en_subastas(_huella_pujas(db.get('contabilidad')),
                                          MI_EQUIPO).get(seleccion) or {}
            st.markdown(_html_tu_contra(seleccion, mio, suyo, orden_jornada, marcador),
                        unsafe_allow_html=True)

        # 📋 Cómo encaja su plantilla y por dónde se le puede atacar. Eran cuatro
        # cajas de Streamlit con mucho aire y poco que decir ("Jugadores 17"),
        # un recuadro amarillo genérico por aviso y, lo más importante, el
        # puesto de la jornada escondido en gris al final. Ahora es una banda de
        # fichas con la jornada en grande y los avisos como tarjetas propias.
        analisis = analisis_rival(seleccion, mgr_data, plantilla, best_xi, xi_players, resumen_liga)
        tuyo = seleccion == MI_EQUIPO
        c_barra.markdown(CSS_RIVAL + _barra_rival(analisis, total_jugadores, porteros, defensas,
                                                  medios, delanteros), unsafe_allow_html=True)
        st.markdown(CSS_RIVAL + _alertas_html(analisis, tuyo), unsafe_allow_html=True)


        # 🌟 Los mejores de su once, por línea, con el mismo criterio que el
        # brillo de las cartas: calidad del jugador por la probabilidad de que
        # juegue. Es lo que mejor anticipa lo que va a dar en las próximas
        # jornadas, sin depender del rival de este domingo (antes se elegía por
        # los puntos esperados del próximo partido y cambiaba cada semana).
        def mejor_de(lista):
            return max(lista, key=lambda p: (indice_brillo_jugador(p),
                                             _a_float(p.get('Media Puntos'), 0.0) or 0.0)) if lista else None

        mejores_linea = [(nombre, mejor_de(best_xi[clave]), clave)
                         for nombre, clave in (("Delantero", "DEL"), ("Centrocampista", "MED"),
                                               ("Defensa", "DEF"), ("Portero", "POR"))]
        candidatos_mvp = [p for _, p, _ in mejores_linea if p is not None]
        mvp_all = max(candidatos_mvp, key=indice_brillo_jugador) if candidatos_mvp else None

        col_pitch, col_banquillo = st.columns([2.7, 1])

        with col_pitch:
            indices_liga = indices_valoracion(resumen_liga)
            estrellas_html, puesto_liga = estrellas_relativas(
                indices_liga.get(seleccion, 0.0), list(indices_liga.values())
            )

            def pintar_linea(jugadores, cantidad_requerida, pos_type):
                linea_html = '<div style="display: flex; justify-content: space-around; margin-bottom: 34px; position: relative; z-index: 2;">'
                for i in range(int(cantidad_requerida)):
                    if i < len(jugadores): linea_html += generar_carta_html(jugadores[i], pos_type, is_empty=False)
                    else: linea_html += generar_carta_html(None, pos_type, is_empty=True)
                linea_html += '</div>'
                return linea_html

            form_vals = best_form.split('-')
            req_d = int(form_vals[0]) if len(form_vals) == 3 else 3
            req_m = int(form_vals[1]) if len(form_vals) == 3 else 4
            req_f = int(form_vals[2]) if len(form_vals) == 3 else 3

            html_centro = f'<div style="background: linear-gradient(145deg, rgba(20,20,30,0.8), rgba(10,10,15,0.9)); backdrop-filter: blur(5px); border: 2px solid rgba(255,255,255,0.1); border-radius: 10px; margin-bottom: 20px; padding: 15px; display: flex; justify-content: space-around; align-items: center; box-shadow: 0 8px 16px rgba(0,0,0,0.8); border-top: 4px solid #ffd700;"><div style="text-align: center;"><div style="color: #aaa; font-size: 0.8em; text-transform: uppercase; letter-spacing: 1px;">Valor del once</div><div style="color: #ffd700; font-size: 1.5em; font-weight: 900;">{formato_euro(best_value)}</div>{_html_variacion(var_diaria_xi, size="0.75em")}</div><div style="text-align: center;"><div style="color: #aaa; font-size: 0.8em; text-transform: uppercase; letter-spacing: 1px;" title="Puesto en la liga por lo que se espera que puntúe su once">Valoración</div><div style="font-size: 1.5em; text-shadow: 0 0 5px gold;">{estrellas_html}</div><div style="color:#888; font-size:0.7em;">{f"{puesto_liga}º de {len(resumen_liga)} de la liga" if puesto_liga else ""}</div></div><div style="text-align: center;"><div style="color: #aaa; font-size: 0.8em; text-transform: uppercase; letter-spacing: 1px;">Alineación</div><div style="color: white; font-size: 1.5em; font-weight: 900;">{best_form}</div></div></div><div style="background: repeating-linear-gradient(0deg, rgba(55,126,34,0.9), rgba(55,126,34,0.9) 40px, rgba(50,117,30,0.9) 40px, rgba(50,117,30,0.9) 80px); border: 3px solid rgba(255,255,255,0.2); border-radius: 8px; position: relative; padding: 35px 10px 10px 10px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); backdrop-filter: blur(2px);"><div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 130px; height: 130px; border: 2px solid rgba(255,255,255,0.4); border-radius: 50%; z-index: 1;"></div><div style="position: absolute; top: 50%; left: 0; width: 100%; border-top: 2px solid rgba(255,255,255,0.4); z-index: 1;"></div><div style="position: absolute; top: 0; left: 25%; width: 50%; height: 15%; border: 2px solid rgba(255,255,255,0.4); border-top: none; z-index: 1;"></div><div style="position: absolute; bottom: 0; left: 25%; width: 50%; height: 15%; border: 2px solid rgba(255,255,255,0.4); border-bottom: none; z-index: 1;"></div>{pintar_linea(best_xi["DEL"], req_f, "DEL")}{pintar_linea(best_xi["MED"], req_m, "MED")}{pintar_linea(best_xi["DEF"], req_d, "DEF")}{pintar_linea(best_xi["POR"], 1, "POR")}</div>'
            st.markdown(html_centro, unsafe_allow_html=True)

            # Cuatro tarjetas, una por línea. El mejor de toda la plantilla ya no
            # sale repetido en una quinta: su tarjeta va en dorado y lo dice.
            tarjetas_top_html = ""
            for nombre_linea, p_data, p_type in mejores_linea:
                if p_data is None:
                    continue
                es_mvp = mvp_all is not None and p_data is mvp_all
                color_borde = "#ffd700" if es_mvp else "#87cefa"
                etiqueta = (f"Mejor jugador · {nombre_linea}" if es_mvp else f"Mejor {nombre_linea.lower()}")
                c_html = generar_carta_html(p_data, p_type)
                tarjetas_top_html += (
                    f'<div style="flex: 0 0 auto; background: linear-gradient(145deg, rgba(20,20,30,0.9), '
                    f'rgba(10,10,15,0.95)); border: {"2px" if es_mvp else "1px"} solid {color_borde}; '
                    f'border-radius: 12px; padding: 14px 10px; text-align: center; '
                    f'box-shadow: 0 8px 16px rgba(0,0,0,0.5){", 0 0 18px rgba(255,215,0,0.25)" if es_mvp else ""};">'
                    f'<div style="color: {color_borde}; font-weight: 800; font-size: 0.72em; letter-spacing: 1px; '
                    f'margin-bottom: 12px; text-transform: uppercase; white-space: nowrap;">'
                    f'{"👑 " if es_mvp else ""}{etiqueta}</div>'
                    f'<div style="display: flex; justify-content: center;">{c_html}</div></div>')
            html_top_posiciones = (f'<div style="display: flex; flex-wrap: wrap; justify-content: center; '
                                   f'gap: 16px; margin-top: 22px;">{tarjetas_top_html}</div>')
            st.markdown(html_top_posiciones, unsafe_allow_html=True)

        with col_banquillo:
            banquillo_html = ""
            if len(banquillo_df) > 0:
                for _, p in banquillo_df.iterrows():
                    pos_main = str(p['Posición']).split('/')[0].strip()
                    if pos_main == 'Portero': t = 'POR'
                    elif pos_main == 'Defensa': t = 'DEF'
                    elif pos_main == 'Centrocampista': t = 'MED'
                    else: t = 'DEL'
                    banquillo_html += f'<div>{generar_carta_html(p, t, is_empty=False)}</div>'
            else:
                banquillo_html = '<div style="grid-column: 1 / -1; color: #bbb; font-style: italic; margin-top: 10px; text-align: center;">Sin jugadores de reserva disponibles.</div>'

            html_valor_banquillo = f'<div style="text-align: center; margin-bottom: 15px;"><div style="color: #222; font-size: 1.3em; font-weight: 900; text-shadow: 1px 1px 0px rgba(255,255,255,0.6);">{formato_euro(valor_suplente)}</div>{_html_variacion(var_diaria_banquillo, size="0.85em", chip=True)}</div>'
            html_banquillo = f'<div style="background: linear-gradient(to bottom, rgba(159,168,179,0.9) 0%, rgba(213,217,220,0.9) 10%, rgba(123,132,140,0.9) 100%); border: 4px solid rgba(90,98,104,0.8); border-radius: 12px; padding: 15px; box-shadow: inset 0 20px 30px rgba(0,0,0,0.3), 0 10px 20px rgba(0,0,0,0.5); height: 100%;"><h4 style="text-align: center; color: #222; margin-top: 0; margin-bottom: 10px; font-weight: 900; text-transform: uppercase; letter-spacing: 1px; text-shadow: 1px 1px 0px rgba(255,255,255,0.6); font-size: 0.95em;">Banquillo</h4>{html_valor_banquillo}<div style="background: rgba(17,17,17,0.8); border-radius: 10px; padding: 12px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; justify-items: center; box-shadow: inset 0 0 15px rgba(0,0,0,0.8);">{banquillo_html}</div></div>'
            st.markdown(html_banquillo, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

if _pagina == "Rivales":
    ui_rival()


# ==========================================
# ⚔️ PESTAÑA: CARA A CARA (OPTIMIZADA)
# ==========================================
# ==========================================
# ⚖️ PESTAÑA: COMPARAR
# ==========================================
# Dos jugadores, cara a cara, y solo su rendimiento.
#
# Hubo una versión con atajos, veredictos de alineación, de venta y de fichaje,
# calendario y dinero. Hacía de todo, y justo por eso no apetecía tocarla.
# Comparar es poner dos números al lado y ver quién gana: es lo único que hace.

COLOR_A, COLOR_B = '#38bdf8', '#fb923c'   # azul y naranja: se distinguen incluso con daltonismo
# La barra del que pierde (o empata) va en gris: con el color apagado, el
# naranja salía de un marrón sucio y el ganador no destacaba.
GRIS_PIERDE = 'rgba(255,255,255,0.16)'


@st.cache_data(show_spinner=False)
def _indice_comparar(huella=None):
    """{'Jugador · Equipo': índice en el mercado}, en orden alfabético.

    Con el equipo en la etiqueta no hay homónimos que confundir, y el orden no
    manda a los acentuados detrás de la Z."""
    mercado = db['mercado'].dropna(subset=['Jugador'])
    indice = {}
    for idx, jugador, equipo in zip(mercado.index, mercado['Jugador'], mercado['Equipo']):
        etiqueta = f"{str(jugador).strip()} · {str(equipo or '').strip()}"
        indice.setdefault(etiqueta, idx)
    return dict(sorted(indice.items(), key=lambda kv: _clave_alfabetica(kv[0])))


@st.cache_data(show_spinner=False)
def _historico_por_jugador(huella=None):
    """El histórico partido por jugador y ordenado por fecha, para no filtrar
    21.000 filas cada vez que se pinta una comparación."""
    hist = cargar_historico_completo(huella)
    if hist is None or hist.empty:
        return {}
    h = hist.dropna(subset=['Fecha', 'Jugador']).copy()
    h['Jugador'] = h['Jugador'].astype(str).str.strip()
    h['Equipo'] = h['Equipo'].astype(str).str.strip()
    h = h.sort_values('Fecha')
    columnas = ['Fecha', 'Equipo', 'Puntos', 'Media Puntos', 'Valor Actual (€)']
    return {nombre: grupo[columnas].reset_index(drop=True)
            for nombre, grupo in h.groupby('Jugador', sort=False)}


def _serie_historica(jugador, equipo):
    serie = _historico_por_jugador(_huella_excel(resolver_excel_path())).get(str(jugador).strip())
    if serie is None or serie.empty:
        return None
    # Dos jugadores distintos con el mismo nombre aparecen el mismo día: ahí sí
    # hay que separar por equipo. Uno traspasado aparece un día en cada club y
    # su historia es toda suya, así que se deja entera.
    if serie['Fecha'].duplicated().any():
        serie = serie[serie['Equipo'] == str(equipo).strip()]
    return serie if not serie.empty else None


def _partidos_jugados(puntos, media):
    """Partidos jugados que se deducen de los puntos y la media de un día."""
    if media is None or pd.isna(media) or abs(float(media)) < 1e-9:
        return 0 if (puntos is None or pd.isna(puntos) or float(puntos) == 0) else None
    return int(round(float(puntos) / float(media)))


def forma_reciente(jugador, equipo, n=5):
    """Lo que hizo en los últimos n partidos de su equipo, del más antiguo al
    más reciente.

    Sale del histórico diario: lo que suma entre la víspera de cada partido y
    la víspera del siguiente, y si en ese tiempo le sube el número de partidos
    jugados (así se distingue un 0 jugando de no haber salido). Comprobado
    contra el total de Biwenger: los partidos de Yamal suman sus 84 puntos.

    Cada partido: {'jornada', 'rival', 'es_casa', 'pts', 'jugo'}. 'pts' es None
    si el histórico no alcanza para saberlo."""
    cal = df_cal_global
    if cal is None or cal.empty or not equipo:
        return []
    serie = _serie_historica(jugador, equipo)
    if serie is None:
        return []
    del_equipo = cal[(cal['Local'] == equipo) | (cal['Visitante'] == equipo)]
    jugados = del_equipo[del_equipo['Estado'] == 'Finalizado'].dropna(subset=['Fecha']).sort_values('Fecha')
    if jugados.empty:
        return []
    fechas_equipo = sorted(del_equipo['Fecha'].dropna().unique())
    fechas = serie['Fecha'].values
    puntos = pd.to_numeric(serie['Puntos'], errors='coerce').values
    medias = pd.to_numeric(serie['Media Puntos'], errors='coerce').values

    resultado = []
    for _, partido in jugados.tail(n).iterrows():
        dia = partido['Fecha']
        es_casa = partido['Local'] == equipo
        entrada = {'jornada': int(partido['Jornada']) if pd.notna(partido['Jornada']) else None,
                   'rival': partido['Visitante'] if es_casa else partido['Local'],
                   'es_casa': bool(es_casa), 'pts': None, 'jugo': None}
        siguientes = [f for f in fechas_equipo if f > np.datetime64(dia)]
        limite = siguientes[0] if siguientes else None
        # Antes: la última foto anterior al día del partido. Después: la última
        # antes del siguiente partido, que ya recoge los puntos (y cualquier
        # rectificación) aunque la importación de ese día fuera por la mañana.
        antes = np.where(fechas < np.datetime64(dia))[0]
        despues = np.where((fechas >= np.datetime64(dia))
                           & ((fechas < limite) if limite is not None else True))[0]
        if len(antes) and len(despues):
            i, j = antes[-1], despues[-1]
            if not (pd.isna(puntos[i]) or pd.isna(puntos[j])):
                entrada['pts'] = float(puntos[j] - puntos[i])
                pj_antes = _partidos_jugados(puntos[i], medias[i])
                pj_despues = _partidos_jugados(puntos[j], medias[j])
                if pj_antes is not None and pj_despues is not None:
                    entrada['jugo'] = pj_despues > pj_antes
                else:
                    entrada['jugo'] = entrada['pts'] != 0
        resultado.append(entrada)
    return resultado


def _partidos_del_equipo(equipo):
    """Cuántos partidos ha terminado ya su equipo: para decir "6 de 7"."""
    cal = df_cal_global
    if cal is None or cal.empty or not equipo:
        return None
    del_equipo = cal[((cal['Local'] == equipo) | (cal['Visitante'] == equipo))
                     & (cal['Estado'] == 'Finalizado')]
    return len(del_equipo) or None


def _eventos_del_jugador(nombre, equipo):
    """{jornada: (goles, asistencias)} de la hoja Eventos_Jornada que escribe el bot."""
    eventos = db.get('eventos')
    if eventos is None or eventos.empty or 'Jugador' not in eventos.columns:
        return {}
    suyos = eventos[eventos['Jugador'].astype(str).str.strip() == nombre]
    if 'Equipo' in suyos.columns and (suyos['Equipo'].astype(str).str.strip() == equipo).any():
        suyos = suyos[suyos['Equipo'].astype(str).str.strip() == equipo]
    return {int(j): (int(_a_float(g, 0.0) or 0), int(_a_float(a, 0.0) or 0))
            for j, g, a in zip(suyos['Jornada'], suyos.get('Goles', 0), suyos.get('Asistencias', 0))
            if pd.notna(j)}


def _iconos_eventos(partido):
    """⚽ por gol y 🅰️ por asistencia, para ver si sus puntos vienen de ahí."""
    goles, asist = partido.get('goles', 0) or 0, partido.get('asist', 0) or 0
    if not goles and not asist:
        return ""
    trozos = []
    if goles:
        trozos.append("⚽" * goles if goles <= 3 else f"⚽×{goles}")
    if asist:
        trozos.append("🅰️" * asist if asist <= 3 else f"🅰️×{asist}")
    return f"<div class='h2h-eventos'>{' '.join(trozos)}</div>"


def _rendimiento(fila):
    """Los números de rendimiento de un jugador, y su temporada partido a partido."""
    nombre = str(fila['Jugador']).strip()
    equipo = str(fila.get('Equipo') or '').strip()
    pj = int(_a_float(fila.get('PJ'), 0.0) or 0)
    pj_casa = int(_a_float(fila.get('PJ Casa'), 0.0) or 0)
    pj_fuera = int(_a_float(fila.get('PJ Fuera'), 0.0) or 0)
    temporada = sorted(forma_reciente(nombre, equipo, n=99),
                       key=lambda p: (p['jornada'] is None, p['jornada'] or 0))
    eventos = _eventos_del_jugador(nombre, equipo)
    for partido in temporada:
        goles, asist = eventos.get(partido['jornada'], (0, 0))
        partido['goles'], partido['asist'] = goles, asist
    jugados = [p['pts'] for p in temporada if p['jugo'] and p['pts'] is not None]
    return {
        'nombre': nombre, 'equipo': equipo, 'fila': fila,
        'pos': _pos_principal(fila.get('Posición')),
        'puntos': _a_float(fila.get('Puntos'), 0.0) or 0.0,
        'media': _a_float(fila.get('Media Puntos'), 0.0) or 0.0,
        'pj': pj, 'partidos_equipo': _partidos_del_equipo(equipo),
        # Sin partidos en casa (o fuera) no hay media que valga: un 0 diría
        # "es malo en casa" cuando lo único que pasa es que no ha jugado ahí.
        'media_casa': (_a_float(fila.get('Media Puntos Casa'), 0.0) or 0.0) if pj_casa else None,
        'media_fuera': (_a_float(fila.get('Media Puntos Fuera'), 0.0) or 0.0) if pj_fuera else None,
        'goles': int(_a_float(fila.get('Goles'), 0.0) or 0),
        'asist': int(_a_float(fila.get('Asistencias'), 0.0) or 0),
        # Forma: la media de sus tres últimos partidos jugados. Regularidad: la
        # parte de sus partidos con 6 o más, el verde de Biwenger para arriba.
        'forma': (sum(jugados[-3:]) / len(jugados[-3:])) if jugados else None,
        'regularidad': (sum(1 for p in jugados if p >= 6) / len(jugados)) if jugados else None,
        'temporada': temporada,
        'proximos': (tramo_de_calendario(equipo, 3) or {}).get('partidos', []),
    }


def _texto_entero(valor):
    """Un entero para leer, con el signo menos tipográfico ("−1", no "-1").

    OJO con el nombre: se llamó _entero y pisaba a la _entero(valor, defecto)
    de arriba, la que convierte celdas del Excel en números. Python se queda
    con la última definición, así que el reparto casa/fuera del bot recibía
    esta y reventaba ("takes 1 positional argument but 2 were given")."""
    return f"{valor:.0f}".replace('-', '−')


def _filas_cara_a_cara(a, b):
    """(rótulo, valor A, valor B, texto A, texto B) de cada apartado.
    El valor decide quién gana; el texto es lo que se lee."""
    def jugados_de(f):
        return (f['pj'] / f['partidos_equipo']) if f['partidos_equipo'] else float(f['pj'])

    def texto_jugados(f):
        return f"{f['pj']} de {f['partidos_equipo']}" if f['partidos_equipo'] else str(f['pj'])

    def media_de(clave):
        return lambda f: f[clave]

    def texto_media(clave):
        return lambda f: formato_puntos(f[clave]) if f[clave] is not None else "—"

    filas = [
        ("Puntos", lambda f: f['puntos'], lambda f: _texto_entero(f['puntos'])),
        ("Media por partido", media_de('media'), texto_media('media')),
        ("Partidos jugados", jugados_de, texto_jugados),
        ("Media en casa", media_de('media_casa'), texto_media('media_casa')),
        ("Media fuera", media_de('media_fuera'), texto_media('media_fuera')),
        ("Forma (últimos 3)", media_de('forma'), texto_media('forma')),
        ("Regularidad (6 o más)", lambda f: f['regularidad'],
         lambda f: f"{f['regularidad'] * 100:.0f}%" if f['regularidad'] is not None else "—"),
        ("Goles + asistencias", lambda f: f['goles'] + f['asist'],
         lambda f: f"{f['goles'] + f['asist']} <span class='h2h-detalle'>({f['goles']} + {f['asist']})</span>"),
    ]
    return [(rotulo, valor(a), valor(b), texto(a), texto(b)) for rotulo, valor, texto in filas]


CSS_CARA_A_CARA = """
<style>
.h2h { max-width:980px; margin:8px auto 0 auto; }
.h2h-cabecera { display:grid; grid-template-columns:1fr 190px 1fr; align-items:end; margin-bottom:26px; }
.h2h-jugador { display:flex; flex-direction:column; align-items:center; }
.h2h-raya { width:46px; height:3px; border-radius:3px; margin:12px 0 7px 0; }
.h2h-nombre { font-family:'Fraunces', Georgia, serif; font-size:1.2rem; color:#f2f4f8; text-align:center; }
.h2h-sub { color:#8b93a7; font-size:0.78rem; margin-top:2px; }
.h2h-marcador { text-align:center; padding-bottom:26px; }
.h2h-marcador-num { font-family:'Fraunces', Georgia, serif; font-size:2.6rem; font-weight:600; line-height:1; }
.h2h-marcador-guion { color:#4b5363; margin:0 10px; font-size:2rem; }
.h2h-marcador-txt { color:#8b93a7; font-size:0.72rem; letter-spacing:0.1em; text-transform:uppercase; margin-top:8px; }
.h2h-nota { text-align:center; color:#8b93a7; font-size:0.8rem; margin:-12px 0 20px 0; }
.h2h-fila { display:grid; grid-template-columns:78px 1fr 190px 1fr 78px; align-items:center;
            gap:14px; padding:9px 0; }
.h2h-fila + .h2h-fila { border-top:1px solid rgba(255,255,255,0.05); }
.h2h-val { font-size:1.05rem; color:#c3cbd9; font-variant-numeric:tabular-nums; }
.h2h-val.izq { text-align:right; } .h2h-val.der { text-align:left; }
.h2h-val.gana { font-weight:700; }
.h2h-pista { height:8px; border-radius:5px; background:rgba(255,255,255,0.05); display:flex; }
.h2h-pista.izq { justify-content:flex-end; }
.h2h-pista span { display:block; height:100%; border-radius:5px; }
.h2h-rotulo { text-align:center; color:#aeb6c4; font-size:0.84rem; }
.h2h-detalle { color:#8b93a7; font-size:0.78rem; font-weight:400; }
.h2h-seccion { display:flex; align-items:center; justify-content:center; gap:14px; color:#f2f4f8; font-size:0.92rem; font-weight:800; letter-spacing:0.16em; text-transform:uppercase; text-align:center; margin:46px 0 16px 0; }
.h2h-seccion::before { content:''; width:34px; height:2px; border-radius:2px; background:linear-gradient(90deg, transparent, #e7c565); }
.h2h-seccion::after { content:''; width:34px; height:2px; border-radius:2px; background:linear-gradient(90deg, #e7c565, transparent); }
.h2h-leyenda { color:#8b93a7; font-size:0.86rem; margin-bottom:18px; text-align:center; }
/* "safe center": centrado mientras quepa; si hay más jornadas que ancho, se
   alinea a la izquierda y se desplaza, en vez de cortar las primeras. */
.h2h-jmarco { overflow-x:auto; padding-bottom:6px; }
.h2h-jinterior { width:max-content; margin:0 auto; display:flex; flex-direction:column; gap:14px; }
.h2h-carril { background:rgba(255,255,255,0.022); border:1px solid rgba(255,255,255,0.07);
              border-radius:12px; padding:12px 18px 10px 18px; }
.h2h-carril-cab { display:flex; align-items:center; gap:10px; padding-bottom:8px; margin-bottom:6px;
                  border-bottom:1px solid rgba(255,255,255,0.06); }
.h2h-carril-marca { width:4px; height:18px; border-radius:2px; }
.h2h-carril-nombre { font-family:'Fraunces', Georgia, serif; font-size:1.02rem; font-weight:600; color:#f2f4f8; }
.h2h-carril-equipo { color:#8b93a7; font-size:0.78rem; }
.h2h-carril-dato { margin-left:auto; color:#aeb6c4; font-size:0.78rem; font-variant-numeric:tabular-nums; }
.h2h-jornadas { display:flex; gap:12px; }
.h2h-j { display:flex; flex-direction:column; align-items:center; min-width:50px; }
/* Dos carriles iguales, uno encima del otro, con las barras siempre hacia
   arriba y su propio eje de jornadas debajo. */
.h2h-j-carril { height:140px; width:100%; display:flex; flex-direction:column; align-items:center;
                justify-content:flex-end; }

.h2h-j-barra { width:30px; border-radius:5px 5px 2px 2px; }
.h2h-eventos { font-size:0.78rem; line-height:1; margin:2px 0; letter-spacing:1px; white-space:nowrap; }
.h2h-j-num { font-size:1.15rem; color:#dfe5ee; margin:4px 0; font-weight:800; line-height:1.1;
             font-variant-numeric:tabular-nums; }
.h2h-prox { width:46px; padding:6px 0 5px 0; border:1px dashed; border-radius:8px; display:flex;
            flex-direction:column; align-items:center; gap:2px; margin:2px 0; }
.h2h-prox-lugar { font-size:0.66rem; color:#c3cbd9; font-weight:600; }
.h2h-prox-nivel { font-size:0.62rem; font-weight:600; }
.h2h-j-eje-prox { color:#c3cbd9; font-weight:600; }
.h2h-j-eje { font-size:0.8rem; color:#8b93a7; padding:6px 0; border-top:1px solid rgba(255,255,255,0.12);
             border-bottom:1px solid rgba(255,255,255,0.12); width:100%; text-align:center; }
</style>
"""


def _nivel_dificultad(valor):
    c1, c2, c3, c4 = cortes_color_dificultad()
    if valor < c2:
        return "fácil"
    return "igualado" if valor < c3 else "difícil"


# 🎨 Los colores de los puntos de cada partido, los mismos que usa Biwenger:
# rojo si resta, gris el cero, naranja de 1 a 5, verde de 6 a 9 y azul de 10
# en adelante.
COLOR_PUNTOS_CERO = '#9ca3af'
COLORES_PUNTOS_BIWENGER = (
    (0, '#e53935', 'Negativo'),
    (6, '#ff9800', '1 a 5'),
    (10, '#16a34a', '6 a 9'),
    (None, '#0ea5e9', '10 o más'),
)


def color_puntos_biwenger(pts):
    if pts is not None and round(float(pts)) == 0:
        return COLOR_PUNTOS_CERO
    for tope, color, _ in COLORES_PUNTOS_BIWENGER:
        if tope is None or pts < tope:
            return color
    return COLORES_PUNTOS_BIWENGER[-1][1]


def _columna_jornada(jornada, pa, pb, tope, nombre_a='A', nombre_b='B', prox_a=None, prox_b=None):
    """Una jornada: A en el carril de arriba y B en el de abajo, los dos con
    las barras hacia arriba y del color de Biwenger según los puntos.

    Si ya se jugó, la barra con sus puntos. Si está entre sus tres próximos
    partidos, una ficha con el escudo del rival, casa o fuera y lo difícil que
    es, del color de la dificultad. Cuando ese partido se juegue, la misma
    columna pasa sola a enseñar los puntos."""
    def media_columna(partido, proximo, color, arriba):
        if partido is None and proximo is not None:
            tono = color_dificultad(proximo['dificultad'])
            return (f"<div class='h2h-prox' style='border-color:{tono}; background:{tono}1f;'>"
                    f"{escudo_html(proximo['rival'], 26)}"
                    f"<div class='h2h-prox-lugar'>{'Casa' if proximo['es_casa'] else 'Fuera'}</div>"
                    f"<div class='h2h-prox-nivel' style='color:{tono};'>"
                    f"{_nivel_dificultad(proximo['dificultad'])}</div></div>")
        if partido is None or partido['pts'] is None:
            barra, numero = "", "<div class='h2h-j-num' style='color:#4b5363;'>·</div>"
        elif not partido['jugo']:
            barra, numero = "", "<div class='h2h-j-num' style='color:#6f7789;'>–</div>"
        else:
            pts = partido['pts']
            alto = max(4.0, abs(pts) / tope * 96) if pts else 4.0
            tono = color_puntos_biwenger(pts)
            barra = f"<div class='h2h-j-barra' style='height:{alto:.0f}px; background:{tono};'></div>"
            numero = f"<div class='h2h-j-num' style='color:{tono};'>{_texto_entero(pts)}</div>"
            return _iconos_eventos(partido) + numero + barra
        return numero + barra

    def ayuda(partido, proximo, quien):
        if partido is None and proximo is not None:
            lugar = 'en casa' if proximo['es_casa'] else 'fuera'
            return (f"{quien}: contra {proximo['rival']} {lugar}, "
                    f"{_texto_dificultad(proximo['dificultad'])}")
        if partido is None or partido['pts'] is None:
            return f"{quien}: sin dato"
        if not partido['jugo']:
            return f"{quien}: no jugó"
        lugar = 'casa' if partido['es_casa'] else 'fuera'
        extra = "".join(f", {n} {r}{'es' if n > 1 and r == 'gol' else ('s' if n > 1 else '')}"
                        for n, r in ((partido.get('goles', 0), 'gol'), (partido.get('asist', 0), 'asistencia')) if n)
        return f"{quien}: {_texto_entero(partido['pts'])} ({partido['rival']}, {lugar}{extra})"

    # Un solo carril: pa/prox_a son los del jugador de este carril.
    por_jugar = pa is None
    titulo = f"J{jornada} · {ayuda(pa, prox_a, nombre_a)}".replace("'", "&#39;")
    eje = f"<div class='h2h-j-eje{' h2h-j-eje-prox' if por_jugar else ''}'>J{jornada}</div>"
    return (f"<div class='h2h-j' title='{titulo}'>"
            f"<div class='h2h-j-carril'>{media_columna(pa, prox_a, COLOR_A, True)}</div>{eje}</div>")


def _carril_jornadas(f, color, jornadas, por_jornada, proximos, tope):
    """Un carril del jornada a jornada: cabecera con el jugador y sus barras."""
    jugados = [p for p in por_jornada.values() if p['jugo'] and p['pts'] is not None]
    resumen = (f"{len(jugados)} partido{'s' if len(jugados) != 1 else ''} · "
               f"{_texto_entero(sum(p['pts'] for p in jugados))} pts") if jugados else "sin partidos"
    columnas = "".join(_columna_jornada(j, por_jornada.get(j), None, tope, f['nombre'], None,
                                        proximos.get(j), None) for j in jornadas)
    return (f"<div class='h2h-carril'><div class='h2h-carril-cab'>"
            f"<span class='h2h-carril-marca' style='background:{color};'></span>"
            f"<span class='h2h-carril-nombre'>{f['nombre']}</span>"
            f"<span class='h2h-carril-equipo'>{f['equipo']}</span>"
            f"<span class='h2h-carril-dato'>{resumen}</span></div>"
            f"<div class='h2h-jornadas'>{columnas}</div></div>")


def _texto_dificultad(valor):
    if valor is None or pd.isna(valor):
        return "sin dato"
    c1, c2, c3, c4 = cortes_color_dificultad()
    if valor < c1: return "muy asequible"
    if valor < c2: return "asequible"
    if valor < c3: return "igualado"
    if valor < c4: return "difícil"
    return "muy difícil"


def _html_cara_a_cara(a, b):
    filas = _filas_cara_a_cara(a, b)
    gana_a = sum(1 for _, va, vb, _, _ in filas if va is not None and vb is not None and va > vb)
    gana_b = sum(1 for _, va, vb, _, _ in filas if va is not None and vb is not None and vb > va)

    def jugador(f, color):
        carta = generar_carta_html(f['fila'], pos_type={'Portero': 'POR', 'Defensa': 'DEF',
                                                         'Centrocampista': 'MED'}.get(f['pos'], 'DEL'),
                                   mostrar_proximo_rival=False)
        return (f"<div class='h2h-jugador'>{carta}<div class='h2h-raya' style='background:{color};'></div>"
                f"<div class='h2h-nombre'>{f['nombre']}</div>"
                f"<div class='h2h-sub'>{f['equipo']} · {f['pos'].lower()}</div></div>")

    html = [CSS_CARA_A_CARA, "<div class='h2h'>",
            "<div class='h2h-cabecera'>", jugador(a, COLOR_A),
            f"<div class='h2h-marcador'><span class='h2h-marcador-num' style='color:{COLOR_A};'>{gana_a}</span>"
            f"<span class='h2h-marcador-guion'>–</span>"
            f"<span class='h2h-marcador-num' style='color:{COLOR_B};'>{gana_b}</span>"
            f"<div class='h2h-marcador-txt'>apartados ganados</div></div>",
            jugador(b, COLOR_B), "</div>"]

    for rotulo, va, vb, ta, tb in filas:
        comparable = va is not None and vb is not None
        tope = max(abs(va or 0), abs(vb or 0)) or 1.0
        ancho_a = (max(va, 0) / tope * 100) if va is not None else 0
        ancho_b = (max(vb, 0) / tope * 100) if vb is not None else 0
        a_gana = comparable and va > vb
        b_gana = comparable and vb > va
        html.append(
            "<div class='h2h-fila'>"
            f"<div class='h2h-val izq{' gana' if a_gana else ''}' style='{f'color:{COLOR_A};' if a_gana else ''}'>{ta}</div>"
            f"<div class='h2h-pista izq'><span style='width:{ancho_a:.0f}%; "
            f"background:{COLOR_A if a_gana else GRIS_PIERDE};'></span></div>"
            f"<div class='h2h-rotulo'>{rotulo}</div>"
            f"<div class='h2h-pista'><span style='width:{ancho_b:.0f}%; "
            f"background:{COLOR_B if b_gana else GRIS_PIERDE};'></span></div>"
            f"<div class='h2h-val der{' gana' if b_gana else ''}' style='{f'color:{COLOR_B};' if b_gana else ''}'>{tb}</div>"
            "</div>")

    # Jornada a jornada: la media esconde si los puntos llegan de uno en uno o
    # de golpe en dos partidos, y eso solo se ve partido a partido.
    por_jornada_a = {p['jornada']: p for p in a['temporada'] if p['jornada'] is not None}
    por_jornada_b = {p['jornada']: p for p in b['temporada'] if p['jornada'] is not None}
    proximos_a = {p['jornada']: p for p in a['proximos'] if p['jornada'] is not None}
    proximos_b = {p['jornada']: p for p in b['proximos'] if p['jornada'] is not None}
    jornadas = sorted(set(por_jornada_a) | set(por_jornada_b) | set(proximos_a) | set(proximos_b))
    if jornadas:
        todos = [p['pts'] for p in list(por_jornada_a.values()) + list(por_jornada_b.values())
                 if p['jugo'] and p['pts'] is not None]
        tope = max([abs(x) for x in todos] + [1.0])
        html.append("<div class='h2h-seccion'>Rendimiento por jornada</div><div class='h2h-jmarco'>"
                    "<div class='h2h-jinterior'>"
                    + _carril_jornadas(a, COLOR_A, jornadas, por_jornada_a, proximos_a, tope)
                    + _carril_jornadas(b, COLOR_B, jornadas, por_jornada_b, proximos_b, tope)
                    + "</div></div>")
    html.append("</div>")
    return "".join(html)


def _aplicar_comparacion():
    """El botón Comparar: lo elegido pasa a ser lo que se compara. Elegir y
    comparar van por separado, como pediste, para que elegir no dispare nada."""
    st.session_state['comp_par'] = (st.session_state.get('comp_a'), st.session_state.get('comp_b'))


@st.fragment
def ui_comparador():
    indice = _indice_comparar(_huella_excel(resolver_excel_path()))
    if not indice:
        st.info("No hay jugadores en el mercado para comparar.")
        return
    # Un jugador que ya no está en el mercado (renombrado, fuera del juego) no
    # puede quedarse elegido: el desplegable no admite valores que no ofrece.
    for clave in ('comp_a', 'comp_b'):
        if st.session_state.get(clave) is not None and st.session_state[clave] not in indice:
            del st.session_state[clave]

    opciones = list(indice.keys())
    # El botón va EN MEDIO de los dos buscadores: se lee como "este contra este".
    try:
        c_a, c_boton, c_b = st.columns([3, 1.1, 3], vertical_alignment="bottom")
    except TypeError:          # Streamlit antiguo: sin alineación vertical de columnas
        c_a, c_boton, c_b = st.columns([3, 1.1, 3])
    # Sin rótulo encima: el buscador ya dice "Elige un jugador" y el botón de
    # en medio deja claro que es uno contra otro. (El rótulo sigue existiendo,
    # oculto, para los lectores de pantalla.)
    elegido_a = c_a.selectbox("Jugador", opciones, index=None, key="comp_a",
                              placeholder="Elige un jugador", label_visibility="collapsed")
    elegido_b = c_b.selectbox("Contra", opciones, index=None, key="comp_b",
                              placeholder="Elige otro", label_visibility="collapsed")
    c_boton.button("Comparar", key="comp_boton", type="primary", use_container_width=True,
                   on_click=_aplicar_comparacion)

    par = st.session_state.get('comp_par')
    if par and any(e is not None and e not in indice for e in par):
        par = None
    pendiente = bool(elegido_a and elegido_b) and tuple(par or ()) != (elegido_a, elegido_b)
    if pendiente:
        st.caption("Pulsa Comparar para verlos cara a cara.")
    if not par or None in par:
        if not pendiente:
            st.caption("Elige dos jugadores y pulsa Comparar.")
        return
    if par[0] == par[1]:
        st.caption("Es el mismo jugador dos veces: elige otro.")
        return

    a = _rendimiento(db['mercado'].loc[indice[par[0]]])
    b = _rendimiento(db['mercado'].loc[indice[par[1]]])
    st.markdown(_html_cara_a_cara(a, b), unsafe_allow_html=True)


# ==========================================
# 🎛️ PESTAÑA: RESUMEN (inicio)
# ==========================================
CSS_RESUMEN = """
<style>
.rs-titulo { display:flex; align-items:center; justify-content:center; gap:14px; color:#f2f4f8; font-size:0.92rem;
             font-weight:800; letter-spacing:0.16em; text-transform:uppercase; text-align:center; margin:34px 0 18px 0; }
.rs-titulo::before { content:''; width:34px; height:2px; border-radius:2px; background:linear-gradient(90deg, transparent, #e7c565); }
.rs-titulo::after { content:''; width:34px; height:2px; border-radius:2px; background:linear-gradient(90deg, #e7c565, transparent); }
.rs-num { font-family:'Inter', sans-serif !important; font-variant-numeric:tabular-nums; }

/* Cabecera: quién eres, dónde estás y tus cifras */
.rs-heroe { position:relative; overflow:hidden; border-radius:20px; padding:26px 30px 22px;
            background:radial-gradient(120% 140% at 0% 0%, color-mix(in srgb, var(--c) 16%, transparent), transparent 55%),
                       linear-gradient(180deg, #1c202a, #14171e);
            border:1px solid rgba(255,255,255,0.08); box-shadow:0 14px 34px rgba(0,0,0,0.35); margin-top:4px; }
.rs-heroe::before { content:''; position:absolute; top:0; left:0; right:0; height:4px; background:var(--c); }
.rs-arriba { display:flex; align-items:center; justify-content:space-between; gap:24px; flex-wrap:wrap; }
.rs-yo { display:flex; align-items:center; gap:18px; min-width:0; }
.rs-puesto { width:66px; height:66px; border-radius:50%; flex:none; display:flex; align-items:center; justify-content:center;
             background:var(--c); color:#0b0e14; font-size:1.7rem; font-weight:900;
             box-shadow:0 0 0 5px color-mix(in srgb, var(--c) 22%, transparent); font-family:'Inter', sans-serif !important; }
.rs-nombre b { display:block; color:#fff; font-size:2rem; font-weight:900; line-height:1.05; letter-spacing:-0.01em;
               font-family:'Inter', sans-serif !important; }
.rs-nombre span { display:block; color:#aab3c2; font-size:0.86rem; margin-top:5px; }
.rs-nombre span b { display:inline; font-size:inherit; color:#f4f6fa; font-weight:700; letter-spacing:0; }
.rs-rangos { display:flex; gap:10px; flex-wrap:wrap; }
.rs-rango { display:flex; flex-direction:column; align-items:center; gap:3px; min-width:118px; padding:9px 14px;
            border-radius:12px; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); }
.rs-rango .r { color:#8b93a7; font-size:0.58rem; font-weight:700; letter-spacing:0.15em; text-transform:uppercase; white-space:nowrap; }
.rs-rango .v { font-size:1.25rem; font-weight:800; line-height:1.1; font-family:'Inter', sans-serif !important; }
.rs-rango .v small { color:#8b93a7; font-size:0.7rem; font-weight:600; margin-left:3px; }
.rs-kpis { display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); margin-top:22px; padding-top:20px;
           border-top:1px solid rgba(255,255,255,0.07); }
@media (max-width: 1100px) { .rs-kpis { grid-template-columns:repeat(3, minmax(0, 1fr)); row-gap:18px; } }
.rs-kpi { container-type:inline-size; display:flex; flex-direction:column; align-items:center; justify-content:flex-start;
          gap:7px; padding:0 10px; text-align:center; min-width:0; }
.rs-kpi + .rs-kpi { border-left:1px solid rgba(255,255,255,0.07); }
.rs-kpi .r { color:#8b93a7; font-size:0.62rem; font-weight:700; letter-spacing:0.16em; text-transform:uppercase; white-space:nowrap; }
.rs-kpi .v { color:#f4f6fa; font-size:1.7rem; font-weight:800; line-height:1.05; white-space:nowrap;
             font-family:'Inter', sans-serif !important; font-variant-numeric:tabular-nums; letter-spacing:-0.01em; }
@container (max-width: 250px) { .rs-kpi .v { font-size:1.4rem; } }
@container (max-width: 205px) { .rs-kpi .v { font-size:1.15rem; } }
.rs-kpi .v small { color:#8b93a7; font-size:0.75rem; font-weight:600; margin-left:4px; }
.rs-kpi .v.neg { color:#f87171; }
.rs-delta { display:inline-flex; align-items:center; gap:4px; border-radius:999px; padding:2px 10px; font-size:0.74rem;
            font-weight:700; white-space:nowrap; font-family:'Inter', sans-serif !important; }
.rs-delta.sube { color:#4ade80; background:rgba(74,222,128,0.12); }
.rs-delta.baja { color:#f87171; background:rgba(248,113,113,0.12); }
.rs-delta.igual { color:#9ca3af; background:rgba(255,255,255,0.06); }
.rs-lineas { display:flex; gap:4px; flex-wrap:wrap; justify-content:center; }
.rs-lineas span { background:rgba(255,255,255,0.06); border-radius:999px; padding:2px 8px; font-size:0.66rem; color:#aab3c2; }
.rs-lineas span b { color:#f4f6fa; margin-left:3px; font-family:'Inter', sans-serif !important; }

/* Avisos: tarjetas iguales, centradas */
.rs-avisos { display:flex; flex-wrap:wrap; align-items:stretch; justify-content:center; gap:14px; }
.rs-avisos > .rs-aviso { flex:0 1 280px; min-width:215px; box-sizing:border-box; }
.rs-aviso { position:relative; overflow:hidden; display:flex; flex-direction:column; align-items:center; gap:8px;
            padding:18px 16px 16px; border-radius:16px; text-align:center;
            background:linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.012));
            border:1px solid rgba(255,255,255,0.08); }
.rs-aviso::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:var(--c); }
.rs-aviso.rojo { --c:#f87171; background:linear-gradient(180deg, rgba(248,113,113,0.11), rgba(248,113,113,0.02));
                 border-color:rgba(248,113,113,0.28); }
.rs-aviso.naranja { --c:#fbbf24; background:linear-gradient(180deg, rgba(251,191,36,0.07), rgba(251,191,36,0.01));
                    border-color:rgba(251,191,36,0.2); }
.rs-aviso.azul { --c:#60a5fa; }
.rs-aviso.verde { --c:#4ade80; }
.rs-av-ico { width:40px; height:40px; border-radius:50%; display:flex; align-items:center; justify-content:center;
             font-size:1.2rem; background:color-mix(in srgb, var(--c) 14%, transparent);
             border:1px solid color-mix(in srgb, var(--c) 35%, transparent); }
.rs-av-tit { color:#c3cbd9; font-size:0.66rem; font-weight:800; letter-spacing:0.15em; text-transform:uppercase; line-height:1.3; }
.rs-av-dato { font-size:1.55rem; font-weight:800; line-height:1.1; white-space:nowrap; color:#f4f6fa;
              font-family:'Inter', sans-serif !important; font-variant-numeric:tabular-nums; }
.rs-aviso.rojo .rs-av-dato { color:#fca5a5; } .rs-aviso.naranja .rs-av-dato { color:#fcd34d; }
.rs-aviso.verde .rs-av-dato { color:#86efac; } .rs-aviso.azul .rs-av-dato { color:#93c5fd; }
.rs-av-nota { color:#8b93a7; font-size:0.74rem; line-height:1.35; }
.rs-av-filas { width:100%; display:flex; flex-direction:column; gap:6px; margin-top:4px; padding-top:10px;
               border-top:1px solid rgba(255,255,255,0.07); }
.rs-jug { display:flex; align-items:center; gap:9px; font-size:0.8rem; color:#e5e9f0; text-align:left; }
.rs-jug img, .rs-jug .ini { width:28px; height:28px; border-radius:50%; object-fit:cover; flex:none;
                           border:2px solid #6b7280; background:#232734; }
.rs-jug .ini { display:flex; align-items:center; justify-content:center; font-size:0.62rem; font-weight:800; color:#fff; }
.rs-jug .n { flex:1; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-weight:600; }
.rs-jug .d { white-space:nowrap; font-weight:700; font-variant-numeric:tabular-nums; font-family:'Inter', sans-serif !important;
             display:flex; align-items:center; gap:5px; }
.rs-jug .d small { color:#8b93a7; font-weight:500; font-size:0.68rem; }
.rs-etq { border-radius:999px; padding:2px 8px; font-size:0.64rem; font-weight:700; white-space:nowrap; }
.rs-etq.rojo { background:rgba(248,113,113,0.14); color:#fca5a5; }
.rs-etq.ambar { background:rgba(251,191,36,0.12); color:#fcd34d; }
.rs-etq.verde { background:rgba(74,222,128,0.12); color:#86efac; }
.rs-mas { color:#8b93a7; font-size:0.72rem; text-align:center; }
.rs-duo { display:flex; align-items:center; justify-content:center; gap:22px; }
.rs-duo div { display:flex; flex-direction:column; align-items:center; gap:2px; }
.rs-duo b { font-size:1.55rem; font-weight:800; color:#f4f6fa; line-height:1.05; font-family:'Inter', sans-serif !important; }
.rs-duo span { color:#8b93a7; font-size:0.62rem; font-weight:700; letter-spacing:0.14em; text-transform:uppercase; }
.rs-duo i { width:1px; height:34px; background:rgba(255,255,255,0.1); }

/* Plan de ventas */
.rs-cuentas { display:flex; justify-content:center; align-items:stretch; gap:0; margin:0 auto 22px; max-width:760px;
              border-radius:16px; background:linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.012));
              border:1px solid rgba(255,255,255,0.08); padding:16px 8px; }
.rs-cuenta { flex:1; display:flex; flex-direction:column; align-items:center; gap:6px; }
.rs-cuenta + .rs-cuenta { border-left:1px solid rgba(255,255,255,0.07); }
.rs-cuenta .r { color:#8b93a7; font-size:0.62rem; font-weight:700; letter-spacing:0.16em; text-transform:uppercase; }
.rs-cuenta .v { font-size:1.45rem; font-weight:800; white-space:nowrap; color:#f4f6fa; font-family:'Inter', sans-serif !important;
                font-variant-numeric:tabular-nums; }
.rs-ventas { display:flex; justify-content:center; flex-wrap:wrap; gap:26px 52px; }
.rs-venta { display:flex; flex-direction:column; align-items:center; gap:12px; }
.rs-venta .carta { zoom:1.3; }
.rs-venta .rs-etq { font-size:0.7rem; padding:3px 11px; }
.rs-otras { display:flex; flex-direction:column; align-items:center; gap:10px; margin-top:26px; }
.rs-otras-tit { color:#8b93a7; font-size:0.66rem; font-weight:800; letter-spacing:0.16em; text-transform:uppercase; }
.rs-otra { display:flex; align-items:center; gap:14px; flex-wrap:wrap; justify-content:center; padding:10px 16px;
           border-radius:12px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.07); max-width:980px; }
.rs-otra .num { color:#e7c565; font-size:0.66rem; font-weight:800; letter-spacing:0.14em; text-transform:uppercase; }
.rs-otra .chips { display:flex; gap:6px; flex-wrap:wrap; justify-content:center; }
.rs-otra .chips span { background:rgba(255,255,255,0.07); border-radius:999px; padding:3px 10px; font-size:0.76rem; color:#e5e9f0; }
.rs-otra .tot { color:#f4f6fa; font-weight:800; font-size:0.86rem; white-space:nowrap; font-family:'Inter', sans-serif !important; }
.rs-otra .tot small { color:#8b93a7; font-weight:500; margin-left:6px; }
.rs-sin { max-width:640px; margin:0 auto; }

/* La liga */
.rs-liga { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:16px; }
@media (max-width: 1000px) { .rs-liga { grid-template-columns:1fr; } }
.rs-panel { border-radius:16px; padding:18px 20px 14px; background:linear-gradient(180deg, #1c202a, #14171e);
            border:1px solid rgba(255,255,255,0.08); }
.rs-panel-tit { color:#c3cbd9; font-size:0.68rem; font-weight:800; letter-spacing:0.16em; text-transform:uppercase;
                text-align:center; margin-bottom:12px; }
.rs-rk { display:grid; grid-template-columns:22px 130px 1fr 112px; align-items:center; gap:12px; padding:6px 8px;
         border-radius:9px; font-size:0.82rem; }
.rs-rk.mio { background:rgba(231,197,101,0.08); box-shadow:inset 0 0 0 1px rgba(231,197,101,0.35); }
.rs-rk .p { color:#8b93a7; font-weight:800; text-align:right; font-family:'Inter', sans-serif !important; }
.rs-rk .q { display:flex; align-items:center; gap:8px; color:#e5e9f0; font-weight:600; white-space:nowrap; overflow:hidden; }
.rs-rk .q i { width:9px; height:9px; border-radius:50%; flex:none; }
.rs-rk.mio .q { color:#fff; font-weight:800; }
.rs-rk .b { height:7px; border-radius:4px; background:rgba(255,255,255,0.06); overflow:hidden; }
.rs-rk .b span { display:block; height:100%; border-radius:4px; }
.rs-rk .b.centro { position:relative; }
.rs-rk .b.centro span { position:absolute; top:0; }
.rs-rk .b.centro::after { content:''; position:absolute; left:50%; top:-3px; bottom:-3px; width:1px; background:rgba(255,255,255,0.25); }
.rs-rk .v { color:#f4f6fa; font-weight:700; text-align:right; white-space:nowrap; font-family:'Inter', sans-serif !important;
            font-variant-numeric:tabular-nums; }
</style>
"""

ICONOS_AVISO = {'rojo': '🚨', 'naranja': '⚠️', 'azul': '📌', 'verde': '📈'}
ORDEN_GRAVEDAD_AVISO = {'rojo': 0, 'naranja': 1, 'azul': 2, 'verde': 3}
MAX_FILAS_AVISO = 5


def _jugador_aviso(fila, derecha):
    """Una fila con la cara, el nombre y un dato a la derecha."""
    nombre = str(fila.get('Jugador') or '').strip()
    color_pos = COLOR_POSICION.get(_pos_principal(fila.get('Posición')), '#6b7280')
    url = url_imagen(f"caras/{nombre}.png", f"caras/{nombre}.jpg")
    cara = (f"<img src='{url}' style='border-color:{color_pos};'>" if url else
            f"<div class='ini' style='border-color:{color_pos};'>{''.join(p[0] for p in nombre.split()[:2]).upper()}</div>")
    return f"<div class='rs-jug'>{cara}<span class='n'>{nombre}</span><span class='d'>{derecha}</span></div>"


def _aviso_html(av):
    filas = av.get('filas') or []
    sobran = len(filas) - MAX_FILAS_AVISO
    bloque = ""
    if filas:
        bloque = ("<div class='rs-av-filas'>" + "".join(filas[:MAX_FILAS_AVISO])
                  + (f"<div class='rs-mas'>y {sobran} más</div>" if sobran > 0 else "") + "</div>")
    return (f"<div class='rs-aviso {av['nivel']}'>"
            f"<div class='rs-av-ico'>{av.get('icono') or ICONOS_AVISO[av['nivel']]}</div>"
            f"<div class='rs-av-tit'>{av['titulo']}</div>"
            + (f"<div class='rs-av-dato'>{av['dato']}</div>" if av.get('dato') else "")
            + (f"<div class='rs-av-nota'>{av['nota']}</div>" if av.get('nota') else "")
            + bloque + "</div>")


def _delta_html(var):
    if var is None or pd.isna(var) or not var:
        return "<span class='rs-delta igual'>= 0 € hoy</span>"
    clase, flecha = ('sube', '▲') if var > 0 else ('baja', '▼')
    return f"<span class='rs-delta {clase}'>{flecha} {formato_euro(abs(var))} hoy</span>"


def _puesto_en(serie_valores, persona, ascendente=False):
    """Puesto de `persona` al ordenar un {persona: valor}; None si no está."""
    orden = sorted(serie_valores, key=lambda p: serie_valores[p], reverse=not ascendente)
    return orden.index(persona) + 1 if persona in orden else None


def _avisos_resumen(info, plantilla):
    """Los avisos de la portada, cada uno con su nivel, cifra y jugadores."""
    avisos = []
    saldo = _a_float(info.get('Balance Total (€)'), 0.0) or 0.0
    valor = _a_float(info.get('Valor de Equipo (€)'), 0.0) or 0.0

    if saldo < 0:
        avisos.append({'nivel': 'rojo', 'icono': '🚨', 'titulo': 'Números rojos',
                       'dato': formato_euro(saldo), 'nota': 'No puntúas hasta volver a positivo'})
    elif saldo < 1_000_000:
        avisos.append({'nivel': 'naranja', 'icono': '💸', 'titulo': 'Caja justa',
                       'dato': formato_euro(saldo), 'nota': 'Sin margen para pujar por un jugador top'})

    df_hist = cargar_historico_completo(_huella_excel(resolver_excel_path()))
    if not df_hist.empty:
        ultima = df_hist['Fecha'].dropna().max()
        if pd.notna(ultima):
            dias = (pd.Timestamp(datetime.now().date()) - ultima.normalize()).days
            if dias >= 2:
                avisos.append({'nivel': 'naranja', 'icono': '🗓️', 'titulo': 'Histórico sin actualizar',
                               'dato': f"{dias} días", 'nota': f"Última importación: {ultima:%d/%m/%Y}"})

    if plantilla.empty:
        return avisos

    posiciones = plantilla['Posición'].astype(str)
    faltan = []
    for texto, rotulo, minimo in (('Portero', 'Porteros', 1), ('Defensa', 'Defensas', 3),
                                  ('Centrocampista', 'Centrocampistas', 3), ('Delantero', 'Delanteros', 1)):
        tiene = int(posiciones.str.contains(texto, case=False, na=False).sum())
        if tiene < minimo:
            faltan.append(f"<div class='rs-jug'><span class='n'>{rotulo}</span>"
                          f"<span class='d'>{tiene} <small>de {minimo}</small></span></div>")
    if faltan:
        avisos.append({'nivel': 'rojo', 'icono': '🧩', 'titulo': 'Once incompleto', 'filas': faltan})

    # Bajas y dudas, todas en la misma tarjeta: primero las bajas.
    etiquetas = {'lesionado': ('rojo', 'Lesionado'), 'sancionado': ('rojo', 'Sancionado'),
                 'descartado': ('rojo', 'Descartado'), 'duda': ('ambar', 'Duda')}
    ausencias = [(f, estado_jugador(f)) for _, f in plantilla.iterrows()]
    ausencias = sorted(((f, e) for f, e in ausencias if e in etiquetas), key=lambda x: x[1] == 'duda')
    if ausencias:
        bajas = sum(1 for _, e in ausencias if e != 'duda')
        avisos.append({
            'nivel': 'rojo' if bajas else 'naranja', 'icono': '🚑', 'titulo': 'Bajas y dudas',
            'filas': [_jugador_aviso(f, f"<span class='rs-etq {etiquetas[e][0]}'>{etiquetas[e][1]}</span>")
                      for f, e in ausencias]})

    # Subidas y caídas en porcentaje: el mismo euro no pesa igual en un jugador
    # de 200.000 € que en uno de 6 millones.
    PCT_DESPLOME, PCT_RACHA, MINIMO_EUROS = -0.04, 0.05, 20000
    mov = plantilla.assign(_var=pd.to_numeric(plantilla['Variación Diaria (€)'], errors='coerce'),
                           _valor=pd.to_numeric(plantilla['Valor Actual (€)'], errors='coerce'))
    mov = mov.dropna(subset=['_var', '_valor'])
    mov = mov[mov['_valor'] > 0].copy()
    mov['_pct'] = mov['_var'] / mov['_valor']

    def filas_mov(sub, color):
        return [_jugador_aviso(r, f"<span style='color:{color};'>{r['_pct'] * 100:+.1f}%</span>"
                                  f"<small>{formato_tendencia(r['_var'])}</small>")
                for _, r in sub.iterrows()]

    caen = mov[(mov['_pct'] <= PCT_DESPLOME) & (mov['_var'] <= -MINIMO_EUROS)].sort_values('_pct')
    if not caen.empty:
        avisos.append({'nivel': 'naranja', 'icono': '📉', 'titulo': 'Caídas fuertes',
                       'filas': filas_mov(caen, '#f87171')})
    suben = mov[(mov['_pct'] >= PCT_RACHA) & (mov['_var'] >= MINIMO_EUROS)].sort_values('_pct', ascending=False)
    if not suben.empty:
        avisos.append({'nivel': 'verde', 'icono': '🚀', 'titulo': 'Subidas fuertes',
                       'filas': filas_mov(suben, '#4ade80')})

    sin_cuadrar = int(((pd.to_numeric(plantilla['PJ'], errors='coerce').fillna(0) > 0)
                       & plantilla['PJ Casa'].isna()).sum())
    if sin_cuadrar:
        avisos.append({'nivel': 'naranja', 'icono': '🏠', 'titulo': 'Casa y fuera sin repartir',
                       'dato': f"{sin_cuadrar} jugador{'es' if sin_cuadrar != 1 else ''}",
                       'nota': 'Pulsa actualizar para descargarlo'})

    n = len(plantilla)
    if n < 13:
        avisos.append({'nivel': 'naranja', 'icono': '👥', 'titulo': 'Plantilla corta',
                       'dato': f"{n} jugadores", 'nota': 'Una baja te obliga a comerte un cero'})
    elif n > 22:
        avisos.append({'nivel': 'azul', 'icono': '👥', 'titulo': 'Plantilla larga',
                       'dato': f"{n} jugadores", 'nota': 'Mucho dinero parado en el banquillo'})

    if valor > 0:
        valores = pd.to_numeric(plantilla['Valor Actual (€)'], errors='coerce')
        if valores.notna().any():
            estrella = plantilla.loc[valores.idxmax()]
            peso = valores.max() / valor
            if peso > 0.35:
                avisos.append({'nivel': 'azul', 'icono': '👑', 'titulo': 'Dependencia de un jugador',
                               'dato': f"{peso * 100:.0f}% del valor",
                               'filas': [_jugador_aviso(estrella, formato_euro(valores.max()))]})

    # La jornada que viene: cuántos juegan en casa y los cruces más duros.
    en_casa = en_fuera = 0
    duros = []
    corte_duro = cortes_color_dificultad()[3]
    for _, jug in plantilla.iterrows():
        fix = get_fixture_equipo(jug.get('Equipo'))
        if not fix:
            continue
        if fix['es_casa']:
            en_casa += 1
        else:
            en_fuera += 1
        if fix['dificultad'] >= corte_duro:
            duros.append((fix['dificultad'], jug, fix['rival']))
    if en_casa or en_fuera:
        duros.sort(key=lambda x: -x[0])
        avisos.append({
            'nivel': 'azul', 'icono': '🗓️', 'titulo': 'Próxima jornada',
            'dato': (f"<div class='rs-duo'><div><b>{en_casa}</b><span>En casa</span></div><i></i>"
                     f"<div><b>{en_fuera}</b><span>Fuera</span></div></div>"),
            'filas': [_jugador_aviso(j, f"<small>vs</small>{escudo_html(rival, 20)}") for _, j, rival in duros]})

    avisos.sort(key=lambda a: ORDEN_GRAVEDAD_AVISO.get(a['nivel'], 9))
    return avisos


def _plan_de_ventas_html(saldo, plantilla):
    deuda = abs(saldo)
    vendibles = jugadores_vendibles(MI_EQUIPO, recortar=False)
    opciones = buscar_ventas_para_deuda(vendibles, deuda)
    bloqueados = [f['Jugador'] for _, f in plantilla.iterrows()
                  if not vendible_antes_de_jornada(f['Jugador'], MI_EQUIPO)]
    html = "<div class='rs-titulo'>Plan de ventas</div>"
    if not opciones:
        texto = "Ninguna combinación de hasta 6 jugadores vendibles cubre la deuda."
        if bloqueados:
            texto = f"{texto} Con candado: {', '.join(map(str, bloqueados))}."
        return html + ("<div class='rs-avisos rs-sin'>" + _aviso_html(
            {'nivel': 'rojo', 'icono': '🔒', 'titulo': 'Sin salida con ventas', 'dato': formato_euro(saldo),
             'nota': texto}) + "</div>")

    mejor = opciones[0]
    queda = mejor['ingreso'] - deuda
    html += ("<div class='rs-cuentas'>"
             f"<div class='rs-cuenta'><span class='r'>Deuda</span><span class='v' style='color:#f87171;'>{formato_euro(saldo)}</span></div>"
             f"<div class='rs-cuenta'><span class='r'>Ingreso</span><span class='v'>{formato_euro(mejor['ingreso'])}</span></div>"
             f"<div class='rs-cuenta'><span class='r'>Saldo final</span><span class='v' style='color:#4ade80;'>"
             f"{formato_tendencia(queda) if queda else '0 €'}</span></div></div>")
    cartas = []
    for sug in mejor['jugadores']:
        pos = str(sug['Posición']).split('/')[0].strip()
        rotulo_pos = ABREVIA_POSICION.get(pos, 'DEL')
        libre = fecha_desbloqueo(sug['Jugador'], MI_EQUIPO)
        etiqueta = (f"<span class='rs-etq ambar'>🔒 Vendible el {libre:%d/%m}</span>" if libre
                    else "<span class='rs-etq verde'>Vendible ya</span>")
        cartas.append(f"<div class='rs-venta'><div class='carta'>{generar_carta_html(sug, rotulo_pos)}</div>{etiqueta}</div>")
    html += "<div class='rs-ventas'>" + "".join(cartas) + "</div>"

    if len(opciones) > 1:
        html += "<div class='rs-otras'><div class='rs-otras-tit'>Alternativas</div>"
        for i, alt in enumerate(opciones[1:], start=2):
            chips = "".join(f"<span>{j['Jugador']}</span>" for j in alt['jugadores'])
            html += (f"<div class='rs-otra'><span class='num'>Opción {i}</span><div class='chips'>{chips}</div>"
                     f"<span class='tot'>{formato_euro(alt['ingreso'])}"
                     f"<small>{'sobran ' + formato_euro(alt['exceso']) if alt['exceso'] > 0 else 'justo'}</small></span></div>")
        html += "</div>"
    return html


def _ranking_html(titulo, valores, formato, colores, con_signo=False):
    """Panel con la liga ordenada por un dato, con barra y tu fila resaltada.

    Con `con_signo` (saldo, variación) la barra sale del centro: a la derecha
    lo positivo y a la izquierda lo negativo, y la cifra va en verde o rojo."""
    orden = sorted(valores.items(), key=lambda x: -x[1])
    if con_signo:
        maximo = max((abs(v) for _, v in orden), default=0) or 1
    else:
        maximo = max((v for _, v in orden), default=0) or 1
    filas = []
    for i, (persona, v) in enumerate(orden, start=1):
        color = colores.get(persona, '#8b93a7')
        if con_signo:
            ancho = abs(v) / maximo * 50
            lado = 'left:50%' if v >= 0 else 'right:50%'
            barra = (f"<span class='b centro'><span style='{lado}; width:{ancho:.1f}%; background:{color};'></span></span>")
            color_v = '#4ade80' if v > 0 else '#f87171' if v < 0 else '#9ca3af'
            cifra = f"<span style='color:{color_v};'>{formato(v)}</span>"
        else:
            ancho = max(v, 0) / maximo * 100
            barra = f"<span class='b'><span style='width:{ancho:.0f}%; background:{color};'></span></span>"
            cifra = formato(v)
        filas.append(f"<div class='rs-rk{' mio' if persona == MI_EQUIPO else ''}'><span class='p'>{i}</span>"
                     f"<span class='q'><i style='background:{color};'></i>{persona}</span>"
                     f"{barra}<span class='v'>{cifra}</span></div>")
    return f"<div class='rs-panel'><div class='rs-panel-tit'>{titulo}</div>{''.join(filas)}</div>"


def ui_resumen():
    part = db['participantes'].dropna(subset=['Persona']).copy()
    part['Persona'] = part['Persona'].astype(str).str.replace('⭐ ', '', regex=False).str.strip()
    mias = part[part['Persona'] == MI_EQUIPO]
    if mias.empty:
        st.warning(f"No se han encontrado datos del equipo '{MI_EQUIPO}' en la hoja de Participantes.")
        return
    info = mias.iloc[0]
    plantilla = db['plantillas'][db['plantillas']['Participante'] == MI_EQUIPO]
    color = COLORES_MANAGERS.get(MI_EQUIPO, '#e7c565')

    saldo = _a_float(info.get('Balance Total (€)'), 0.0) or 0.0
    valor = _a_float(info.get('Valor de Equipo (€)'), 0.0) or 0.0
    patrimonio = _a_float(info.get('Patrimonio Total (€)'), 0.0) or 0.0
    var = _a_float(info.get('Variación Diaria (€)'), 0.0) or 0.0
    total = len(part)

    puntos = {p: int(_a_float(v, 0) or 0) for p, v in zip(part['Persona'], part.get('Puntos', pd.Series(0, index=part.index)))}
    hay_puntos = any(puntos.values())
    mis_puntos = puntos.get(MI_EQUIPO, 0)
    clasif = sorted(puntos, key=lambda p: -puntos[p])
    puesto = clasif.index(MI_EQUIPO) + 1 if hay_puntos else None
    if not hay_puntos:
        distancia = ""
    elif puesto == 1:
        distancia = "Líder de la liga"
    else:
        delante = clasif[puesto - 2]
        dif = puntos[delante] - mis_puntos
        distancia = f"Empatado con <b>{delante}</b>" if dif == 0 else f"A <b>{dif} puntos</b> de {delante}"

    rangos = []
    try:
        indices = indices_valoracion(resumen_onces_liga(_huella_excel(resolver_excel_path())))
        rangos.append(("Calidad de plantilla", _puesto_en(indices, MI_EQUIPO)))
    except Exception:
        pass
    valores_eq = {p: _a_float(v, 0.0) or 0.0 for p, v in zip(part['Persona'], part['Valor de Equipo (€)'])}
    patrimonios = {p: _a_float(v, 0.0) or 0.0 for p, v in zip(part['Persona'], part['Patrimonio Total (€)'])}
    rangos.append(("Valor de equipo", _puesto_en(valores_eq, MI_EQUIPO)))
    rangos.append(("Patrimonio", _puesto_en(patrimonios, MI_EQUIPO)))

    def color_puesto(p):
        return '#4ade80' if p <= 3 else '#f87171' if p > total - 3 else '#fcd34d'

    rangos_html = "".join(f"<div class='rs-rango'><span class='r'>{r}</span>"
                          f"<span class='v' style='color:{color_puesto(p)};'>{p}º<small>de {total}</small></span></div>"
                          for r, p in rangos if p)

    lineas = [int(plantilla['Posición'].astype(str).str.contains(t, case=False, na=False).sum())
              for t in ('Portero', 'Defensa', 'Centrocampista', 'Delantero')]
    chips_lineas = "".join(f"<span>{r}<b>{n}</b></span>" for r, n in zip(('POR', 'DEF', 'MED', 'DEL'), lineas))

    kpis = [
        ("Puntos de liga", f"{mis_puntos}<small>pts</small>", ""),
        ("Valor de equipo", formato_euro(valor), _delta_html(var)),
        ("Patrimonio", formato_euro(patrimonio), _delta_html(var)),
        ("Saldo", formato_euro(saldo), ""),
        ("Plantilla", f"{len(plantilla)}<small>jugadores</small>", f"<div class='rs-lineas'>{chips_lineas}</div>"),
    ]
    kpis_html = "".join(f"<div class='rs-kpi'><span class='r'>{r}</span>"
                        f"<span class='v{' neg' if r == 'Saldo' and saldo < 0 else ''}'>{v}</span>{extra}</div>"
                        for r, v, extra in kpis)

    heroe = (f"<div class='rs-heroe' style='--c:{color};'><div class='rs-arriba'>"
             f"<div class='rs-yo'>"
             + (f"<div class='rs-puesto'>{puesto}º</div>" if puesto else "")
             + f"<div class='rs-nombre'><b>{MI_EQUIPO}</b>"
             + (f"<span>{distancia}</span>" if distancia else "")
             + f"</div></div><div class='rs-rangos'>{rangos_html}</div></div>"
             f"<div class='rs-kpis'>{kpis_html}</div></div>")

    avisos = _avisos_resumen(info, plantilla)
    urgentes = [a for a in avisos if a['nivel'] in ('rojo', 'naranja')]
    contexto = [a for a in avisos if a['nivel'] not in ('rojo', 'naranja')]
    if not urgentes:
        urgentes = [{'nivel': 'verde', 'icono': '✅', 'titulo': 'Todo en orden',
                     'nota': 'Once cubierto y saldo en positivo'}]

    html = CSS_RESUMEN + heroe
    html += "<div class='rs-titulo'>Alertas</div><div class='rs-avisos'>" + "".join(map(_aviso_html, urgentes)) + "</div>"
    # Si estás en rojo, el plan para salir va justo debajo de las alertas.
    if saldo < 0:
        html += _plan_de_ventas_html(saldo, plantilla)
    st.markdown(html, unsafe_allow_html=True)

    liga = ""
    if contexto:
        liga += "<div class='rs-titulo'>Información</div><div class='rs-avisos'>" + "".join(map(_aviso_html, contexto)) + "</div>"
    liga += "<div class='rs-titulo'>La liga</div><div class='rs-liga'>"
    if hay_puntos:
        liga += _ranking_html("Clasificación", puntos, lambda v: f"{int(v)} pts", COLORES_MANAGERS)
    liga += _ranking_html("Patrimonio", patrimonios, formato_euro, COLORES_MANAGERS)
    variaciones = {p: _a_float(v, 0.0) or 0.0 for p, v in zip(part['Persona'], part['Variación Diaria (€)'])}
    saldos = {p: _a_float(v, 0.0) or 0.0 for p, v in zip(part['Persona'], part['Balance Total (€)'])}
    liga += _ranking_html("Variación diaria", variaciones,
                          lambda v: formato_tendencia(v) if v else "0 €", COLORES_MANAGERS, con_signo=True)
    liga += _ranking_html("Saldo", saldos, formato_euro, COLORES_MANAGERS, con_signo=True)
    liga += "</div>"
    st.markdown(liga, unsafe_allow_html=True)


if _pagina == "Comparar":
    ui_comparador()

if _pagina == "Mercado":
    ui_mercado()

if _pagina == "Plantillas":
    ui_plantillas()

if _pagina == "Movimientos":
    ui_auditoria()

if _pagina == "Participantes":
    ui_participantes()
if _pagina == "Resumen":
    ui_resumen()


# ==========================================
# 📚 PESTAÑA: HISTÓRICO (evolución diaria/semanal/mensual/anual)
# ==========================================
# Qué se puede dibujar del histórico. Antes solo se graficaba el valor de
# mercado, aunque cada bloque guarda también puntos, media y variación.
METRICAS_HISTORICO = {
    "Valor de mercado": ('Valor Actual (€)', formato_euro, "Valor (€)"),
    "Media de puntos": ('Media Puntos', formato_puntos, "Media"),
    "Puntos acumulados": ('Puntos', lambda v: f"{v:,.0f}".replace(",", "."), "Puntos"),
    "Variación diaria": ('Variación Diaria (€)', formato_tendencia, "Variación (€)"),
}

COLORES_SERIES_HIST = ['#ffd966', '#4ade80', '#f87171', '#60a5fa', '#c084fc', '#fb923c',
                       '#2dd4bf', '#f472b6', '#a3e635', '#38bdf8', '#fbbf24', '#e879f9']


@st.fragment
def _historial_html(lista_movimientos, serie):
    """Lista de compras y ventas del jugador para la ficha de resumen.

    Incluye TAMBIÉN los movimientos que no se pueden pintar en la gráfica por
    caer fuera de los días importados. Es lo que pasaba con Angeliño y Miguel
    Román: ambos comprados el 09/08 y el histórico arranca el 10/08, así que
    solo se veía el punto de la venta y parecía que faltaba la compra."""
    if not lista_movimientos:
        return ""
    filas = []
    for fecha, tipo, persona, importe, _sobrepuja in sorted(lista_movimientos, key=lambda x: x[0]):
        es_compra = str(tipo).strip().lower() == 'compra'
        fuera = pd.Timestamp(fecha) not in serie.index
        icono = '🛒' if es_compra else '💸'
        color = '#f87171' if es_compra else '#f59e0b'
        filas.append(
            f'<div style="font-size:0.78em; color:#c7d0e0; margin-top:3px;">'
            f'<span style="color:{color};">{icono}</span> '
            f'{pd.Timestamp(fecha).strftime("%d/%m")} · '
            f'{"comprado por" if es_compra else "vendido por"} <b>{persona}</b> · '
            f'{formato_euro(importe)}'
            + (' <span title="Fuera de los días importados: no se puede marcar en la gráfica">🕘</span>'
               if fuera else '')
            + '</div>'
        )
    return ('<div style="margin-top:8px; border-top:1px solid rgba(255,255,255,0.08); padding-top:6px;">'
            '<div style="color:#8b93a7; font-size:0.72em; text-transform:uppercase; '
            'letter-spacing:1px;">Movimientos</div>' + "".join(filas) + '</div>')


def _texto_con_variacion(serie, formateador):
    """Para cada punto: el dato del día y, debajo, cuánto ha cambiado respecto
    al anterior. El primero no tiene con qué compararse."""
    valores = list(serie.values)
    textos = []
    for i, v in enumerate(valores):
        if i == 0:
            cambio = "<span style='color:#9aa3b2;'>primer día importado</span>"
        else:
            delta = float(v) - float(valores[i - 1])
            if delta > 0:
                cambio = f"<span style='color:#4ade80;'>⬆ {formateador(delta)}</span>"
            elif delta < 0:
                cambio = f"<span style='color:#f87171;'>⬇ {formateador(abs(delta))}</span>"
            else:
                cambio = "<span style='color:#9aa3b2;'>— se mantiene</span>"
        textos.append(f"{formateador(v)}<br>{cambio}")
    return textos


@st.cache_data(show_spinner=False)
def movimientos_por_jugador(huella=None):
    """{(jugador, equipo): [(fecha, tipo, persona, importe, sobrepuja), ...]}

    Sirve para marcar en la gráfica del histórico el día exacto en que un
    jugador cambió de manos. Solo entran los movimientos con fecha: hoy la
    columna 'Fecha Fichaje' de Contabilidad está rellena en las 107 compras y en
    ninguna de las 89 ventas, así que de momento se marcan las compras. En
    cuanto pongas fecha en una venta, aparecerá sola sin tocar nada."""
    contabilidad = db.get('contabilidad')
    if contabilidad is None or contabilidad.empty or 'Fecha Fichaje' not in contabilidad.columns:
        return {}
    registro = {}
    for _, fila in contabilidad.dropna(subset=['Jugador']).iterrows():
        fecha = _a_fecha(fila.get('Fecha Fichaje'))
        if not fecha:
            continue
        clave = (str(fila['Jugador']).strip(), str(fila.get('Equipo') or '').strip())
        registro.setdefault(clave, []).append((
            fecha, str(fila.get('Tipo de Operación') or ''), fila.get('Persona'),
            fila.get('Importe (€)'), fila.get('Sobrepuja (€)'),
        ))
    return registro


@st.cache_data(show_spinner=False)
def evolucion_patrimonios(huella=None):
    """Cuánto ha ganado o perdido la plantilla de cada mánager desde el primer
    día importado.

    El Histórico guarda el valor diario de cientos de jugadores y la pestaña
    solo dejaba mirarlos de uno en uno. La pregunta que uno se hace al abrir un
    histórico es si va ganando o perdiendo, y no se podía responder.
    """
    hist = cargar_historico_completo(huella)
    plantillas = db.get('plantillas')
    if hist.empty or plantillas is None or plantillas.empty:
        return pd.DataFrame()

    h = hist.dropna(subset=['Fecha', 'Jugador']).copy()
    h['_k'] = h['Jugador'].astype(str).str.strip() + '||' + h['Equipo'].astype(str).str.strip()
    h = h.sort_values('Fecha')
    primeros = h.drop_duplicates('_k', keep='first').set_index('_k')['Valor Actual (€)']
    ultimos = h.drop_duplicates('_k', keep='last').set_index('_k')['Valor Actual (€)']

    filas = []
    for persona, grupo in plantillas.dropna(subset=['Jugador', 'Participante']).groupby('Participante'):
        claves = (grupo['Jugador'].astype(str).str.strip() + '||'
                  + grupo['Equipo'].astype(str).str.strip())
        ini = pd.to_numeric(claves.map(primeros), errors='coerce')
        fin = pd.to_numeric(claves.map(ultimos), errors='coerce')
        validos = ini.notna() & fin.notna()
        if not validos.any():
            continue
        filas.append({
            'Mánager': str(persona).strip(),
            'Jugadores': int(validos.sum()),
            'Valor entonces': float(ini[validos].sum()),
            'Valor hoy': float(fin[validos].sum()),
            'Ha ganado': float(fin[validos].sum() - ini[validos].sum()),
        })
    if not filas:
        return pd.DataFrame()
    marco = pd.DataFrame(filas).sort_values('Ha ganado', ascending=False).reset_index(drop=True)
    marco.insert(0, 'Puesto', range(1, len(marco) + 1))
    return marco


def _historico_con_hoy(hist):
    """El histórico más el mercado de ahora, si el mercado es más reciente.

    El botón de actualizar trae los precios nuevos pero no importa el día al
    histórico (eso lo hace la ejecución de las 8:30). Entretanto la carta decía
    1.630.000 € y la ficha de al lado 1.380.000 €. Si el mercado ya no coincide
    con el último día guardado, se añade como un día más."""
    mercado = db.get('mercado')
    if hist.empty or mercado is None or mercado.empty:
        return hist
    ultimo = hist['Fecha'].max()
    guardado = hist[hist['Fecha'] == ultimo][['Jugador', 'Equipo', 'Valor Actual (€)']]
    ahora = mercado.dropna(subset=['Jugador'])
    cruce = ahora.merge(guardado, on=['Jugador', 'Equipo'], suffixes=('', '_h'))
    if cruce.empty:
        return hist
    distintos = (pd.to_numeric(cruce['Valor Actual (€)'], errors='coerce')
                 != pd.to_numeric(cruce['Valor Actual (€)_h'], errors='coerce')).mean()
    if distintos < 0.10:
        return hist
    dia = max(pd.Timestamp(fecha_de_mercado().date()), ultimo + pd.Timedelta(days=1))
    nuevo = ahora[[c for c in hist.columns if c in ahora.columns]].copy()
    nuevo['Fecha'] = dia
    if 'Fecha_Texto' in hist.columns:
        nuevo['Fecha_Texto'] = dia.strftime('%d/%m/%Y')
    return pd.concat([hist, nuevo], ignore_index=True)


@st.cache_data(show_spinner=False, persist="disk")
def cambios_de_valor(huella=None, dias=None):
    """Quién más ha subido y quién más ha bajado en los últimos `dias`.

    Las rachas cuentan días seguidos en la misma dirección, que está bien para
    detectar tendencias pero responde a otra pregunta. Lo que uno quiere saber
    al abrir esto suele ser más simple: quién se ha movido y cuánto, hoy, esta
    semana o este mes.

    Con `dias=None` se compara contra el primer día del histórico. Si no hay un
    día exacto a esa distancia (el bot puede haberse saltado una jornada), se
    coge el primero disponible a partir de ahí, que es lo honesto: comparar
    contra el dato más cercano que existe, no inventar uno.
    """
    hist = _historico_con_hoy(cargar_historico_completo(huella))
    if hist.empty:
        return pd.DataFrame(), pd.DataFrame()

    h = hist.dropna(subset=['Fecha', 'Jugador']).copy()
    h['_clave'] = (h['Jugador'].astype(str).str.strip() + '||'
                   + h['Equipo'].astype(str).str.strip())
    h = h.sort_values('Fecha')

    ultimo_dia = h['Fecha'].max()
    if dias is None:
        dia_ref = h['Fecha'].min()
    else:
        objetivo = ultimo_dia - pd.Timedelta(days=int(dias))
        anteriores = h.loc[h['Fecha'] <= objetivo, 'Fecha']
        dia_ref = anteriores.max() if not anteriores.empty else h['Fecha'].min()
    if pd.isna(dia_ref) or dia_ref == ultimo_dia:
        return pd.DataFrame(), pd.DataFrame()

    hoy = h[h['Fecha'] == ultimo_dia].drop_duplicates('_clave').set_index('_clave')
    antes = h[h['Fecha'] == dia_ref].drop_duplicates('_clave').set_index('_clave')
    comunes = hoy.index.intersection(antes.index)
    if comunes.empty:
        return pd.DataFrame(), pd.DataFrame()

    tabla = pd.DataFrame({
        'Jugador': hoy.loc[comunes, 'Jugador'],
        'Equipo': hoy.loc[comunes, 'Equipo'],
        'Antes': pd.to_numeric(antes.loc[comunes, 'Valor Actual (€)'], errors='coerce'),
        'Ahora': pd.to_numeric(hoy.loc[comunes, 'Valor Actual (€)'], errors='coerce'),
    }).dropna(subset=['Antes', 'Ahora'])
    tabla['Cambio'] = tabla['Ahora'] - tabla['Antes']
    tabla['%'] = (tabla['Cambio'] / tabla['Antes'].replace(0, pd.NA)) * 100
    tabla = tabla[tabla['Cambio'] != 0].reset_index(drop=True)
    tabla.attrs['desde'] = dia_ref
    tabla.attrs['hasta'] = ultimo_dia

    suben = tabla.sort_values('Cambio', ascending=False)
    bajan = tabla.sort_values('Cambio')
    for marco in (suben, bajan):
        marco.attrs['desde'] = dia_ref
        marco.attrs['hasta'] = ultimo_dia
    return suben, bajan


CSS_FICHA_HISTORICO = """
<style>
.hj-lista { display:flex; flex-direction:column; gap:14px; margin-top:14px; }
.hj-ficha { display:grid; grid-template-columns:200px 1fr; gap:24px; align-items:center;
            background:linear-gradient(145deg, rgba(20,20,30,0.85), rgba(10,10,15,0.9));
            border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:20px 22px;
            text-align:center; }
.hj-ficha.sin-carta { grid-template-columns:1fr; }
@media (max-width: 760px) { .hj-ficha { grid-template-columns:1fr; } }
.hj-carta { display:flex; justify-content:center; align-items:center; }
.hj-nombre { color:#f2f4f8; font-size:1.25rem; font-weight:700; line-height:1.2; }
.hj-sub { color:#8b93a7; font-size:0.82rem; margin-top:3px; }
.hj-bloques { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; margin-top:14px; }
@media (max-width: 900px) { .hj-bloques { grid-template-columns:1fr; } }
.hj-bloque { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.07);
             border-radius:10px; padding:14px 12px; display:flex; flex-direction:column;
             align-items:center; justify-content:center; min-height:118px; }
.hj-rotulo { color:#8b93a7; font-size:0.68rem; letter-spacing:0.12em; text-transform:uppercase; }
.hj-cifra { font-family:'Fraunces', Georgia, serif; font-size:1.6rem; font-weight:600; color:#f2f4f8;
            line-height:1.1; margin-top:6px; font-variant-numeric:tabular-nums; white-space:nowrap; }
.hj-linea { color:#c3cbd9; font-size:0.78rem; margin-top:4px; }
.hj-datos { display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:10px; margin-top:12px;
            padding-top:12px; border-top:1px solid rgba(255,255,255,0.07); }
@media (max-width: 900px) { .hj-datos { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
.hj-dato b { display:block; font-family:'Fraunces', Georgia, serif; font-size:1.15rem; font-weight:600;
             color:#f2f4f8; margin-top:3px; font-variant-numeric:tabular-nums; }
.hj-dato span { color:#8b93a7; font-size:0.74rem; }
.hj-chip { display:inline-block; background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.1);
           border-radius:999px; padding:2px 12px; color:#f2f4f8; font-size:0.9rem; font-weight:600; margin-top:6px; }
.hj-movs { margin-top:4px; }
.hj-verde { color:#4ade80; } .hj-rojo { color:#f87171; } .hj-gris { color:#8b93a7; }
</style>
"""

NOMBRE_PLURAL_POSICION = {'Portero': 'porteros', 'Defensa': 'defensas',
                          'Centrocampista': 'centrocampistas', 'Delantero': 'delanteros'}


def _clase_signo(valor):
    return 'hj-verde' if valor > 0 else ('hj-rojo' if valor < 0 else 'hj-gris')


def _puestos_por_posicion(mercado):
    """{(jugador, equipo): (puesto, total)} por puntos dentro de su posición."""
    if mercado is None or mercado.empty:
        return {}
    aux = mercado.dropna(subset=['Jugador']).copy()
    # Solo cuentan los que han jugado: "72º de 204" metía en el total a los que
    # no han pisado el campo y hacía parecer peor a cualquiera.
    aux = aux[pd.to_numeric(aux.get('PJ'), errors='coerce').fillna(0) > 0]
    aux['_pos'] = aux['Posición'].map(_pos_principal)
    aux['_pts'] = pd.to_numeric(aux['Puntos'], errors='coerce').fillna(0)
    aux['_puesto'] = aux.groupby('_pos')['_pts'].rank(ascending=False, method='min')
    totales = aux.groupby('_pos')['Jugador'].count().to_dict()
    return {(str(f['Jugador']).strip(), str(f['Equipo']).strip()): (int(f['_puesto']), totales[f['_pos']])
            for _, f in aux.iterrows()}


def _ficha_historico_html(etiqueta, color, serie, clave, movimientos, fila, puestos):
    """Ficha de un jugador bajo la gráfica del histórico: su carta, lo que vale
    hoy, cómo le va a quien lo tiene y un resumen de su temporada."""
    lista_mov = movimientos.get(clave, [])
    v_hoy = float(serie.iloc[-1])
    v_max, fecha_max = float(serie.max()), serie.idxmax()

    # ── Valor hoy
    variacion = _a_float(fila.get('Variación Diaria (€)'), None) if fila is not None else None
    if variacion is None and len(serie) > 1:
        variacion = v_hoy - float(serie.iloc[-2])
    linea_hoy = (f"<div class='hj-linea'><span class='{_clase_signo(variacion)}'>"
                 f"{formato_tendencia(variacion)}</span> hoy</div>") if variacion is not None else ""
    if v_max and v_hoy < v_max * 0.9995:
        linea_techo = (f"<div class='hj-linea'><span class='hj-rojo'>"
                       f"{(v_hoy - v_max) / v_max * 100:.1f}%</span> bajo su máximo "
                       f"({formato_euro(v_max)}, {pd.Timestamp(fecha_max):%d/%m})</div>")
    else:
        linea_techo = "<div class='hj-linea hj-verde'>En su máximo</div>"
    bloque_valor = (f"<div class='hj-bloque'><div class='hj-rotulo'>Valor hoy</div>"
                    f"<div class='hj-cifra'>{formato_euro(v_hoy)}</div>{linea_hoy}{linea_techo}</div>")

    # ── Propietario y cómo le va desde que lo compró
    dueno = str(fila.get('Estado') or '').strip() if fila is not None else ''
    if dueno == 'Tuyo':
        dueno = MI_EQUIPO
    if not dueno or dueno.lower() == 'libre':
        bloque_dueno = ("<div class='hj-bloque'><div class='hj-rotulo'>Propietario</div>"
                        "<div class='hj-cifra hj-gris'>Libre</div></div>")
    else:
        compras = [m for m in lista_mov
                   if str(m[1]).strip().lower() == 'compra' and str(m[2]).strip() == dueno]
        nombre_dueno = "Tú" if dueno == MI_EQUIPO else dueno
        if compras:
            fecha_c, _, _, importe_c, _ = max(compras, key=lambda m: m[0])
            importe_c = _a_float(importe_c, None)
        else:
            fecha_c, importe_c = None, None
        if importe_c:
            gana = v_hoy - importe_c
            bloque_dueno = (
                f"<div class='hj-bloque'><div class='hj-rotulo'>Propietario</div>"
                f"<span class='hj-chip'>{nombre_dueno}</span>"
                f"<div class='hj-cifra {_clase_signo(gana)}'>{formato_tendencia(gana)}</div>"
                f"<div class='hj-linea'>{gana / importe_c * 100:+.1f}% · pagó {formato_euro(importe_c)}"
                f" el {pd.Timestamp(fecha_c):%d/%m}</div></div>")
        else:
            bloque_dueno = (
                f"<div class='hj-bloque'><div class='hj-rotulo'>Propietario</div>"
                f"<span class='hj-chip'>{nombre_dueno}</span>"
                f"<div class='hj-linea' style='margin-top:10px;'>Sin compra registrada "
                f"(reparto inicial)</div></div>")

    # ── Puntos y puesto en su posición
    if fila is not None:
        pos = _pos_principal(fila.get('Posición'))
        puntos = _a_float(fila.get('Puntos'), 0.0) or 0.0
        puesto = puestos.get(clave)
        linea_puesto = (f"<div class='hj-linea'>{puesto[0]}º de {puesto[1]} "
                        f"{NOMBRE_PLURAL_POSICION.get(pos, 'jugadores')}</div>") if puesto else ""
        bloque_puntos = (f"<div class='hj-bloque'><div class='hj-rotulo'>Puntos</div>"
                         f"<div class='hj-cifra'>{puntos:.0f}</div>{linea_puesto}</div>")
    else:
        bloque_puntos = ""

    # ── Resumen de su temporada
    datos = ""
    if fila is not None:
        pj = int(_a_float(fila.get('PJ'), 0.0) or 0)
        partidos_equipo = int(partidos_equipos_global.get(fila.get('Equipo'), 0) or 0)

        def _media(col, pj_col):
            n = int(_a_float(fila.get(pj_col), 0.0) or 0)
            if not n:
                return "—", "sin partidos"
            return formato_puntos(fila.get(col)), f"{n} partido{'s' if n != 1 else ''}"

        m_casa, n_casa = _media('Media Puntos Casa', 'PJ Casa')
        m_fuera, n_fuera = _media('Media Puntos Fuera', 'PJ Fuera')
        goles = int(_a_float(fila.get('Goles'), 0.0) or 0)
        asist = int(_a_float(fila.get('Asistencias'), 0.0) or 0)
        celdas = [
            ("Media", formato_puntos(fila.get('Media Puntos')) if pj else "—", "por partido"),
            ("En casa", m_casa, n_casa),
            ("Fuera", m_fuera, n_fuera),
            ("Ha jugado", f"{pj} de {partidos_equipo}" if partidos_equipo else str(pj),
             "partidos de su equipo"),
            ("Goles · asist.", f"{goles} · {asist}", "en la temporada"),
        ]
        datos = "<div class='hj-datos'>" + "".join(
            f"<div class='hj-dato'><div class='hj-rotulo'>{r}</div><b>{v}</b><span>{s}</span></div>"
            for r, v, s in celdas) + "</div>"

    subtitulo = ""
    if fila is not None:
        subtitulo = (f"<div class='hj-sub'>{fila.get('Equipo')} · "
                     f"{str(fila.get('Posición') or '').replace('/', ' / ')}</div>")
    cuerpo = (f"<div><div class='hj-nombre'>{etiqueta}</div>{subtitulo}"
              f"<div class='hj-bloques'>{bloque_valor}{bloque_dueno}{bloque_puntos}</div>"
              f"{datos}<div class='hj-movs'>{_historial_html(lista_mov, serie) or ''}</div></div>")
    if fila is None:
        return (f"<div class='hj-ficha sin-carta' style='border-left:4px solid {color};'>"
                f"{cuerpo}</div>")
    return (f"<div class='hj-ficha' style='border-left:4px solid {color};'>"
            f"<div class='hj-carta'>{_carta_escalada(fila, 1.35)}</div>{cuerpo}</div>")


CSS_SUBIDAS = """
<style>
.st-key-hist_periodo [role="radiogroup"] { justify-content:center; }
.sb-fechas { text-align:center; color:#8b93a7; font-size:0.8rem; margin:2px 0 6px 0; }
.sb-titulo { display:flex; align-items:center; gap:14px; margin:18px 0 6px 0; }
.sb-titulo::before, .sb-titulo::after { content:""; flex:1; height:1px; }
.sb-titulo span { font-family:'Fraunces', Georgia, serif; font-size:1.25rem; font-weight:600;
                  letter-spacing:0.08em; text-transform:uppercase; padding:5px 18px; border-radius:10px; }
.sb-titulo.sube::before, .sb-titulo.sube::after { background:linear-gradient(90deg, transparent, rgba(74,222,128,0.45)); }
.sb-titulo.sube::after { background:linear-gradient(90deg, rgba(74,222,128,0.45), transparent); }
.sb-titulo.sube span { color:#4ade80; background:rgba(74,222,128,0.10); border:1px solid rgba(74,222,128,0.35); }
.sb-titulo.baja::before { background:linear-gradient(90deg, transparent, rgba(248,113,113,0.45)); }
.sb-titulo.baja::after { background:linear-gradient(90deg, rgba(248,113,113,0.45), transparent); }
.sb-titulo.baja span { color:#f87171; background:rgba(248,113,113,0.10); border:1px solid rgba(248,113,113,0.35); }
.sb-fila { display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; padding-top:12px;
           margin-bottom:6px; }
.sb-hueco { display:flex; flex-direction:column; align-items:center; gap:4px; }
.sb-pct { font-family:'Fraunces', Georgia, serif; font-size:1.05rem; font-weight:600; min-width:84px;
          text-align:center; padding:4px 12px; border-radius:8px; font-variant-numeric:tabular-nums; }
.sb-pct.sube { color:#4ade80; background:rgba(74,222,128,0.12); border:1px solid rgba(74,222,128,0.35); }
.sb-pct.baja { color:#f87171; background:rgba(248,113,113,0.12); border:1px solid rgba(248,113,113,0.35); }
</style>
"""
CARTAS_POR_FILA_SUBIDAS = 7


def _fila_cartas_cambio(marco, rotulo):
    """Una fila de cartas con los que más se han movido en el periodo. La carta
    lleva abajo lo que ha cambiado EN EL PERIODO (no solo hoy) y debajo el %."""
    if marco is None or marco.empty:
        return ""
    mercado = db['mercado'].dropna(subset=['Jugador'])
    filas = {(str(f['Jugador']).strip(), str(f['Equipo']).strip()): f for _, f in mercado.iterrows()}
    huecos = []
    for _, mov in marco.iterrows():
        # Si en el periodo suben menos de siete, la fila no se rellena con los
        # que bajan (ni al revés).
        if (mov['Cambio'] > 0) != (rotulo == "Suben"):
            continue
        fila = filas.get((str(mov['Jugador']).strip(), str(mov['Equipo']).strip()))
        if fila is None:
            continue           # ya no está en el juego: no hay carta que pintar
        fila = fila.copy()
        fila['Variación Diaria (€)'] = mov['Cambio']
        pct = mov['%']
        clase = 'sube' if mov['Cambio'] > 0 else 'baja'
        texto_pct = f"{pct:+.1f}%".replace('.', ',') if pd.notna(pct) else "—"
        huecos.append(f"<div class='sb-hueco'>{_carta_escalada(fila, 1.1)}"
                      f"<div class='sb-pct {clase}'>{texto_pct}</div></div>")
        if len(huecos) == CARTAS_POR_FILA_SUBIDAS:
            break
    if not huecos:
        return ""
    clase = 'sube' if rotulo == "Suben" else 'baja'
    flecha = '▲' if clase == 'sube' else '▼'
    return (f"<div class='sb-titulo {clase}'><span>{flecha} {rotulo}</span></div>"
            f"<div class='sb-fila'>{''.join(huecos)}</div>")


def ui_historico_filtros(df_hist):
    if df_hist.empty:
        return

    huella_hist = _huella_excel(resolver_excel_path())

    # 📈 Quién se ha movido, y en el plazo que elijas. Antes solo se veían las
    # rachas de días seguidos, que responden a otra pregunta: cuando uno abre
    # esto quiere saber quién ha subido hoy, esta semana o este mes.
    PERIODOS = {"Hoy": 1, "Última semana": 7, "Último mes": 30, "Todo el histórico": None}
    with st.expander("Subidas y bajadas"):
        periodo = st.radio("Periodo", list(PERIODOS), horizontal=True,
                           key="hist_periodo", label_visibility="collapsed")
        suben, bajan = cambios_de_valor(huella_hist, PERIODOS[periodo])

        if suben.empty and bajan.empty:
            st.caption("Todavía no hay dos días que comparar en ese periodo.")
        else:
            desde, hasta = suben.attrs.get('desde'), suben.attrs.get('hasta')
            fechas = (f"<div class='sb-fechas'>Del {pd.Timestamp(desde):%d/%m} al "
                      f"{pd.Timestamp(hasta):%d/%m}</div>"
                      if desde is not None and hasta is not None else "")
            st.markdown(CSS_SUBIDAS + fechas + _fila_cartas_cambio(suben, "Suben")
                        + _fila_cartas_cambio(bajan, "Bajan"), unsafe_allow_html=True)

    # 🏷️ Clave jugador+equipo: el histórico se filtraba por nombre, así que los
    # dos Moussa Diarra se mezclaban en la misma línea y salía un diente de
    # sierra saltando entre 170.000 € y 150.000 €.
    df_hist = _historico_con_hoy(df_hist).copy()
    df_hist['_clave'] = (df_hist['Jugador'].astype(str).str.strip() + '||'
                         + df_hist['Equipo'].astype(str).str.strip())

    # Sin filtros de posición ni de equipo: al histórico se viene a buscar a un
    # jugador por su nombre, y el buscador del desplegable ya hace ese trabajo.
    with st.container(border=True):
        df_hist_filtrado = df_hist

        repetidos_hist = set(
            df_hist_filtrado.drop_duplicates('_clave')['Jugador'].loc[
                df_hist_filtrado.drop_duplicates('_clave')['Jugador'].duplicated()]
        )
        etiquetas_hist, mapa_hist = [], {}
        for _, fila in df_hist_filtrado.drop_duplicates('_clave').sort_values('Jugador').iterrows():
            nombre = str(fila['Jugador'])
            etiqueta = f"{nombre} ({fila['Equipo']})" if nombre in repetidos_hist else nombre
            etiquetas_hist.append(etiqueta)
            mapa_hist[etiqueta] = fila['_clave']

        # 📈 Arranca con UN solo jugador: el que más ha subido hoy en euros de
        # toda la liga. Seis líneas de salida llenaban la gráfica de entrada, y
        # el que más sube es lo primero que uno quiere mirar al abrir esto.
        # (Antes de eso arrancaba con el primero por orden alfabético, que era
        # alguien al azar.)
        mercado_var = db['mercado'].dropna(subset=['Jugador']).copy()
        mercado_var['_var'] = pd.to_numeric(mercado_var['Variación Diaria (€)'], errors='coerce')
        mercado_var = mercado_var.dropna(subset=['_var']).sort_values('_var', ascending=False)

        por_defecto = []
        for _, lider in mercado_var.iterrows():
            clave_lider = (str(lider['Jugador']).strip() + '||' + str(lider['Equipo']).strip())
            etiqueta_lider = next((e for e in etiquetas_hist if mapa_hist[e] == clave_lider), None)
            if etiqueta_lider:
                por_defecto = [etiqueta_lider]
                break
        if not por_defecto and etiquetas_hist:
            por_defecto = etiquetas_hist[:1]

        if "hist_jugadores" not in st.session_state:
            st.session_state["hist_jugadores"] = por_defecto
        else:
            validos = [e for e in st.session_state["hist_jugadores"] if e in etiquetas_hist]
            st.session_state["hist_jugadores"] = validos if validos else por_defecto

        # 🔎 UN FORMULARIO, NO WIDGETS SUELTOS.
        # Streamlit vuelve a ejecutar el script ENTERO con cada interacción: las
        # once pestañas, sus tablas y sus gráficas. Por eso añadir un nombre al
        # desplegable tardaba tanto, y por eso tardaba otra vez al buscar: eran
        # dos recargas completas de la app.
        # Dentro de un formulario no se recarga nada hasta que se pulsa el
        # botón. Escribir y elegir jugadores es instantáneo —no sale de tu
        # navegador— y la única espera es la de dibujar, que es la que tiene
        # sentido esperar.
        # La gráfica es siempre la del valor de mercado: las otras métricas
        # (media, puntos acumulados, variación) ya están en la ficha de abajo.
        try:
            formulario = st.form("hist_buscador", border=False)
        except TypeError:          # Streamlit antiguo: el formulario siempre con borde
            formulario = st.form("hist_buscador")
        with formulario:
            try:
                c1, c2, c3 = st.columns([5, 1.4, 1.1], vertical_alignment="bottom")
            except TypeError:      # Streamlit antiguo: sin alineación vertical
                c1, c2, c3 = st.columns([5, 1.4, 1.1])
            c1.multiselect("Jugadores", etiquetas_hist, key="hist_jugadores")
            granularidad = c2.selectbox("Agrupar por",
                                        ["Diaria", "Semanal", "Mensual", "Anual"],
                                        key="hist_vista")
            with c3:
                buscar = st.form_submit_button("Buscar", type="primary",
                                               use_container_width=True)

    if buscar or 'hist_dibujados' not in st.session_state:
        st.session_state['hist_dibujados'] = list(st.session_state.get("hist_jugadores", []))
    jugadores_sel = [e for e in st.session_state['hist_dibujados'] if e in etiquetas_hist]

    if len(jugadores_sel) > len(COLORES_SERIES_HIST):
        st.warning(f"Has elegido {len(jugadores_sel)} jugadores y solo hay "
                   f"{len(COLORES_SERIES_HIST)} colores: a partir de ahí se repiten y la gráfica "
                   "se vuelve ilegible.")

    if not jugadores_sel:
        st.info("Elige al menos un jugador y pulsa Buscar.")
        return

    metrica_sel = "Valor de mercado"
    columna, formateador, titulo_eje = METRICAS_HISTORICO[metrica_sel]

    movimientos = movimientos_por_jugador(_huella_excel(resolver_excel_path()))

    fig_hist = go.Figure()
    resumenes = []
    for idx, etiqueta in enumerate(jugadores_sel):
        clave = mapa_hist.get(etiqueta)
        df_j = df_hist[df_hist['_clave'] == clave].dropna(subset=['Fecha']).sort_values('Fecha')
        if df_j.empty:
            continue
        serie = pd.to_numeric(df_j.set_index('Fecha')[columna], errors='coerce').dropna()
        if serie.empty:
            continue
        if granularidad == "Semanal":
            serie_plot = serie.resample('W').last().dropna()
        elif granularidad == "Mensual":
            serie_plot = serie.resample('ME').last().dropna()
        elif granularidad == "Anual":
            serie_plot = serie.resample('YE').last().dropna()
        else:
            serie_plot = serie
        color = COLORES_SERIES_HIST[idx % len(COLORES_SERIES_HIST)]
        fig_hist.add_trace(go.Scatter(
            x=serie_plot.index, y=serie_plot.values, mode='lines+markers', name=etiqueta,
            line=dict(color=color, width=3), marker=dict(size=7, color=color),
            # El número se pasa ya formateado en español: %{y:,.2f} lo escribía
            # al estilo inglés ("3,130,000.00") y sin el símbolo de la métrica.
            # Cada punto lleva debajo cuánto ha cambiado respecto al día anterior:
            # el valor suelto no dice si viene subiendo o cayendo.
            text=_texto_con_variacion(serie_plot, formateador),
            hovertemplate=f'<b>{etiqueta}</b><br>%{{x|%d/%m/%Y}}<br>%{{text}}<extra></extra>',
            hoverlabel=dict(bgcolor='#1a1a24', bordercolor=color, font=dict(color='#ffffff', size=13, family='Poppins')),
        ))
        # 🔴 Días en que ese jugador cambió de manos: punto grande y rojo sobre la
        # línea, con el detalle del movimiento al pasar el ratón.
        # ⚠️ La clave del registro de movimientos es una TUPLA (jugador, equipo) y
        # aquí se estaba buscando con el texto "Jugador||Equipo" que usa el
        # histórico. Nunca casaban, así que no salía ni un solo marcador.
        clave_mov = tuple(clave.split('||')) if isinstance(clave, str) and '||' in clave else clave
        for fecha_mov, tipo_mov, persona_mov, importe_mov, sobrepuja_mov in movimientos.get(clave_mov, []):
            marca = pd.Timestamp(fecha_mov)
            if marca not in serie.index:
                continue          # ese día no está importado en el histórico
            es_compra = tipo_mov.strip().lower() == 'compra'
            detalle = (f"{'🛒 Fichado por' if es_compra else '💸 Vendido por'} "
                       f"<b>{persona_mov}</b><br>{formato_euro(importe_mov)}")
            if es_compra and pd.notna(sobrepuja_mov):
                detalle += f"<br>Sobrepuja: {formato_euro(sobrepuja_mov)}"
            fig_hist.add_trace(go.Scatter(
                x=[marca], y=[float(serie.loc[marca])], mode='markers',
                name=f"{'Fichaje' if es_compra else 'Venta'} · {etiqueta}",
                showlegend=False,
                marker=dict(size=16, color='#ef4444' if es_compra else '#f59e0b',
                            line=dict(color='#ffffff', width=2), symbol='circle'),
                text=[f"<b>{etiqueta}</b><br>{detalle}"],
                hovertemplate='%{text}<br>%{x|%d/%m/%Y}<extra></extra>',
                hoverlabel=dict(bgcolor='#2a1216', bordercolor='#ef4444',
                                font=dict(color='#ffffff', size=13, family='Poppins')),
            ))

        resumenes.append((etiqueta, color, serie, clave_mov))

    fig_hist.update_layout(
        title=f"{metrica_sel} ({granularidad.lower()})",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Poppins", color="#fff"),
        yaxis_title=titulo_eje, xaxis_title="",
        margin=dict(l=40, r=40, t=60, b=40), height=440,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hoverlabel=dict(bgcolor='#1a1a24', font_size=13, font_family="Poppins", font_color="white"),
    )
    with st.container(border=True):
        st.plotly_chart(fig_hist, use_container_width=True)

    # 🪪 Una ficha por jugador: su carta, lo que vale hoy, cómo le va a quien lo
    # tiene desde que lo compró y un resumen de su temporada.
    mercado_hist = db['mercado'].dropna(subset=['Jugador'])
    filas_mercado = {(str(f['Jugador']).strip(), str(f['Equipo']).strip()): f
                     for _, f in mercado_hist.iterrows()}
    puestos = _puestos_por_posicion(mercado_hist)
    fichas = "".join(
        _ficha_historico_html(etiqueta, color, serie, clave_mov, movimientos,
                              filas_mercado.get(clave_mov), puestos)
        for etiqueta, color, serie, clave_mov in resumenes)
    st.markdown(CSS_FICHA_HISTORICO + f"<div class='hj-lista'>{fichas}</div>",
                unsafe_allow_html=True)


if _pagina == "Histórico":
    st.markdown("<div class='animate-fade-in'>", unsafe_allow_html=True)

    # 🏠✈️ Si el contador de PJ_Split no cuadra con el PJ del export, es que falta
    # una importación: mientras tanto, esos jugadores usan el reparto aproximado.
    try:
        _m = db['mercado']
        _desfasados = int(((_m['PJ'] > 0) & _m['PJ Casa'].isna()).sum())
    except Exception:
        _desfasados = 0
    if _desfasados:
        st.warning(
            f"{_desfasados} jugador/es tienen el desglose casa/fuera sin cuadrar con sus "
            "partidos jugados; sus medias en casa y fuera son aproximadas hasta la próxima "
            "ejecución del bot."
        )

    df_hist = cargar_historico_completo(_huella_excel(resolver_excel_path()))

    if df_hist.empty:
        st.info("Todavía no hay ningún bloque en la hoja 'Historico'. Ejecuta el bot, o "
                "usa «Importar hoy» en Mantenimiento, aquí abajo.")
    else:
        ui_historico_filtros(df_hist)

    # 🔧 MANTENIMIENTO, AL FINAL Y PLEGADO.
    # Estos dos botones eran lo primero que se veía al abrir la pestaña, con
    # ocho líneas explicando cuándo pulsarlos. Ya no hace falta: el bot importa
    # el día y reparte la jornada cada mañana. Se quedan por si hay que hacerlo
    # a mano o deshacer algo, que es lo que son ahora: herramientas de rescate,
    # no el flujo de cada día.
    st.divider()
    with st.expander("Mantenimiento del histórico"):
        with st.container(border=True):
            c_imp1, c_imp2, c_imp3 = st.columns([3, 1, 1])
            c_imp1.markdown("**Importar la foto de hoy**  \nGuarda los precios de hoy "
                        "como un bloque nuevo del histórico.")
            if c_imp2.button("📥 Importar hoy", use_container_width=True):
                nuevos_fichajes = actualizar_registro_fichajes()
                ok, msg = importar_dia_a_historico(db['mercado'])
                if ok:
                    st.success(msg)
                    if nuevos_fichajes:
                        st.info(f"🔒 {nuevos_fichajes} jugador/es nuevos en las plantillas: "
                                f"empieza su cuenta atrás de {DIAS_BLOQUEO_VENTA} días para poder venderlos.")
                    cargar_historico_completo.clear()
                    st.cache_data.clear()
                    # También la caché de recursos: el modelo de pujas usa
                    # @st.cache_resource y con st.cache_data.clear() no se enteraba,
                    # así que se entrenaba una vez al arrancar y no volvía a
                    # entrenarse en toda la sesión por muchas compras que añadieras.
                    st.cache_resource.clear()
                    st.session_state['app_ya_cargada'] = False
                    st.rerun()
                else:
                    st.warning(msg)
            if c_imp3.button("↩️ Deshacer último", use_container_width=True, help="Elimina el último bloque importado, por si te equivocaste"):
                ok, msg = deshacer_ultima_importacion()
                if ok:
                    fichajes_revertidos = revertir_registro_fichajes()
                    st.success(msg)
                    if fichajes_revertidos:
                        st.info(f"🔒 También se han quitado {fichajes_revertidos} alta/s de hoy del "
                                "registro de fichajes, para que su cuenta atrás no arranque antes de tiempo.")
                    cargar_historico_completo.clear()
                    st.cache_data.clear()
                    # También la caché de recursos: el modelo de pujas usa
                    # @st.cache_resource y con st.cache_data.clear() no se enteraba,
                    # así que se entrenaba una vez al arrancar y no volvía a
                    # entrenarse en toda la sesión por muchas compras que añadieras.
                    st.cache_resource.clear()
                    st.session_state['app_ya_cargada'] = False
                    st.rerun()
                else:
                    st.warning(msg)

    st.markdown("</div>", unsafe_allow_html=True)


# ⚽ Ya está: fuera la pantalla de carga.
# Va aquí abajo del todo, no antes de crear las pestañas. Streamlit ejecuta el
# contenido de las once pestañas DESPUÉS de dibujarlas, así que quitándola
# arriba se veía la app entera en negro mientras seguía calculando, y encima se
# podía cambiar de pestaña y no ver nada. Con el balón puesto hasta el final,
# cuando desaparece hay algo que mirar.
_pantalla_carga.empty()
st.session_state['app_ya_cargada'] = True
