# ADR-004: disponibilidad de información

- Estado: aceptada
- Fecha: 2026-08-17

## Decisión

La fecha de emisión de cada pronóstico es la fecha efectiva de publicación por
la CMF de la observación `t`. Una variable es admisible únicamente cuando
`available_date <= forecast_issue_date`.

## Consecuencias

El dataset modelable deberá conservar separadamente la fecha económica de la
observación y la fecha en que se hizo pública. Los rezagos se aplicarán usando
fechas de disponibilidad, no supuestos de cierre de mes, para evitar look-ahead
bias.
