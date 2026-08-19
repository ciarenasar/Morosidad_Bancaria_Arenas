# Cobertura conjunta y muestra modelable

## Resultado

| Componente | Cobertura útil |
|---|---:|
| Objetivo CMF | 148/148 meses |
| Fechas efectivas de publicación CMF | 148/148 meses |
| Series BCCh seleccionadas | 8 |
| Cobertura de cada serie BCCh | 148/148 meses |
| Valores de predictor faltantes después del corte as-of | 0 |
| Violaciones de `available_date` | 0 |
| Objetivos conocidos a seis meses | 142 |
| Variables del feature set v1 | 23 |
| Filas completas de desarrollo | 106 |

La base integrada tiene 148 filas, de las cuales 118 corresponden a desarrollo,
24 al holdout final y seis a pronósticos cuyo resultado a seis meses aún no es
observable.

## Predictores iniciales

1. IMACEC desestacionalizado.
2. Inflación anual IPC.
3. Tasa nacional de desempleo.
4. TPM promedio mensual.
5. Tipo de cambio observado promedio mensual.
6. Tasa promedio de créditos de consumo.
7. Colocaciones reales de consumo.
8. M1 real promedio.

El conjunto de fuentes es deliberadamente pequeño para una muestra de 118 meses
de desarrollo. Después de construir rezagos de hasta 12 meses quedan 106 filas
completas de desarrollo. Las transformaciones son deterministas y retrospectivas:
cada una termina en la observación que ya había superado el corte
`available_date` de la fecha de emisión. El holdout no interviene en la elección
de variables ni en las métricas de desarrollo.

La especificación completa se encuentra en `configs/features.toml` y el primer
backtest en [baseline_backtest_v1.md](baseline_backtest_v1.md).
