"""Genera los notebooks académicos de reproducción del proyecto."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"


def md(source: str):
    return new_markdown_cell(dedent(source).strip())


def code(source: str):
    return new_code_cell(dedent(source).strip())


def notebook(cells: list, title: str):
    document = new_notebook(cells=cells)
    document.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    document.metadata["language_info"] = {"name": "python", "version": "3.11"}
    document.metadata["project"] = {
        "title": title,
        "course": "Machine Learning Aplicado a las Finanzas — USACH",
    }
    return document


COMMON_SETUP = """
from pathlib import Path

ROOT = Path.cwd().resolve()
if ROOT.name.lower() == "notebooks":
    ROOT = ROOT.parent

print(f"Raíz del proyecto: {ROOT}")
"""


def build_master():
    cells = [
        md(
            """
            # 00 — Reproducción completa

            Este notebook es la puerta de entrada al proyecto. Reconstruye el
            análisis desde las respuestas crudas locales, actualiza la
            trazabilidad, ejecuta las pruebas y compara las conclusiones antes y
            después.

            El pipeline respeta el calendario efectivo de publicación: para una
            emisión en el mes `t`, solo admite variables con `available_date`
            anterior o igual a `forecast_issue_date`.
            """
        ),
        code(COMMON_SETUP),
        md(
            """
            ## Inventario mínimo

            La reproducción local no descarga datos ni necesita credenciales.
            Requiere las capas `data/raw`, el código de `src` y las
            configuraciones versionadas en `configs`.
            """
        ),
        code(
            """
            required = [
                ROOT / "data" / "raw" / "bcch" / "catalog_monthly.json",
                ROOT / "data" / "raw" / "cmf_publication_calendar" / "cmf_press.html",
                ROOT / "configs" / "base.toml",
                ROOT / "src" / "morosidad_bancaria" / "cli.py",
            ]
            inventory = {path.relative_to(ROOT).as_posix(): path.exists() for path in required}
            inventory
            """
        ),
        md(
            """
            ## Ejecución

            Para volver a correr las doce etapas desde este notebook, cambie
            `RUN_FULL_REPRODUCTION` a `True`. La ejecución conserva cerrado el
            holdout 2024–2025.
            """
        ),
        code(
            """
            import os
            import subprocess
            import sys

            RUN_FULL_REPRODUCTION = False

            if RUN_FULL_REPRODUCTION:
                environment = os.environ.copy()
                environment["PYTHONPATH"] = str(ROOT / "src")
                environment["PYTHONDONTWRITEBYTECODE"] = "1"
                subprocess.run(
                    [sys.executable, "-B", "scripts/run_reproduction.py"],
                    cwd=ROOT,
                    env=environment,
                    check=True,
                )
            else:
                print("Ejecución omitida. Use RUN_FULL_REPRODUCTION = True para reconstruir.")
            """
        ),
        md("## Resultado de la última reproducción"),
        code(
            """
            import json
            from IPython.display import Markdown, display

            comparison_path = ROOT / "reports" / "reproduction_comparison.json"
            if comparison_path.exists():
                comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
                verdict = "NO CAMBIARON" if not comparison["conclusions_changed"] else "CAMBIARON"
                display(Markdown(
                    f"**Conclusiones: {verdict}.**  "
                    f"Archivos analíticos modificados: {comparison['key_files_changed']}."
                ))
                comparison["after"]
            else:
                print("Aún no existe una comparación. Ejecute scripts/run_reproduction.py.")
            """
        ),
    ]
    return notebook(cells, "Reproducción completa")


def build_data():
    cells = [
        md(
            """
            # 01 — Datos y diseño point-in-time

            Reconstrucción del universo mensual, calendario de publicación y
            auditoría de disponibilidad. El objetivo es comprobar que ninguna
            variable use información publicada después de la fecha de emisión.
            """
        ),
        code(COMMON_SETUP),
        code(
            """
            import pandas as pd
            import matplotlib.pyplot as plt

            base = pd.read_csv(
                ROOT / "data" / "processed" / "modeling_base.csv",
                parse_dates=["observation_date", "forecast_issue_date", "target_date_h6", "target_available_date_h6"],
            )
            features = pd.read_csv(
                ROOT / "data" / "processed" / "model_matrix_consumption_h6_v001.csv",
                parse_dates=["observation_date", "forecast_issue_date"],
            )

            summary = pd.Series({
                "observaciones mensuales": len(base),
                "inicio": base["observation_date"].min().date(),
                "fin": base["observation_date"].max().date(),
                "filas de desarrollo": int((base["split"] == "development").sum()),
                "filas de holdout": int((base["split"] == "holdout").sum()),
                "filas con features completas": int(features["complete_features"].sum()),
            }, name="valor")
            summary.to_frame()
            """
        ),
        md("## Auditoría de disponibilidad"),
        code(
            """
            issue_date = pd.to_datetime(base["forecast_issue_date"])
            available_columns = [column for column in base.columns if column.endswith("__available_date")]
            violations = {}
            for column in available_columns:
                available = pd.to_datetime(base[column], errors="coerce")
                violations[column] = int(((available > issue_date) & available.notna()).sum())

            audit = pd.Series(violations, name="violaciones").to_frame()
            assert audit["violaciones"].sum() == 0, "Se detectó look-ahead por disponibilidad"
            audit
            """
        ),
        md("## Evolución de la morosidad observada"),
        code(
            """
            figure, axis = plt.subplots(figsize=(11, 4))
            axis.plot(base["observation_date"], base["npl90_consumption_percent_t"], color="#17365d")
            axis.axvspan(pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-31"), color="#f4b183", alpha=0.25, label="holdout cerrado")
            axis.set(title="Morosidad de consumo de 90 días o más", ylabel="Porcentaje", xlabel="Mes")
            axis.legend()
            axis.grid(alpha=0.2)
            plt.tight_layout()
            plt.show()
            """
        ),
        md(
            """
            **Lectura:** la base contiene 148 meses continuos y la auditoría no
            encuentra variables publicadas después de la fecha de emisión. El
            área sombreada corresponde al holdout reservado, no utilizado para
            seleccionar ni evaluar modelos.
            """
        ),
    ]
    return notebook(cells, "Datos y diseño point-in-time")


def build_models():
    cells = [
        md(
            """
            # 02 — Validación, modelos y robustez

            Comparación fuera de muestra sobre desarrollo mediante ventanas
            expansivas, selección interna temporal y purga de etiquetas no
            publicadas. Las métricas se agregan sobre 46 orígenes de pronóstico.
            """
        ),
        code(COMMON_SETUP),
        code(
            """
            import pandas as pd
            import matplotlib.pyplot as plt

            metrics = pd.read_csv(ROOT / "reports" / "tables" / "model_comparison_development.csv")
            overall = metrics.loc[metrics["fold_id"].astype(str) == "all"].copy()
            overall = overall.sort_values("mae")
            overall[["model", "n", "mae", "rmse", "directional_accuracy"]]
            """
        ),
        code(
            """
            colors = ["#3b82f6" if model == "zero_change" else "#a8b2c1" for model in overall["model"]]
            axis = overall.plot.barh(x="model", y="mae", color=colors, figsize=(9, 5), legend=False)
            axis.invert_yaxis()
            axis.set(title="MAE fuera de muestra — horizonte 6 meses", xlabel="MAE (puntos porcentuales)", ylabel="")
            axis.grid(axis="x", alpha=0.2)
            plt.tight_layout()
            plt.show()
            """
        ),
        md("## Estabilidad frente al benchmark cambio cero"),
        code(
            """
            stability = pd.read_csv(ROOT / "reports" / "tables" / "stability_vs_zero_development.csv")
            stability.loc[
                stability["model"].isin(["elastic_net", "random_forest", "xgboost"]),
                ["model", "mae", "mae_improvement_vs_zero_pct", "bootstrap_probability_better_than_zero", "ci_conclusion"],
            ].sort_values("mae")
            """
        ),
        md("## Robustez por horizonte"),
        code(
            """
            horizons = pd.read_csv(ROOT / "reports" / "tables" / "horizon_robustness_metrics.csv")
            horizon_overall = horizons.loc[
                (horizons["fold_id"].astype(str) == "all")
                & (horizons["training_scheme"] == "expanding")
            ].copy()
            horizon_table = horizon_overall.pivot(index="horizon_months", columns="model", values="mae")
            horizon_table["elastic_net_improvement_vs_zero_pct"] = (
                (horizon_table["zero_change"] - horizon_table["elastic_net"])
                / horizon_table["zero_change"] * 100
            )
            horizon_table
            """
        ),
        md("## Drivers del challenger"),
        code(
            """
            importance = pd.read_csv(ROOT / "reports" / "tables" / "feature_importance_global.csv")
            top = importance.loc[
                (importance["fold_id"].astype(str) == "all")
                & (importance["model"] == "elastic_net")
            ].nsmallest(10, "rank")
            axis = top.sort_values("normalized_importance").plot.barh(
                x="feature", y="normalized_importance", figsize=(9, 5), color="#3b82f6", legend=False
            )
            axis.set(title="Importancia global fuera de muestra", xlabel="Importancia normalizada", ylabel="")
            axis.grid(axis="x", alpha=0.2)
            plt.tight_layout()
            plt.show()
            """
        ),
        md(
            """
            **Lectura:** cambio cero mantiene el menor MAE a seis meses.
            ElasticNet es el mejor modelo aprendido, pero su mejora es negativa y
            la evidencia bootstrap no permite promoverlo. El resultado positivo
            de `h=12` permanece como hipótesis descriptiva, no como autorización
            para cambiar el campeón.
            """
        ),
    ]
    return notebook(cells, "Validación, modelos y robustez")


def build_alert():
    cells = [
        md(
            """
            # 03 — Alerta de estrés y conclusiones

            Evaluación del ranking de estrés a seis meses. Se distingue entre
            capacidad de ordenar casos y calibración probabilística, porque una
            buena Average Precision no garantiza probabilidades confiables.
            """
        ),
        code(COMMON_SETUP),
        code(
            """
            import json
            import pandas as pd
            import matplotlib.pyplot as plt
            from IPython.display import Markdown, display

            stress = pd.read_csv(ROOT / "reports" / "tables" / "stress_alert_metrics_development.csv")
            overall = stress.loc[stress["fold_id"].astype(str) == "all"].copy()
            overall[["model", "events", "average_precision", "roc_auc", "brier_score", "precision", "recall"]]
            """
        ),
        code(
            """
            candidates = overall.loc[overall["model"] != "historical_prevalence"].copy()
            best = candidates.sort_values("average_precision", ascending=False).iloc[0]
            prevalence = overall.loc[overall["model"] == "historical_prevalence"].iloc[0]

            figure, axes = plt.subplots(1, 2, figsize=(11, 4))
            candidates.plot.bar(x="model", y="average_precision", ax=axes[0], color="#3b82f6", legend=False)
            candidates.plot.bar(x="model", y="brier_score", ax=axes[1], color="#a8b2c1", legend=False)
            axes[1].axhline(prevalence["brier_score"], color="#c00000", linestyle="--", label="prevalencia")
            axes[0].set(title="Capacidad de ranking", ylabel="Average Precision", xlabel="")
            axes[1].set(title="Error probabilístico", ylabel="Brier", xlabel="")
            axes[1].legend()
            for axis in axes:
                axis.tick_params(axis="x", rotation=20)
                axis.grid(axis="y", alpha=0.2)
            plt.tight_layout()
            plt.show()
            """
        ),
        md("## Controles técnicos y decisión"),
        code(
            """
            acceptance = json.loads(
                (ROOT / "data" / "metadata" / "technical_acceptance_v001.json").read_text(encoding="utf-8")
            )
            calibrated = float(best["brier_score"]) <= float(prevalence["brier_score"])
            holdout = next(
                check["observed"] for check in acceptance["checks"]
                if check["id"] == "holdout_rows_evaluated"
            )

            display(Markdown(f'''\
            - Mejor ranking de estrés: **{best['model']}**, AP **{best['average_precision']:.3f}**.
            - Brier del challenger: **{best['brier_score']:.3f}**; prevalencia: **{prevalence['brier_score']:.3f}**.
            - ¿Probabilidad mejor calibrada que prevalencia?: **{'sí' if calibrated else 'no'}**.
            - Estado técnico: **{acceptance['status']} ({acceptance['checks_passed']}/{acceptance['checks_total']})**.
            - Filas de holdout evaluadas: **{holdout}**.
            '''))
            """
        ),
        code(
            """
            comparison_path = ROOT / "reports" / "reproduction_comparison.json"
            if comparison_path.exists():
                comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
                verdict = "NO CAMBIARON" if not comparison["conclusions_changed"] else "CAMBIARON"
                display(Markdown(
                    f"## Veredicto de reproducción\\n\\n"
                    f"Las conclusiones **{verdict}**. "
                    f"Archivos analíticos clave con diferencias: **{comparison['key_files_changed']}**."
                ))
            """
        ),
        md(
            """
            ## Conclusión final

            El modelo simple gana por evidencia, no por defecto. Cambio cero se
            mantiene como campeón h=6; ElasticNet queda como challenger de
            investigación. La logística sirve para priorizar episodios, pero no
            como probabilidad calibrada ni alerta operativa. El holdout continúa
            cerrado.
            """
        ),
    ]
    return notebook(cells, "Alerta de estrés y conclusiones")


def main() -> int:
    NOTEBOOKS.mkdir(parents=True, exist_ok=True)
    documents = {
        "00_reproduccion_completa.ipynb": build_master(),
        "01_datos_y_diseno_point_in_time.ipynb": build_data(),
        "02_validacion_modelos_y_robustez.ipynb": build_models(),
        "03_alerta_de_estres_y_conclusiones.ipynb": build_alert(),
    }
    for filename, document in documents.items():
        path = NOTEBOOKS / filename
        nbformat.write(document, path)
        print(f"Generado: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
