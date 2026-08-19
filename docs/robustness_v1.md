# Estabilidad y parsimonia v1

## Pregunta

Se evaluó si reducir la dimensión de ElasticNet corrige su desventaja frente al
cambio cero y si esa desventaja es estable ante la dependencia del horizonte de
seis meses. Todas las comparaciones usan los mismos 46 orígenes de desarrollo;
el holdout no participa.

## Especificaciones predefinidas

| ElasticNet | Variables | MAE (pp) | Mejora vs. cero |
|---|---:|---:|---:|
| Completo | 23 | **0,507** | -16,8% |
| Núcleo autorregresivo | 5 | 0,519 | -19,6% |
| Núcleo macro | 8 | 0,664 | -53,1% |
| Núcleo mixto | 10 | 0,682 | -57,2% |

La parsimonia no mejora el modelo. El conjunto autorregresivo de cinco variables
se acerca al completo, pero tampoco supera al cambio cero. Los núcleos macro y
mixto reaccionan con especial intensidad durante marzo de 2020–febrero de 2021.

## Incertidumbre frente a cambio cero

Se aplicó bootstrap móvil circular a la diferencia mensual de error absoluto,
con bloques de seis meses y 10.000 réplicas.

| Modelo | Diferencia MAE (pp) | IC 95% por bloques | Prob. bootstrap de mejora | Meses ganados |
|---|---:|---:|---:|---:|
| ElasticNet completo | +0,073 | [-0,019; +0,186] | 6,6% | 28,3% |
| ElasticNet AR 5 | +0,085 | [-0,010; +0,191] | 4,2% | 26,1% |
| XGBoost | +0,103 | [-0,043; +0,276] | 9,5% | 34,8% |
| Random Forest | +0,150 | [-0,057; +0,406] | 9,8% | 37,0% |

Los cuatro intervalos incluyen cero: con esta muestra no se puede declarar una
diferencia concluyente al 95%. Sin embargo, los estimadores puntuales, las bajas
frecuencias de mejora bootstrap y las tasas de victoria mensual inferiores a
50% favorecen mantener el cambio cero como campeón.

El promedio móvil, el ElasticNet macro, el ElasticNet mixto y el ingenuo
estacional sí presentan intervalos completamente positivos y quedan clasificados
como peores que el cambio cero bajo este protocolo.

## Sensibilidad al período pandémico

Al excluir marzo de 2020–febrero de 2021 quedan 34 orígenes. El cambio cero logra
un MAE aproximado de 0,361 pp y ElasticNet completo 0,454 pp: la diferencia de
+0,093 pp sigue favoreciendo al benchmark. Por tanto, el resultado agregado no
se explica únicamente por el primer bloque pandémico.

ElasticNet presenta sesgo medio de +0,048 pp, error absoluto percentil 90 de
0,963 pp y máximo de 1,454 pp. Estos valores se conservarán como referencia para
los análisis de drivers y meses críticos.

## Decisión

- Campeón de desarrollo: cambio cero.
- Challenger aprendido: ElasticNet completo de 23 variables.
- Alternativa de simplicidad: ElasticNet autorregresivo de cinco variables.
- Holdout: permanece cerrado.

La revisión posterior de coeficientes, importancias y meses de mayor error se
encuentra en [explainability_v1.md](explainability_v1.md). Las extensiones a
horizontes de tres y doce meses y a ventana móvil se evaluaron por separado en
[horizon_robustness_v1.md](horizon_robustness_v1.md), sin reabrir la selección
del modelo h=6.

Archivos auditables:

- `reports/tables/parsimonious_model_comparison.csv`.
- `reports/tables/parsimonious_predictions_development.csv`.
- `reports/tables/parsimonious_tuning_development.csv`.
- `reports/tables/stability_vs_zero_development.csv`.
- `data/metadata/robustness_v001.json`.
