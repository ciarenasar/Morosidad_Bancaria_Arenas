# Robustez por horizonte y ventana v1

## Pregunta

Se comprobó si el desempeño cambia al pronosticar la variación de morosidad a
3, 6 o 12 meses y al usar una ventana expansiva o una ventana móvil de 60 meses
calendario. La comparación se limitó al campeón cambio cero y al challenger
ElasticNet completo ya definidos. Todos los resultados corresponden a los
mismos 46 orígenes externos entre marzo de 2020 y diciembre de 2023; el holdout
no participa.

## Protocolo point-in-time

Para cada horizonte se construyó la etiqueta `mora(t+h) - mora(t)` y se asignó
como fecha de disponibilidad la publicación CMF efectiva de `t+h`. Antes de
ajustar cada pronóstico se purgaron las etiquetas que todavía no estaban
publicadas.

La ventana móvil conserva primero los meses de observación entre `t-60` y
`t-1`, y después aplica la purga. Por ello contiene 58 observaciones utilizables
en h=3, 55 en h=6 y 49 en h=12. La ventana expansiva crece, respectivamente,
de 58 a 103, de 55 a 100 y de 49 a 94 observaciones. La purga máxima fue de 2,
5 y 11 meses, coherente con cada horizonte.

ElasticNet vuelve a seleccionar sus hiperparámetros dentro de cada bloque con
validación temporal purgada. El caso h=6 expansivo reproduce exactamente las
46 predicciones del experimento principal.

![Robustez por horizonte](../reports/figures/horizon_robustness.png)

## Resultados agregados

| Horizonte | Ventana | MAE cero (pp) | MAE ElasticNet (pp) | Mejora vs. cero | Dirección correcta |
|---:|---|---:|---:|---:|---:|
| 3 | Expansiva | 0,246 | 0,287 | -16,7% | 26,1% |
| 3 | Móvil | 0,246 | 0,296 | -20,5% | 30,4% |
| 6 | Expansiva | 0,434 | 0,507 | -16,8% | 41,3% |
| 6 | Móvil | 0,434 | 0,522 | -20,4% | 37,0% |
| 12 | Expansiva | 0,660 | **0,643** | **+2,5%** | **82,6%** |
| 12 | Móvil | 0,660 | 0,685 | -3,9% | 78,3% |

El horizonte de tres meses no aporta señal útil para ElasticNet. El resultado a
seis meses confirma el backtest principal. A doce meses aparece una señal
direccional interesante y una mejora pequeña con ventana expansiva, pero esta
ventaja agregada no basta para declarar superioridad.

## Incertidumbre frente a cambio cero

Se aplicó bootstrap móvil circular a la diferencia mensual de error absoluto.
El largo del bloque coincide con cada horizonte y se usaron 10.000 réplicas.

| Horizonte | Ventana | Diferencia MAE (pp) | IC 95% por bloques | Prob. de mejora | Conclusión |
|---:|---|---:|---:|---:|---|
| 3 | Expansiva | +0,041 | [+0,008; +0,086] | 0,3% | Peor que cero |
| 3 | Móvil | +0,050 | [+0,015; +0,101] | 0,0% | Peor que cero |
| 6 | Expansiva | +0,073 | [-0,021; +0,186] | 7,0% | Inconcluso |
| 6 | Móvil | +0,089 | [-0,032; +0,241] | 8,8% | Inconcluso |
| 12 | Expansiva | -0,017 | [-0,235; +0,153] | 53,8% | Inconcluso |
| 12 | Móvil | +0,026 | [-0,336; +0,295] | 40,7% | Inconcluso |

La mejora h=12 expansiva depende del período. ElasticNet pierde ligeramente en
los dos primeros bloques, gana con fuerza entre marzo de 2022 y febrero de 2023
y vuelve a perder en el último bloque. El intervalo amplio refleja esa
inestabilidad.

## Comparación directa de ventanas

La diferencia se define como MAE móvil menos MAE expansivo. Los tres estimadores
son positivos: +0,009 pp en h=3, +0,016 pp en h=6 y +0,042 pp en h=12. Sus
intervalos de 95% contienen cero, por lo que no hay evidencia concluyente de que
una ventana móvil mejore la capacidad predictiva.

## Decisión

- El cambio cero permanece como campeón para h=6.
- ElasticNet a h=3 se descarta bajo este protocolo.
- h=12 expansivo queda como hipótesis secundaria para datos futuros, no como
  modelo promovido.
- La ventana expansiva sigue siendo la especificación de referencia.
- El holdout permanece cerrado.

Archivos auditables:

- `reports/tables/horizon_robustness_predictions.csv`.
- `reports/tables/horizon_robustness_tuning.csv`.
- `reports/tables/horizon_robustness_metrics.csv`.
- `reports/tables/horizon_robustness_bootstrap.csv`.
- `reports/tables/horizon_window_comparison.csv`.
- `data/metadata/horizon_robustness_v001.json`.
