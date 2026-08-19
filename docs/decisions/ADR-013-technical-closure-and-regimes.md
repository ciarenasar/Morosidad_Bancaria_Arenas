# ADR-013: cierre técnico y regímenes de evaluación

- Estado: aceptada para el MVP antes de ejecutar el análisis
- Fecha: 2026-08-17

## Decisión

Cerrar la evaluación de desarrollo con cuatro dimensiones de régimen definidas
sin consultar sus resultados:

- pandemia: marzo de 2020 a febrero de 2021;
- inflación alta: IPC anual mayor o igual a 6%;
- TPM alta: promedio mensual mayor o igual a 5%;
- contracción: variación anual de IMACEC inferior a 0%.

Cada dimensión se divide en dos estados mutuamente excluyentes. IPC, TPM e
IMACEC corresponden al valor point-in-time ya seleccionado para la fecha de
emisión. Se reportarán métricas para cambio cero, ElasticNet, Random Forest y
XGBoost, además de los cuatro modelos de alerta del hito 8.

## Uso de los resultados

El análisis por régimen es descriptivo. No puede cambiar el campeón, seleccionar
features, ajustar hiperparámetros ni justificar la apertura del holdout. Los
subgrupos pequeños o sin ambas clases se conservarán y sus métricas no definidas
se mostrarán como tales.

## Cierre reproducible

El repositorio incorporará:

- un comando que reconstruya localmente todo el análisis desde los datos raw;
- controles automáticos de cobertura, particiones, probabilidades y artefactos;
- hashes SHA-256 de código, configuración, datos y resultados;
- una model card que distinga el campeón de regresión del challenger de alerta;
- un manual de reproducción sin credenciales embebidas.

## Consecuencias

Los resultados del holdout permanecen inaccesibles. Un estado Git sin commit se
registrará como limitación de trazabilidad, pero no modificará resultados ni
impedirá reproducirlos desde los archivos locales y sus hashes.
