# Agente Financiero — Proyecto v4

Combina lo mejor de las 2 versiones anteriores:
  - **De la v2**: datos locales en DuckDB, cargados desde tus archivos
    exportados manualmente (mayor_*.txt, balance_mayoreo_*.txt, etc.) —
    sin depender de que Fabric esté sincronizado al día.
  - **De la v3**: la lógica de clasificación validada trabajando contra
    Fabric — el mapeo REAL de cuentas por empresa (extraído de los
    archivos gyp.xlsx de cada una: Cofersa, Prisma, Mundial, Febeca,
    Sillaca, Beval), el ajuste de signo de cuentas de ingreso, los 3
    subtotales calculados (Gastos Operativos, Ganancia Operativa, Semi
    Neto), y toda la interfaz mejorada (sin dashboard automático al
    entrar, selector de partidas en cajitas, botón de "Analizar con IA"
    fijo arriba a la derecha).

## Diferencia clave vs. la v3

Como esto usa archivos locales (no una conexión en vivo a Fabric), la
"foto" de los datos es de cuando se generaron esos archivos — no vas a
ver el problema de sincronización de agosto que encontramos en Fabric,
pero tampoco vas a tener datos más recientes que esa foto hasta que
vuelvas a cargar archivos actualizados.

## Instalación y uso

```bash
py -m pip install -r requirements.txt
python 06_cargar_todo.py        # primera vez, o cuando lleguen archivos nuevos
$env:ANTHROPIC_API_KEY="tu-key-aqui"
python -m streamlit run app.py
```

## Estructura de archivos

| Archivo | Qué hace |
|---|---|
| `01_cargar_catalogos.py` a `05_cargar_manual_cuentas.py` | Cargadores de datos (idénticos a la v2) |
| `13_cargar_presupuesto.py` | Carga el presupuesto plano |
| `09_cte_clasificacion.py` | El mapeo REAL de las 6 empresas + la lógica de clasificación |
| `12_crear_vista.py` | Crea la vista `mayor_gyp_clasificado` en la base — el agente de IA la consulta directo |
| `06_cargar_todo.py` | Corre todo el pipeline de carga de una vez, en el orden correcto |
| `07_sql_tool.py` | Guardarraíles de SQL (solo SELECT) |
| `08_system_prompt.py` | Las reglas de negocio para el agente de IA |
| `09_agente_loop.py` | El loop de tool-use con la API de Claude |
| `10_dashboard.py` | El dashboard principal (con subtotales) |
| `11_conversaciones.py` | Guardar/cargar conversaciones por usuario |
| `14_dashboard_detalle.py` | Las 4 vistas del detalle por partida |
| `app.py` | La interfaz de Streamlit |

## ⚠️ Hallazgo conocido (dato de origen, no un bug)

Para Cofersa, la columna Centro de Costo en `asientos_de_planificacion.xlsx`
tiene algunas fechas del año 2000 en vez de códigos reales — no afecta los
montos totales, solo se ve raro en la pestaña "Tendencia y Centro de
Costo" si entras a una categoría de Cofersa. Es un tema del archivo de
origen, no de la lógica de esta app.

## Pendiente

- Prisma sigue con el mismo pendiente que en la v3 (relacionado con
  "Prisma CR") — Personal y Gastos Varios pueden verse altos.
- Renta Bruta de Cofersa (Ingresos Mercantiles, Merma) tiene volatilidad
  real conocida (rebates de proveedores, provisiones contabilizadas un
  mes tarde) — no es un error de clasificación.
