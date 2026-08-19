# Validación de reproducción

## Veredicto

Las conclusiones **NO CAMBIARON** después de reconstruir el proyecto desde los
datos crudos locales.

| Indicador | Antes | Después |
|---|---:|---:|
| Campeón de regresión | zero_change | zero_change |
| MAE del campeón (pp) | 0.433693 | 0.433693 |
| Challenger aprendido | elastic_net | elastic_net |
| Mejora del challenger vs. cero | -16.796343 | -16.796343 |
| Mejor ranking de estrés | logistic_regression | logistic_regression |
| Average Precision de estrés | 0.771382 | 0.771382 |
| Brier de estrés | 0.276900 | 0.276900 |
| Brier de prevalencia | 0.248204 | 0.248204 |
| Alerta operativa aprobada | False | False |
| Holdout evaluado | 0 | 0 |
| Estado técnico | passed | passed |

## Integridad de resultados

- Archivos analíticos clave comparados: 46.
- Archivos con diferencias: 0.
- Ningún archivo analítico clave cambió.

## Interpretación

El campeón de regresión continúa siendo cambio cero. ElasticNet permanece como
challenger aprendido y no supera al benchmark de forma robusta. La regresión
logística conserva el mejor ranking de estrés, pero su Brier no mejora la
prevalencia histórica, por lo que la alerta sigue sin aprobación operativa. El
holdout permanece cerrado.
