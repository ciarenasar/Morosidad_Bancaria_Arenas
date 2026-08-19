# ADR-007: validación expansiva con purga mensual de etiquetas

- Estado: aceptada para el MVP
- Fecha: 2026-08-17

## Decisión

Evaluar el conjunto de desarrollo mediante orígenes mensuales, ajuste con ventana
expansiva y una purga dinámica de las etiquetas que aún no eran públicas en cada
fecha de emisión. Los orígenes se agrupan en bloques no solapados de hasta 12
meses para reportar estabilidad temporal.

El primer origen se ubica después de 60 observaciones con variables completas.
Esta cifra reemplaza la recomendación preliminar de 84 meses porque la cobertura
efectiva de desarrollo, después de los rezagos, contiene 106 meses. La decisión
debe revisarse si se amplía la historia.

## Regla de purga

Una observación histórica puede entrar al entrenamiento de un origen solo si:

```text
target_available_date_h6 <= forecast_issue_date del origen
```

Por ello, el primer origen parte de 60 meses de historia potencial, pero utiliza
55 etiquetas efectivamente conocidas. El modelo se vuelve a estimar en cada mes;
los bloques anuales no congelan el entrenamiento.

## Holdout

Los 24 meses entre enero de 2024 y diciembre de 2025 permanecen bloqueados. El
backtest de desarrollo no los selecciona, no calcula métricas sobre ellos y no
los utiliza para decidir variables o modelos.

## Consecuencias

La evaluación reproduce mejor el conjunto informativo histórico y evita que el
horizonte de seis meses filtre resultados futuros al entrenamiento. Como costo,
hay menos etiquetas efectivas en cada origen y cuatro bloques —el último de diez
meses—, por lo que la incertidumbre de las comparaciones sigue siendo elevada.

