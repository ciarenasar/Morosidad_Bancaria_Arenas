# Model card v1

## Sistema evaluado

- Unidad: sistema bancario chileno agregado, cartera de consumo, frecuencia mensual.
- Fecha de observación: mes `t`; emisión: publicación CMF efectiva de `t`.
- Target principal: cambio de mora de 90 días o más entre `t` y `t+6`.
- Alerta secundaria: cambio h=6 superior al percentil 80 disponible en train.
- Desarrollo externo: 46 orígenes, marzo de 2020 a diciembre de 2023.
- Holdout reservado: enero de 2024 a diciembre de 2025, no evaluado.

## Campeón de regresión

El campeón es **cambio cero**, no un modelo ajustado. Pronostica que la variación
de mora h=6 será cero. Su MAE de desarrollo es 0,434 pp y su
RMSE es 0,566 pp.

ElasticNet completo es el challenger aprendido. Obtiene MAE
0,507 pp, una mejora relativa de
-16,8% frente al campeón. La
mejora negativa y el bootstrap por bloques justifican mantener cambio cero.

El mejor resultado descriptivo de ElasticNet por régimen ocurre en
`high_inflation` (6,5%)
y el peor en `lower_inflation`
(-40,0%). Estos cortes no
se usan para seleccionar el modelo.

## Challenger de alerta

La regresión logística es el mejor ranking de estrés: AP
0,771, ROC-AUC
0,787, recall
56,2% y precision
60,0%. Su Brier
(0,277) es peor que la prevalencia histórica
(0,248), por lo que no se presenta como una
probabilidad calibrada ni se promueve a alerta operativa.

## Variables y estimación

Los modelos aprendidos usan 23 variables de historia de mora, actividad,
inflación, desempleo, tasas, tipo de cambio, crédito, dinero y estacionalidad.
La imputación, el escalamiento y el ajuste ocurren dentro de cada muestra
temporal. Las etiquetas no publicadas se purgan antes de entrenar.

## Uso previsto

- Investigación académica sobre predictibilidad agregada de morosidad.
- Benchmark reproducible y diagnóstico de señales macrofinancieras.
- Priorización exploratoria de meses para revisión humana.

## Usos no previstos

- Scoring de personas, aprobación de crédito o decisiones automáticas.
- Inferencia causal o recomendación regulatoria definitiva.
- Uso de las probabilidades de estrés como probabilidades calibradas.
- Producción en tiempo real sin validación adicional y monitoreo de drift.

## Limitaciones materiales

- Solo 46 orígenes externos y dos episodios efectivos de estrés.
- Las series macro son el vintage vigente, no el vintage histórico completo.
- El período de evaluación incluye quiebres por pandemia e inflación.
- El análisis agregado no representa heterogeneidad entre bancos o carteras.
- El repositorio debe registrar un commit antes de una entrega versionada.

## Estado

- Campeón h=6: cambio cero.
- Challenger de regresión: ElasticNet completo.
- Challenger de ranking de estrés: regresión logística.
- Alerta operativa: no aprobada.
- Holdout: cerrado.
