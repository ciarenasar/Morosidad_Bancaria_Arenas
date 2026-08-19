# ADR-005: holdout temporal final

- Estado: aceptada
- Fecha: 2026-08-17

## Contexto

La serie objetivo tiene 148 meses continuos entre marzo de 2014 y junio de 2026.
Con horizonte de seis meses existen 142 filas etiquetadas.

## Decisión

Reservar como holdout final los 24 meses con fecha de observación entre enero de
2024 y diciembre de 2025. El desarrollo y la selección de modelos usarán marzo de
2014 a diciembre de 2023, con validación de ventana expansiva.

## Consecuencias

Quedan 118 filas etiquetadas para desarrollo y 24 para evaluación final. Las seis
observaciones de enero a junio de 2026 no tienen todavía objetivo a seis meses y
se conservan como filas de pronóstico, fuera de las métricas.

El holdout no debe consultarse para escoger variables, hiperparámetros, umbrales
ni transformaciones. Cualquier cambio posterior exige una nueva decisión y una
justificación explícita.
