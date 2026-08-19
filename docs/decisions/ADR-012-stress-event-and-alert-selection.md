# ADR-012: evento de estrés y selección de alertas

- Estado: aceptada para el MVP antes de ejecutar el backtest
- Fecha: 2026-08-17

## Decisión

Definir estrés como un cambio de morosidad a seis meses estrictamente superior
al percentil 80 de los cambios h=6 cuyas etiquetas estaban disponibles en la
fecha de emisión. El percentil se vuelve a calcular para cada origen; el target
de prueba nunca participa en su umbral.

Comparar tres clasificadores sobre las 23 variables congeladas: regresión
logística regularizada, Random Forest y XGBoost. La probabilidad histórica de
estrés de cada muestra de entrenamiento será el benchmark sin variables.

Los hiperparámetros se seleccionan por precisión promedio en 24 orígenes
internos temporales y purgados. El umbral de alerta se elige por F1 entre siete
valores predefinidos, usando esas mismas predicciones internas. Los modelos se
reestiman mensualmente y los hiperparámetros se revisan por bloque externo.

## Fundamento

Un umbral histórico expandible se adapta al nivel y volatilidad observados sin
mirar el futuro. El percentil 80 produce una clase minoritaria relevante y, a
la vez, una cantidad de eventos compatible con la muestra mensual disponible.
La precisión promedio evalúa el ranking bajo desbalance; F1 hace explícito el
compromiso operativo entre alertas omitidas y falsas alarmas.

## Evaluación

Se reportarán precisión promedio, ROC-AUC, recall, precision, F1, balanced
accuracy, Brier score, prevalencia, tasa de alertas, calibración y matriz de
confusión. La incertidumbre en Brier frente al benchmark se medirá mediante
bootstrap móvil circular con bloques de seis meses y 10.000 réplicas.

## Restricciones

- Solo se evaluarán los 46 orígenes externos de desarrollo ya congelados.
- Las etiquetas aún no publicadas se purgan antes de calcular el percentil.
- El holdout no puede intervenir en umbrales, ajuste, selección ni métricas.
- Una alerta anticipa por construcción el evento agregado del horizonte h=6;
  no identifica el mes exacto dentro de ese intervalo.
