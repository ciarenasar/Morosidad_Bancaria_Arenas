# Alerta de estrés de morosidad v1

## Objetivo y definición

El experimento evalúa una alerta temprana para aumentos inusualmente altos de
la morosidad de consumo a seis meses. En cada fecha de emisión se define estrés
como:

```text
cambio de mora h=6 > percentil 80 de los cambios h=6 disponibles en train
```

El percentil se calcula después de purgar las etiquetas que la CMF todavía no
había publicado. Cambia entre 0,169 y 0,292 puntos porcentuales durante la
evaluación. El valor futuro usado para determinar el evento nunca interviene en
el umbral.

Se utilizaron los mismos 46 orígenes externos de desarrollo, entre marzo de
2020 y diciembre de 2023. Hubo 16 eventos, equivalentes a una prevalencia de
34,8%. Quince forman un episodio continuo entre septiembre de 2021 y noviembre
de 2022; el restante corresponde a agosto de 2023. El holdout no participa.

## Protocolo

Se compararon prevalencia histórica, regresión logística regularizada, Random
Forest y XGBoost sobre las 23 variables congeladas. Para cada clasificador:

- los hiperparámetros se seleccionaron por `Average Precision` en 24 orígenes
  internos temporales y purgados;
- el umbral operativo se seleccionó por F1 entre 0,20 y 0,80;
- el modelo se reestimó mensualmente;
- la selección se renovó solamente al comenzar cada bloque externo.

En total se evaluaron 1.824 predicciones internas, 76 configuraciones y 84
combinaciones de umbral. La regresión logística eligió un umbral de 0,20 en los
cuatro bloques.

![Evaluación de la alerta](../reports/figures/stress_alert_evaluation.png)

## Resultados agregados

`Average Precision` mide calidad del ranking completo; la columna `Precision`
mide la proporción de alertas emitidas que fueron correctas al aplicar el
umbral operativo.

| Modelo | AP | ROC-AUC | Brier | Precision | Recall | F1 | Balanced accuracy | Tasa de alertas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Prevalencia histórica | 0,339 | 0,475 | **0,248** | 0,0% | 0,0% | 0,000 | 0,500 | 0,0% |
| Regresión logística | **0,771** | **0,788** | 0,277 | **60,0%** | 56,3% | 0,581 | **0,681** | 32,6% |
| Random Forest | 0,466 | 0,673 | 0,254 | 41,0% | **100,0%** | 0,582 | 0,617 | 84,8% |
| XGBoost | 0,460 | 0,642 | 0,299 | 48,0% | 75,0% | **0,585** | 0,658 | 54,3% |

La regresión logística es claramente el mejor ranking, pero sus probabilidades
son extremas: 31 de 46 quedan bajo 0,20 con probabilidad media 0,003 aunque su
frecuencia de estrés es 22,6%; otras 15 quedan sobre 0,80 con probabilidad media
0,991 y frecuencia observada de 60,0%. Por ello no debe interpretarse como una
probabilidad calibrada.

Random Forest detecta los 16 eventos, pero genera 23 falsas alarmas y clasifica
84,8% de los meses como estrés. XGBoost ofrece un compromiso intermedio, aunque
su ranking y Brier son inferiores a los de la logística y la prevalencia,
respectivamente.

## Estabilidad temporal y detección de episodios

El primer bloque, marzo de 2020–febrero de 2021, no contiene eventos, por lo que
AP y ROC-AUC no están definidos allí. La regresión logística alcanza AP=1,0 en
los dos bloques centrales y solo 0,143 en el último. El resultado agregado está,
por tanto, dominado por el episodio continuo de 2021–2022.

| Episodio | Modelo | Primera detección correcta | Retraso | Recall del episodio |
|---|---|---|---:|---:|
| Sep-2021 a nov-2022 | Logística | Mar-2022 | 6 meses | 60,0% |
| Sep-2021 a nov-2022 | Random Forest | Sep-2021 | 0 meses | 100,0% |
| Sep-2021 a nov-2022 | XGBoost | Ene-2022 | 4 meses | 73,3% |
| Ago-2023 | Logística | No detectado | — | 0,0% |
| Ago-2023 | Random Forest | Ago-2023 | 0 meses | 100,0% |
| Ago-2023 | XGBoost | Ago-2023 | 0 meses | 100,0% |

Cada verdadero positivo anticipa por construcción en seis meses el cierre del
horizonte pronosticado. El retraso de la tabla se refiere al inicio de la racha
de orígenes clasificados como estrés, no al mes `t+6`.

## Incertidumbre de calibración

La diferencia de Brier se define como pérdida del clasificador menos pérdida de
la prevalencia histórica. Se aplicó bootstrap móvil circular con bloques de
seis meses y 10.000 réplicas.

| Modelo | Diferencia Brier | IC 95% por bloques | Prob. de mejorar | Conclusión |
|---|---:|---:|---:|---|
| Regresión logística | +0,029 | [-0,187; +0,217] | 38,3% | Inconcluso |
| Random Forest | +0,006 | [-0,218; +0,212] | 47,1% | Inconcluso |
| XGBoost | +0,051 | [-0,192; +0,292] | 34,3% | Inconcluso |

Ningún clasificador mejora de forma concluyente el Brier del benchmark. La
muestra efectiva contiene solo dos episodios, de modo que 16 etiquetas
positivas no equivalen a 16 eventos independientes.

## Decisión

- La regresión logística queda como challenger de ranking para investigación.
- No se promueve ningún modelo como probabilidad calibrada o alerta operativa.
- Random Forest solo sería defendible si omitir un evento tuviera un costo muy
  superior al de una falsa alarma, hipótesis que el curso aún no cuantifica.
- El holdout permanece cerrado.

Archivos auditables:

- `reports/tables/stress_alert_predictions_development.csv`.
- `reports/tables/stress_alert_tuning_development.csv`.
- `reports/tables/stress_alert_threshold_tuning_development.csv`.
- `reports/tables/stress_alert_metrics_development.csv`.
- `reports/tables/stress_alert_calibration_development.csv`.
- `reports/tables/stress_alert_brier_bootstrap.csv`.
- `reports/tables/stress_alert_errors_development.csv`.
- `reports/tables/stress_alert_episode_detection.csv`.
- `data/metadata/stress_alert_v001.json`.
