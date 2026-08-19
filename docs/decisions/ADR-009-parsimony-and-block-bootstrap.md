# ADR-009: parsimonia predefinida y bootstrap por bloques

- Estado: aceptada para el MVP
- Fecha: 2026-08-17

## Decisión

Comparar cuatro especificaciones de ElasticNet definidas antes de ejecutar el
análisis: conjunto completo de 23 variables, núcleo mixto de 10, núcleo macro de
ocho y núcleo autorregresivo de cinco. Cada variante conserva la selección
interna purgada y los 46 orígenes externos del experimento principal.

Cuantificar la incertidumbre de la diferencia de error absoluto frente al cambio
cero mediante un bootstrap móvil circular con bloques de seis meses, 10.000
réplicas y semilla fija. El largo del bloque coincide con el horizonte del
objetivo para conservar parcialmente la dependencia creada por resultados
solapados.

## Fundamento

La muestra contiene solo 46 errores externos y los objetivos consecutivos
comparten meses. Un intervalo que tratara las observaciones como independientes
sería demasiado optimista. A la vez, reducir variables permite comprobar si el
mal desempeño proviene de varianza por una especificación excesivamente amplia.

## Regla de interpretación

La diferencia de pérdida se define como:

```text
|error del modelo| - |error del cambio cero|
```

Un valor negativo favorece al modelo. Se declara una diferencia consistente al
95% solo cuando todo el intervalo bootstrap queda a un lado de cero. La
probabilidad bootstrap de mejora se reporta como diagnóstico y no como un
`p-value` paramétrico.

## Consecuencias

La especificación completa sigue siendo el mejor ElasticNet y las reducciones no
mejoran el MAE. Su intervalo frente a cambio cero incluye cero, por lo que la
evidencia favorece al benchmark en el punto estimado, pero no permite afirmar una
diferencia concluyente al 95%. El holdout permanece bloqueado.

