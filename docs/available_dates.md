# Fechas de disponibilidad

## Objetivo CMF

La fecha de emisión se obtuvo de los comunicados oficiales que acompañaron la
publicación mensual de resultados:

- archivo de noticias de la ex-SBIF para marzo de 2014 a abril de 2019;
- archivo de comunicados de la CMF para mayo de 2019 a junio de 2026.

El cruce encontró evidencia para los 148 meses del objetivo. Las publicaciones
ocurrieron entre 25 y 38 días después del cierre del mes. El archivo versionable
`data/metadata/cmf_publication_calendar.csv` conserva el título, organismo y URL
de evidencia de cada fecha.

Fuentes oficiales:

- <https://cronologiabancaria.cmfchile.cl/sbifweb/servlet/Noticia?indice=2.0>
- <https://www.cmfchile.cl/portal/prensa/615/w3-propertyvalue-43349.html>

## Predictores macroeconómicos

La BDE no entrega una fecha histórica de primera publicación por observación.
Para este hito se usan fechas conservadoras, declaradas en
`configs/bcch_series.toml`:

| Grupo | Regla provisional |
|---|---|
| IMACEC y desempleo | día 5 de `t+2` |
| IPC, TPM, dólar, tasa de consumo, colocaciones y M1 | día 15 de `t+1` |

Estas reglas no adelantan información: pueden retrasar una variable respecto de
su publicación real. El ensamblador elige para cada fila la observación más
reciente cuya fecha calculada sea menor o igual a la fecha de emisión CMF y
conserva ambas fechas para auditoría.

Como resultado, IMACEC y desempleo usan `t-1` en 143 de los 148 meses y `t` en
cinco meses en que la publicación bancaria fue suficientemente tardía. Las otras
seis series usan `t` en toda la muestra. Se registraron cero violaciones de
disponibilidad.

## Limitación de revisiones

Las series descargadas desde la BDE son de último vintage. Algunas, especialmente
IMACEC, IPC empalmado y agregados reales, pueden haber sido revisadas después de
la fecha histórica de pronóstico. El MVP controla la fecha de primera
disponibilidad de manera conservadora, pero no puede reconstruir valores vintage
sin una fuente de datos en tiempo real o archivos de publicaciones originales.
