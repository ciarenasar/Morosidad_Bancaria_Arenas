# ADR-001: definición de la variable objetivo

- Estado: aceptada
- Fecha: 2026-08-17

## Decisión

Usar la razón mensual de morosidad de 90 días o más de la cartera de consumo del
sistema bancario agregado, publicada por la CMF. El objetivo continuo será su
cambio en puntos porcentuales entre `t` y `t+h`.

## Consecuencias

La interpretación es directa y evita mezclar niveles con variaciones. Los
primeros `h` meses no pierden observaciones, pero los últimos `h` meses no tendrán
objetivo conocido y se reservarán para pronósticos futuros.
