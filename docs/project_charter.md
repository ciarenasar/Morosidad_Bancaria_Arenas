# Project charter

## Problema y propósito

Construir un proceso reproducible que pronostique el cambio de la morosidad de
90 días o más de la cartera de consumo del sistema bancario chileno. El proyecto
integra los aprendizajes de HW01–HW07 del curso de Finanzas y privilegia una
evaluación honesta fuera de muestra.

## MVP confirmado

| Elemento | Definición |
|---|---|
| Unidad de análisis | Sistema bancario chileno agregado |
| Cartera | Consumo |
| Frecuencia | Mensual |
| Variable base | Razón de morosidad de 90 días o más, en porcentaje |
| Objetivo | Cambio en puntos porcentuales entre `t` y `t+6` |
| Horizonte | 6 meses |
| Fuente del objetivo | APIBEST de la CMF |
| Evaluación | Temporal, sin barajar observaciones |

La variable objetivo será:

`y(t, 6) = morosidad(t + 6) - morosidad(t)`.

## Regla de información disponible

El pronóstico para el mes de observación `t` se considera emitido en la fecha
efectiva en que la CMF publica la información correspondiente a `t`. Solo puede
usar una variable si su `available_date` es anterior o igual a esa fecha de
emisión. Esta regla se aplicará tanto a la creación de características como a la
evaluación walk-forward.

## Criterios de éxito del primer hito

1. Las credenciales permanecen fuera de Git y no aparecen en logs.
2. Las descargas crudas son reproducibles, trazables mediante hash y no se
   transforman en el lugar.
3. Se mide la cobertura efectiva antes de fijar la ventana final de holdout.
4. Toda serie candidata declara `observation_date`, `available_date`, frecuencia,
   unidad y transformación antes de entrar al modelo.

## Fuera del MVP inicial

- predicciones por banco;
- carteras comercial e hipotecaria;
- despliegue en tiempo real;
- modelos neuronales;
- umbral del evento de estrés, que se definirá después del análisis de cobertura
  y distribución, dejando el umbral económico fijo como especificación principal.
