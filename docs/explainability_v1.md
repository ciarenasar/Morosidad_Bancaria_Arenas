# Explicabilidad fuera de muestra v1

## Protocolo

Las explicaciones se calcularon exclusivamente sobre los 46 orígenes externos
de desarrollo. Para cada origen se volvió a estimar el modelo con la muestra
purgada y los hiperparámetros elegidos en el backtest. Se generaron 3.174
atribuciones —23 variables por 46 meses y tres modelos— y ninguna corresponde al
holdout.

La mayor diferencia entre una predicción registrada y su reconstrucción aditiva
fue `2,11e-7`, inferior a la tolerancia de `1e-6`.

![Drivers globales](../reports/figures/global_feature_importance.png)

## Drivers globales

| Modelo | Primer driver | Importancia | Segundo driver | Importancia | Tercer driver | Importancia |
|---|---|---:|---|---:|---|---:|
| ElasticNet | IMACEC anual | 30,2% | Mora media 12m | 20,2% | Crédito consumo real anual | 11,1% |
| XGBoost | Mora media 6m | 13,4% | Mora rezagada 12m | 13,3% | Mora media 3m | 11,0% |
| Random Forest | Mora media 6m | 21,0% | Mora media 12m | 10,1% | Mora rezagada 3m | 8,5% |

ElasticNet mezcla actividad, crédito y persistencia de mora. Los dos modelos de
árboles descansan principalmente en la historia de morosidad. Las escalas no se
comparan entre familias: ElasticNet y XGBoost usan contribuciones locales
absolutas; Random Forest usa reducción media de impureza.

La regularización de ElasticNet es agresiva. IMACEC tiene coeficiente distinto
de cero en 47,8% de los orígenes, la media móvil de mora a 12 meses en 41,3%, la
TPM promedio en 23,9% y el crédito real de consumo en solo 10,9%. Por tanto, el
ranking agregado está impulsado por subconjuntos de meses y no representa un
vector estable de coeficientes.

## Estabilidad entre bloques

La correlación de Spearman promedio entre los seis pares de bloques es:

| Modelo | Correlación media | Mínima | Máxima |
|---|---:|---:|---:|
| ElasticNet | 0,21 | -0,16 | 0,50 |
| XGBoost | 0,41 | 0,07 | 0,68 |
| Random Forest | 0,54 | 0,14 | 0,85 |

ElasticNet muestra la mayor rotación. En el bloque 2 domina IMACEC; en el 3, una
TPM de efecto muy pequeño; y en el 4, la media de mora a 12 meses y M1 real. En
los árboles hay más persistencia: la media de mora a seis meses está entre los
cinco primeros drivers en 75% de los bloques de XGBoost y en 100% de Random
Forest. Incluso así, ninguna familia exhibe un ranking plenamente estable.

## Meses críticos

La regla predefinida produce seis meses únicos: abril–agosto de 2020 por la caída
extraordinaria de la morosidad a seis meses y junio de 2021 por el mayor error
absoluto restante de ElasticNet.

![Pronósticos fuera de muestra](../reports/figures/oos_predictions_timeline.png)

Entre abril y agosto de 2020, ElasticNet queda reducido al intercepto y
pronostica aumentos pequeños, mientras el cambio observado cae entre 0,84 y 1,40
puntos porcentuales. XGBoost y Random Forest también anticipan aumentos y amplían
el error. Los modelos no capturan la ruptura asociada al período pandémico.

En junio de 2021, ElasticNet pronostica +0,767 pp frente a un resultado de
-0,244 pp. Sus mayores aportes positivos son IMACEC anual (+0,494 pp), media de
mora a seis meses (+0,289 pp) y media a 12 meses (+0,051 pp). El fuerte IMACEC
anual incorpora un efecto base posterior a la contracción de 2020; el modelo lo
interpreta como señal extrapolable y sobrestima la mora. Esta es una explicación
del comportamiento del algoritmo, no una afirmación causal.

## Conclusión

Los drivers son económicamente reconocibles, pero no estables. La historia de
mora domina los árboles y ElasticNet rota entre actividad, crédito, tasas y
persistencia. Esta inestabilidad, junto con el peor MAE frente a cambio cero,
refuerza que el modelo aprendido permanezca como challenger y que el holdout
siga cerrado.

Archivos auditables:

- `reports/tables/feature_attributions_oos.csv`.
- `reports/tables/feature_importance_global.csv`.
- `reports/tables/feature_importance_by_fold.csv`.
- `reports/tables/driver_rank_stability.csv`.
- `reports/tables/fold_rank_correlations.csv`.
- `reports/tables/critical_months.csv`.
- `data/metadata/explainability_v001.json`.
