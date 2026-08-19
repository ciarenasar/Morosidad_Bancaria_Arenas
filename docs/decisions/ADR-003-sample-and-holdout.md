# ADR-003: muestra y holdout

- Estado: aceptada con parámetro pendiente
- Fecha: 2026-08-17

## Decisión

Comenzar en la primera observación fiable disponible de la serie objetivo. El
tamaño y las fechas exactas del holdout se fijarán solo después de medir la
cobertura conjunta de objetivo y predictores.

## Consecuencias

No se fuerza ahora una partición que podría dejar muy pocas crisis o muy pocos
datos de entrenamiento. La decisión final deberá documentarse en una nueva ADR y
mantener el orden temporal.
