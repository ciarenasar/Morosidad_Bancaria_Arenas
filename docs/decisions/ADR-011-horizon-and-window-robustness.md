# ADR-011: robustez por horizonte y ventana de entrenamiento

- Estado: aceptada para el MVP
- Fecha: 2026-08-17

## Decisión

Evaluar el campeón de desarrollo, cambio cero, y el challenger ElasticNet
completo en horizontes de 3, 6 y 12 meses. Para cada horizonte se comparan una
ventana expansiva y una ventana móvil de 60 meses calendario.

La ventana móvil se aplica en dos pasos: primero conserva observaciones entre
`t-60` y `t-1`; luego elimina cualquier etiqueta cuya fecha efectiva de
publicación sea posterior a la fecha de emisión del pronóstico. No significa
"las últimas 60 etiquetas disponibles".

Se conservan los mismos 46 orígenes externos de desarrollo y la selección
interna temporal de ElasticNet. El bootstrap móvil circular usa 10.000 réplicas
y un largo de bloque igual al horizonte del objetivo.

## Fundamento

Los horizontes alternativos permiten distinguir falta de señal de un posible
desajuste entre variables y horizonte. La ventana móvil comprueba si descartar
historia antigua ayuda ante cambios de régimen. Limitar la comparación al
campeón y al challenger ya definidos evita convertir el análisis posterior en
otra búsqueda de modelos.

## Regla de interpretación

Las diferencias de pérdida se calculan como error absoluto de ElasticNet menos
error absoluto de cambio cero. Para comparar ventanas se usa error absoluto de
la ventana móvil menos error absoluto de la expansiva. Un intervalo completamente
negativo favorece al primer elemento de cada comparación; si contiene cero, el
resultado se declara inconcluso.

## Consecuencias

ElasticNet es consistentemente peor que cambio cero a tres meses. A seis meses,
la desventaja puntual no es concluyente por bloques. A doce meses, la ventana
expansiva mejora el MAE en 2,5%, pero el intervalo también contiene cero y la
ventaja es inestable entre bloques. La ventana móvil no mejora de forma
concluyente ningún horizonte. No se abre ni se usa el holdout.
