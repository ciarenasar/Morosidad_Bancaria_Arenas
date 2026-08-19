# Entrega final del hito 10

## Qué se entrega

- `deliverables/informe_final_morosidad_bancaria.docx`: informe editable.
- `deliverables/informe_final_morosidad_bancaria.pdf`: versión final para lectura
  y evaluación.
- `deliverables/presentacion_final_morosidad_bancaria.pptx`: presentación de 15
  diapositivas para la defensa.
- `docs/model_card_v1.md`: uso previsto, limitaciones y estado de los modelos.
- `docs/reproduction.md`: instalación, ejecución y controles de verificación.

## Mensaje central

El proyecto no parte de la premisa de que machine learning deba ganar. La
pregunta es si un modelo aprendido mejora una regla simple bajo información
realmente disponible en cada fecha. En los 46 orígenes fuera de muestra de
desarrollo para h=6, cambio cero obtiene MAE de 0,434 puntos porcentuales y
ElasticNet 0,507. El intervalo por bloques de la diferencia incluye cero y el
estimador puntual favorece al benchmark. Por eso:

- cambio cero es el campeón de regresión;
- ElasticNet queda como challenger de investigación;
- la señal favorable a h=12 es una hipótesis que requiere más observaciones;
- la alerta logística ordena razonablemente el riesgo, pero no está calibrada
  para una decisión operativa;
- los resultados por régimen son descriptivos y no autorizan despliegue.

## Cómo leer el informe

El informe sigue el orden de una decisión auditable: pregunta y alcance,
disponibilidad point-in-time, cobertura, diseño de validación, comparación de
modelos, incertidumbre, explicabilidad, robustez, alerta, regímenes, decisión y
limitaciones. Se separan explícitamente tres niveles de evidencia:

1. resultados consolidados que sustentan una decisión;
2. señales exploratorias que justifican seguimiento;
3. limitaciones que impiden una conclusión más fuerte.

## Cómo presentar las diapositivas

La defensa está diseñada para 10 a 12 minutos. La secuencia recomendada es:

1. abrir el problema financiero y la ficha del estudio en las diapositivas 1 a 3;
2. establecer validez point-in-time, cobertura y evaluación temporal en las 4 a 6;
3. presentar el resultado principal solo después de ese contexto, en la 7;
4. explicar quiebres, drivers y horizontes en las 8 a 10;
5. distinguir alerta y regímenes exploratorios en las 11 y 12;
6. cerrar con decisión, agenda de evidencia y conclusión en las 13 a 15.

No conviene presentar el resultado negativo como un fracaso. Es la evidencia
que evita reemplazar una regla robusta por complejidad sin ganancia comprobada.

## Reproducción y aceptación

Con los archivos raw preservados, ejecute:

```powershell
$env:PYTHONPATH = "src"
python -m morosidad_bancaria run-all-local
python -m unittest discover -s tests -v
```

El cierre técnico exige 11 de 11 controles aprobados. El holdout de enero de
2024 a diciembre de 2025 permanece reservado y no se usa para selección,
calibración ni evaluación. Las credenciales residen únicamente en `.env`, que
está excluido del manifiesto y de Git.

## Control de calidad de los entregables

- PDF: 16 páginas, sin páginas vacías ni marcadores de edición.
- Presentación: 15 diapositivas, sin desbordamientos detectados y con guion del
  orador, transiciones y fuentes en cada diapositiva.
- Código: pruebas unitarias y cierre técnico ejecutados antes de la entrega.
