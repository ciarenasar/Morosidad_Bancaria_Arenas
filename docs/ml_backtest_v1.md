# Backtest de modelos ML v1

## Diseño

ElasticNet, Random Forest y XGBoost se evaluaron sobre los mismos 46 orígenes
mensuales de desarrollo usados por los benchmarks, entre marzo de 2020 y
diciembre de 2023. Los tres modelos usan las 23 variables de
`consumption_h6_v001`.

La selección de hiperparámetros es temporal y anidada: se realiza al inicio de
cada uno de los cuatro bloques externos con 12 orígenes internos purgados. Los
modelos se reestiman mensualmente después de la selección. Se ejecutaron 112
combinaciones modelo-bloque y 1.344 predicciones internas. El holdout aportó cero
filas a todo el proceso.

## Comparación agregada de desarrollo

| Modelo | MAE (pp) | RMSE (pp) | MedAE (pp) | Dirección | Mejora MAE vs. cero |
|---|---:|---:|---:|---:|---:|
| Cambio cero | **0,434** | **0,566** | **0,298** | 0,0% | 0,0% |
| ElasticNet | 0,507 | 0,635 | 0,440 | 41,3% | -16,8% |
| XGBoost | 0,537 | 0,677 | 0,484 | 41,3% | -23,8% |
| Último cambio conocido | 0,554 | 0,712 | 0,421 | **67,4%** | -27,7% |
| Random Forest | 0,584 | 0,734 | 0,534 | 52,2% | -34,6% |
| Promedio de 12 cambios | 0,618 | 0,727 | 0,594 | 54,3% | -42,5% |
| OLS autorregresiva | 0,628 | 0,795 | 0,521 | 60,9% | -44,8% |
| Ingenuo estacional | 0,730 | 0,822 | 0,680 | 43,5% | -68,3% |

ElasticNet es el mejor modelo aprendido, pero su MAE es 16,8% peor que el
benchmark de cambio cero. Random Forest supera al cambio cero en los bloques 2 y
3, y XGBoost en el bloque 3; ninguno mantiene esa ventaja en todo el período. En
el último bloque, cuando los cambios reales son pequeños, los árboles producen
errores especialmente grandes.

## Decisión provisional

El cambio cero permanece como campeón de desarrollo. ElasticNet queda como
challenger aprendido por ser el modelo ML con menor MAE y menor RMSE. La revisión
posterior de estabilidad y parsimonia está en
[robustness_v1.md](robustness_v1.md); tampoco justifica abrir el holdout.

Resultados auditables:

- `reports/tables/model_comparison_development.csv`: métricas por bloque y
  agregadas para los ocho modelos.
- `reports/tables/ml_predictions_development.csv`: pronósticos externos.
- `reports/tables/ml_tuning_development.csv`: todas las combinaciones internas y
  la opción seleccionada en cada bloque.
- `data/metadata/ml_backtest_v001.json`: versiones, orígenes y reglas de
  evaluación.

## Limitación

La evaluación sigue siendo pseudo-real-time porque las series del Banco Central
son de último vintage. La comparación tampoco constituye evidencia estadística
definitiva: hay solo 46 errores externos y el horizonte de seis meses genera
solapamiento entre resultados consecutivos.
