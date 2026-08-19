# Cierre técnico v1

## Alcance

Este cierre consolida métricas por régimen sin reabrir la selección de modelos.
Todas las filas pertenecen a desarrollo y usan variables disponibles en la
fecha de emisión. Los regímenes pueden solaparse entre dimensiones.

![Desempeño por régimen](../reports/figures/regime_performance.png)

## Regresión h=6

| Dimensión | Régimen | n | MAE cero | MAE ElasticNet | Mejora ElasticNet |
|---|---|---:|---:|---:|---:|
| pandemic_period | pandemic | 12 | 0,641 | 0,656 | -2,4% |
| pandemic_period | non_pandemic | 34 | 0,361 | 0,454 | -25,8% |
| inflation_regime | high_inflation | 22 | 0,453 | 0,423 | 6,5% |
| inflation_regime | lower_inflation | 24 | 0,416 | 0,583 | -40,0% |
| policy_rate_regime | high_policy_rate | 23 | 0,369 | 0,426 | -15,3% |
| policy_rate_regime | lower_policy_rate | 23 | 0,498 | 0,587 | -17,9% |
| activity_regime | activity_contraction | 16 | 0,537 | 0,570 | -6,0% |
| activity_regime | activity_non_contraction | 30 | 0,378 | 0,473 | -25,0% |

## Alerta logística

| Dimensión | Régimen | n | Eventos | AP | Brier | Recall |
|---|---|---:|---:|---:|---:|---:|
| pandemic_period | pandemic | 12 | 0 | no definido | 0,167 | 0,0% |
| pandemic_period | non_pandemic | 34 | 16 | 0,805 | 0,316 | 56,2% |
| inflation_regime | high_inflation | 22 | 14 | 0,861 | 0,397 | 64,3% |
| inflation_regime | lower_inflation | 24 | 2 | 0,208 | 0,167 | 0,0% |
| policy_rate_regime | high_policy_rate | 23 | 11 | 0,925 | 0,250 | 81,8% |
| policy_rate_regime | lower_policy_rate | 23 | 5 | 0,363 | 0,304 | 0,0% |
| activity_regime | activity_contraction | 16 | 2 | 1,000 | 0,297 | 100,0% |
| activity_regime | activity_non_contraction | 30 | 14 | 0,827 | 0,266 | 50,0% |

Las métricas sin ambas clases se muestran como `no definido`. Los cortes son
diagnósticos: no constituyen evidencia causal ni autorización para desplegar
los modelos.

## Controles y trazabilidad

- `technical_acceptance_v001.json` registra checks de cobertura y holdout.
- `reproduction_manifest_v001.json` registra hashes SHA-256 y entorno.
- `reproduction.md` describe la ejecución local de punta a punta.
- `model_card_v1.md` documenta usos, métricas y limitaciones.

El holdout permanece cerrado para el informe final.
