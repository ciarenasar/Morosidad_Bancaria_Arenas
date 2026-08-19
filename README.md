# Pronóstico de morosidad bancaria en Chile

Proyecto del curso de Finanzas para pronosticar, con información disponible en
tiempo real, el cambio a seis meses de la morosidad de 90 días o más de la
cartera de consumo del sistema bancario chileno.

> Esta es la copia académica `Morosidad_bancaria_arenas`, reestructurada según
> el estándar del curso. No contiene los entregables finales ni credenciales
> locales.

## Estado

Los diez hitos implementan el proyecto completo, desde la construcción de datos
hasta la entrega final:

- definición del MVP y decisiones metodológicas;
- catálogo inicial de fuentes;
- carga segura de credenciales desde `.env`;
- cliente de APIBEST de la CMF con ventanas máximas de 12 meses;
- calendario efectivo de publicación reconstruido desde comunicados CMF/SBIF;
- cliente de la BDE y ocho predictores macroeconómicos con cobertura completa;
- almacenamiento inmutable de respuestas crudas y manifiesto con hash SHA-256;
- integración point-in-time con auditoría automática de `available_date`;
- conjunto v1 de 23 variables reproducibles;
- validación expansiva mensual con purga de etiquetas aún no publicadas;
- cinco benchmarks evaluados exclusivamente sobre desarrollo;
- ElasticNet, Random Forest y XGBoost con selección interna temporal;
- comparación parsimoniosa y bootstrap por bloques para errores solapados;
- explicabilidad fuera de muestra y análisis de meses críticos;
- robustez en horizontes de 3, 6 y 12 meses con ventanas expansiva y móvil;
- alerta de estrés h=6 con target, selección y umbral estrictamente temporales;
- evaluación por regímenes, model card y manifiesto reproducible con SHA-256;
- informe final, presentación para defensa y guía de entrega;
- pruebas unitarias de configuración, fechas y seguridad de secretos.

La auditoría ejecutada el 17 de agosto de 2026 encontró 148 observaciones
mensuales continuas entre marzo de 2014 y junio de 2026. Véase
[docs/data_coverage.md](docs/data_coverage.md).

## Estructura

```text
data/       Datos raw inmutables, externos y capas procesadas
notebooks/  Espacio para exploración y desarrollo interactivo
src/        Código modular reutilizable
models/     Artefactos serializados y metadatos de modelos
reports/    Figuras y tablas analíticas
tests/      Pruebas automatizadas
configs/    Protocolos y parámetros versionados
docs/       Diseño, decisiones, resultados y reproducción
scripts/    Utilidades de construcción
```

## Notebooks reproducibles

Los notebooks siguen el orden lógico del estudio:

1. `00_reproduccion_completa.ipynb`: entrada al pipeline y veredicto de reproducción.
2. `01_datos_y_diseno_point_in_time.ipynb`: cobertura y auditoría de disponibilidad.
3. `02_validacion_modelos_y_robustez.ipynb`: benchmarks, ML, horizontes y drivers.
4. `03_alerta_de_estres_y_conclusiones.ipynb`: alerta, controles y conclusión final.

Para reconstruir el proyecto, comparar resultados y ejecutar las pruebas:

```powershell
python scripts/run_reproduction.py
python scripts/execute_notebooks.py
```

El primer script no requiere acceso a internet: utiliza las respuestas crudas
versionadas en `data/raw` y mantiene cerrado el holdout.

## Inicio rápido

Requiere Python 3.11 o posterior. Desde la raíz del repositorio:

```powershell
Copy-Item .env.example .env
# Complete .env localmente; el archivo está excluido de Git.
$env:PYTHONPATH = "src"
python -m morosidad_bancaria check-config
python -m morosidad_bancaria download-cmf --from-date 2025-01-01 --to-date 2025-12-31
python -m morosidad_bancaria audit-cmf
python -m morosidad_bancaria download-cmf-calendar
python -m morosidad_bancaria build-cmf-calendar
python -m morosidad_bancaria download-bcch-catalog
python -m morosidad_bancaria download-bcch-series
python -m morosidad_bancaria audit-bcch
python -m morosidad_bancaria build-modeling-base
python -m morosidad_bancaria build-features
python -m morosidad_bancaria backtest-baselines
python -m morosidad_bancaria backtest-ml
python -m morosidad_bancaria analyze-robustness
python -m morosidad_bancaria explain-models
python -m morosidad_bancaria analyze-horizons
python -m morosidad_bancaria backtest-stress
python -m morosidad_bancaria close-technical
python -m unittest discover -s tests -v
```

Cuando los datos raw ya están disponibles, todo el análisis puede regenerarse
sin acceso a internet con:

```powershell
python -m morosidad_bancaria run-all-local
```

También puede instalarse en modo editable:

```powershell
python -m pip install -e .
morosidad check-config
```

Las credenciales pueden escribirse con o sin comillas. El programa nunca las
incluye en rutas, manifiestos ni mensajes de consola.

## Diseño de datos

Cada consulta se guarda en `data/raw/cmf_best/` sin transformar. El archivo
`data/metadata/download_manifest.jsonl` registra fecha de descarga, rango
solicitado, estado HTTP, tamaño y hash del contenido. Las capas `interim` y
`processed` se reconstruyen de forma determinista a partir de esas respuestas.

La definición metodológica está en [docs/project_charter.md](docs/project_charter.md),
el primer resultado en
[docs/baseline_backtest_v1.md](docs/baseline_backtest_v1.md), la comparación ML
en [docs/ml_backtest_v1.md](docs/ml_backtest_v1.md) y el análisis de estabilidad
en [docs/robustness_v1.md](docs/robustness_v1.md). El análisis de drivers está en
[docs/explainability_v1.md](docs/explainability_v1.md), la robustez por horizonte
en [docs/horizon_robustness_v1.md](docs/horizon_robustness_v1.md) y la alerta de
estrés en [docs/stress_alert_v1.md](docs/stress_alert_v1.md). Las decisiones
permanentes están en [docs/decisions](docs/decisions). El estado final de los
modelos está en [docs/model_card_v1.md](docs/model_card_v1.md), el cierre por
regímenes en [docs/technical_closure_v1.md](docs/technical_closure_v1.md) y la
ejecución completa en [docs/reproduction.md](docs/reproduction.md).

## Entregables excluidos

Los artefactos finales del hito 10 no forman parte de esta copia. Se conserva
la guía de lectura, defensa y verificación en
[docs/final_delivery.md](docs/final_delivery.md) como documentación del cierre.

El resultado principal es deliberadamente parsimonioso: para el horizonte de
seis meses, ningún modelo aprendido supera de manera robusta al benchmark de
cambio cero. ElasticNet se conserva como challenger de investigación y la
alerta de estrés queda como herramienta exploratoria, no operativa.

## Limitación de vintage

La BDE entrega la versión vigente de sus series, no la versión que se veía en
cada fecha histórica. La selección de meses respeta `available_date`, pero los
valores revisados pueden conservar un sesgo de vintage. Esta limitación está
documentada y no debe confundirse con *look-ahead* por fecha de publicación.
