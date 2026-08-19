# ADR-006: uso de datos macroeconómicos de último vintage

- Estado: aceptada para el MVP
- Fecha: 2026-08-17

## Decisión

Usar las series vigentes de la BDE del Banco Central, aplicando fechas de
disponibilidad conservadoras y declarando explícitamente que sus valores son de
último vintage.

## Fundamento

La API BDE consultada no ofrece vintages históricos por observación. Excluir toda
serie potencialmente revisable eliminaría variables centrales como actividad e
inflación y no resolvería el problema para otros agregados empalmados.

## Consecuencias

El diseño elimina el *look-ahead* derivado del calendario de publicación, pero no
reproduce completamente el valor observado en tiempo real. Los resultados deben
describirse como evaluación pseudo-real-time con latest vintage. Una extensión
posterior podrá reemplazar estas series por archivos de publicación archivados o
una base vintage.
