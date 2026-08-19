# ADR-010: explicabilidad estrictamente fuera de muestra

- Estado: aceptada para el MVP
- Fecha: 2026-08-17

## Decisión

Calcular explicaciones únicamente para las 46 predicciones externas de
desarrollo. En cada origen se reconstruye la misma muestra purgada, se reestima
el modelo con los hiperparámetros registrados y se explica solo la fila que se
habría pronosticado en esa fecha.

Se usan métodos acordes a cada familia:

- ElasticNet: contribución lineal sobre variables estandarizadas dentro del
  pipeline; el coeficiente estandarizado también se conserva.
- XGBoost: TreeSHAP exacto mediante `pred_contribs` del propio booster.
- Random Forest: reducción media de impureza del modelo reestimado, como medida
  global no firmada.

## Verificación

Para ElasticNet y XGBoost, el valor base más la suma de contribuciones debe
reconstruir el pronóstico registrado con tolerancia máxima de `1e-6`. Random
Forest debe reproducir directamente la predicción y sus importancias deben sumar
uno salvo tolerancia numérica.

Las importancias empatadas reciben rango promedio. Esto evita atribuir
estabilidad artificial a las variables que ElasticNet reduce exactamente a
cero.

## Meses críticos

Se define antes del análisis la unión de los cinco mayores cambios absolutos
reales y los cinco mayores errores absolutos de ElasticNet. Para cada mes se
guardan predicciones, errores, contexto disponible y las tres mayores
contribuciones positivas y negativas de ElasticNet y XGBoost.

## Consecuencias y límites

Las contribuciones describen el mecanismo del modelo, no efectos causales ni
necesariamente relaciones económicas estructurales. Las importancias de Random
Forest pueden favorecer variables continuas o correlacionadas, y no tienen
signo. La inestabilidad entre bloques debe reportarse como resultado, no
ocultarse mediante un ranking agregado. El holdout no se explica ni se consulta.

