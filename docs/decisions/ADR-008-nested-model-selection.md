# ADR-008: selección anidada de hiperparámetros por bloque

- Estado: aceptada para el MVP
- Fecha: 2026-08-17

## Decisión

Seleccionar los hiperparámetros de ElasticNet, Random Forest y XGBoost una vez al
inicio de cada bloque externo. La selección minimiza MAE sobre los últimos 12
orígenes internos cuyo resultado ya era conocido en ese momento. Cada origen
interno aplica la misma purga por `target_available_date_h6` que la evaluación
externa.

Después de seleccionar los parámetros del bloque, cada modelo se vuelve a
estimar mensualmente con todas las etiquetas admisibles. Se usa una semilla fija
de 42 y un solo hilo por estimador para obtener resultados deterministas.

## Fundamento

Reoptimizar los hiperparámetros en cada uno de los 46 orígenes externos agregaría
varianza de selección y un costo computacional alto para una muestra pequeña.
Fijarlos para todo el período, en cambio, podría consultar indirectamente meses
posteriores. La actualización por bloque conserva el orden temporal y permite
que el modelo se adapte sin usar el bloque que está evaluando.

## Grillas

- ElasticNet: 12 combinaciones de penalización y mezcla L1/L2.
- Random Forest: ocho combinaciones de profundidad, hoja mínima y número de
  variables por división.
- XGBoost: ocho combinaciones de profundidad, tasa de aprendizaje y peso mínimo
  de hijo.

En total se ejecutan 1.344 predicciones internas. Las grillas completas están en
`configs/models.toml` y cada puntuación queda registrada en
`reports/tables/ml_tuning_development.csv`.

## Consecuencias

Los resultados externos siguen siendo comparables con los benchmarks porque
usan exactamente los mismos 46 orígenes. El holdout no participa en selección,
ajuste ni evaluación. La conclusión depende de una grilla deliberadamente
compacta, adecuada a la muestra, y no demuestra que configuraciones fuera de
ella tengan peor desempeño.

