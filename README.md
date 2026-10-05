# Plataforma de análisis y predicción para Biwenger

Asistente para una liga fantasy de fútbol: lleva la contabilidad de los rivales, predice sus pujas y recomienda qué fichar para reforzar el once y cuánto pujar.

Proyecto personal en Python que funciona a diario con los datos reales de una liga de diez participantes.

**Tecnologías:** Python · Streamlit · pandas · scikit-learn · SQLite · Plotly · API REST

## Qué hace

- **11 módulos de análisis:** resumen, participantes, calendario y clasificación, auditoría de movimientos, plantillas, mercado, scouting, inteligencia de rivales, cara a cara, comparador de jugadores e histórico.
- **Predictor de pujas en dos etapas (Gradient Boosting):** primero estima si cada rival pujará por un jugador y después cuánto ofrecerá. Con validación temporal (cada subasta se predice solo con las anteriores) alcanza un AUC de 0,70, frente a 0,59 de la referencia.
- **Recomendaciones:** fichajes que mejoran el once donde es más débil, puja recomendada para ganar la subasta y ventas con las que financiarla.
- **Motor de puntos esperados** que se recalibra solo con las actuaciones reales: precio, fuerza del equipo, rival, racha y localía.
- **Actualización automática diaria:** un bot descarga el mercado y los movimientos de la liga por API y los guarda en una base de datos SQLite, con copias de seguridad rotativas.

## Cómo está organizado

| Archivo | Qué hace |
|---|---|
| `app.py` | Aplicación web en Streamlit |
| `bot_diario.py` | Bot que actualiza los datos cada mañana (pensado para el Programador de tareas de Windows) |
| `api_biwenger.py` | Descarga de jugadores y equipos desde la API de Biwenger |
| `almacen.py` | Capa de datos sobre SQLite |
| `calculos.py` | Cálculos derivados en Python |
| `migrar_a_sqlite.py` | Migración única del Excel original a SQLite |

El proyecto empezó como un Excel con fórmulas. Al crecer, los datos se migraron a SQLite y las fórmulas se reescribieron en Python, para que la app y el bot no dependan de recalcular el libro.

## Puesta en marcha

1. Instala las dependencias: `pip install -r requirements.txt`
2. Copia `config_bot.example.json` como `config_bot.json` y escribe tus credenciales de Biwenger. Ese archivo no se sube al repositorio.
3. Genera la base de datos inicial con `migrar_a_sqlite.py` y mantenla al día con `python bot_diario.py` (o `Ejecutar_Bot.bat`).
4. Abre la app con `streamlit run app.py` (o `Abrir_Biwenger.bat`).

Está pensado para mi propia liga, así que usarlo en otra requiere generar antes su base de datos.

## Privacidad y derechos

El repositorio no incluye la base de datos de la liga, las credenciales ni las imágenes de jugadores y escudos, que pertenecen a sus propietarios.

## Autor

Jorge Hidalgo Puyol · [LinkedIn](https://www.linkedin.com/in/jorge-hidalgo-puyol)
