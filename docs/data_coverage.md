# Auditoría inicial de cobertura

- Fecha de auditoría: 2026-08-17
- Fuente: APIBEST, Comisión para el Mercado Financiero
- Cuadro: `CMF_CONT_MOR_90DMAS_CONSOL_STO_RAZ_PORC_MONT`
- Serie objetivo: `CMF_CONT_MOR_90DMAS_CONSOL_CCS_STO_RAZ_PORC_MONT`

## Resultado

| Control | Resultado |
|---|---:|
| Primera observación | 2014-03-01 |
| Última observación disponible | 2026-06-01 |
| Observaciones | 148 |
| Meses esperados | 148 |
| Meses faltantes | 0 |
| Mínimo observado | 1.072773 % |
| Máximo observado | 3.037771 % |

APIBEST devolvió dos entradas idénticas de la serie objetivo en cada una de las
13 ventanas consultadas. El proceso comprueba la igualdad y conserva una sola;
si en una descarga futura los duplicados difieren, la construcción falla en vez
de escoger un valor silenciosamente.

## Calendario de publicación

La respuesta del endpoint de rango no contiene la fecha histórica efectiva de
publicación. Esta se reconstruyó posteriormente desde los comunicados oficiales
de CMF y ex-SBIF: 148 de 148 meses tienen evidencia y el rezago efectivo fue de
25 a 38 días desde el cierre mensual. Véase `docs/available_dates.md`.

## Implicación para el holdout

Hay 148 meses de nivel y 142 objetivos continuos conocidos a seis meses. Las
ocho series del Banco Central tienen cobertura completa después del corte as-of.
Se reservaron enero de 2024 a diciembre de 2025 como holdout final de 24 meses,
dejando 118 meses etiquetados para desarrollo.
