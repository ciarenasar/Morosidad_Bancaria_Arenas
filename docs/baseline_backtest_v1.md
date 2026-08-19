# Backtest de benchmarks v1

## Diseño ejecutado

El experimento `consumption_h6_v001` pronostica el cambio en puntos porcentuales
de la morosidad de consumo a seis meses. La matriz contiene 23 variables: nivel,
rezagos, cambios y medias móviles de morosidad; diez señales macroeconómicas
transformadas; y estacionalidad mensual.

Las transformaciones macro terminan en la observación seleccionada por el corte
`available_date` de cada fecha de emisión. Se obtuvieron 136 filas completas:
106 de desarrollo, 24 de holdout y seis filas de pronóstico.

El backtest usa solo desarrollo y comprende 46 orígenes mensuales entre marzo de
2020 y diciembre de 2023. Se ajusta cada mes con ventana expansiva y purga del
objetivo. El entrenamiento efectivo crece de 55 a 100 filas y se purgan como
máximo cinco etiquetas por origen.

## Resultados agregados de desarrollo

| Benchmark | MAE (pp) | RMSE (pp) | MedAE (pp) | Dirección | Mejora MAE vs. cero |
|---|---:|---:|---:|---:|---:|
| Cambio cero | **0,434** | **0,566** | **0,298** | 0,0% | 0,0% |
| Último cambio conocido | 0,554 | 0,712 | 0,421 | **67,4%** | -27,7% |
| Promedio de 12 cambios | 0,618 | 0,727 | 0,594 | 54,3% | -42,5% |
| Ingenuo estacional | 0,730 | 0,822 | 0,680 | 43,5% | -68,3% |
| Regresión OLS autorregresiva | 0,628 | 0,795 | 0,521 | 60,9% | -44,8% |

El cambio cero es el benchmark dominante en MAE, RMSE y error absoluto mediano.
Esto no significa que anticipe la dirección: por definición pronostica una
variación nula y obtiene 0% bajo la regla estricta de signo. El último cambio
conocido ofrece la mayor exactitud direccional, pero con un MAE 27,7% peor.

La OLS supera al cambio cero solo en el bloque marzo de 2022–febrero de 2023;
no lo hace de manera estable. Los modelos ML se evaluaron posteriormente en estos
mismos orígenes; véase [ml_backtest_v1.md](ml_backtest_v1.md).

Los resultados reproducibles están en
[`reports/tables/baseline_metrics_development.csv`](../reports/tables/baseline_metrics_development.csv)
y las predicciones origen por origen en
[`reports/tables/baseline_predictions_development.csv`](../reports/tables/baseline_predictions_development.csv).

## Alcance

La evaluación es pseudo-real-time: respeta calendarios de publicación, pero las
series del Banco Central corresponden a su último vintage. No se han reportado
resultados finales de holdout.
