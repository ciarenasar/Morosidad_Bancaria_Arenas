"""Interfaz de línea de comandos del proyecto."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from morosidad_bancaria.config import (
    ConfigurationError,
    load_credentials,
    load_project_config,
    project_root,
)
from morosidad_bancaria.data.cmf_best import BestApiError, BestClient
from morosidad_bancaria.data.bcch import BcchApiError, BcchClient, load_catalog
from morosidad_bancaria.data.bcch_series import (
    audit_series,
    load_series_specs,
    parse_series_file,
    write_coverage,
    write_observations,
)
from morosidad_bancaria.data.publication_calendar import (
    PublicationCalendarError,
    audit_calendar,
    combine_entries,
    download_calendar_sources,
    parse_cmf_press,
    parse_sbif_archive,
    write_calendar,
)
from morosidad_bancaria.data.modeling_base import (
    ModelingBaseError,
    build_modeling_rows,
    load_modeling_config,
    load_publication_calendar,
    load_target,
    write_modeling_base,
    write_modeling_coverage,
)
from morosidad_bancaria.data.target import (
    TargetDataError,
    extract_target,
    write_coverage_report,
    write_target_csv,
)
from morosidad_bancaria.modeling.backtest import (
    BacktestError,
    load_model_matrix,
    run_backtest,
    summarize_metrics,
    write_backtest_metadata,
    write_csv,
)
from morosidad_bancaria.modeling.features import (
    FeatureEngineeringError,
    build_feature_rows,
    feature_names,
    load_csv_rows,
    load_feature_config,
    load_macro_history,
    write_feature_metadata,
    write_feature_rows,
)
from morosidad_bancaria.modeling.explainability import (
    ExplainabilityError,
    aggregate_attributions,
    build_critical_months,
    driver_rank_stability,
    fold_rank_correlations,
    load_explainability_config,
    run_explainability,
    write_explainability_metadata,
    write_explainability_figures,
)
from morosidad_bancaria.modeling.ml_backtest import (
    MlBacktestError,
    load_ml_config,
    run_ml_backtest,
    write_ml_metadata,
)
from morosidad_bancaria.modeling.horizon_robustness import (
    HorizonRobustnessError,
    horizon_bootstrap,
    load_horizon_robustness_config,
    run_horizon_robustness,
    summarize_horizon_metrics,
    window_bootstrap,
    write_horizon_figure,
    write_horizon_metadata,
)
from morosidad_bancaria.modeling.robustness import (
    RobustnessError,
    load_robustness_config,
    run_parsimonious_backtest,
    stability_against_zero,
    write_robustness_metadata,
)
from morosidad_bancaria.modeling.stress_alert import (
    StressAlertError,
    brier_bootstrap,
    build_calibration_table,
    classification_errors,
    episode_detection,
    load_stress_alert_config,
    run_stress_alert_backtest,
    summarize_stress_metrics,
    write_stress_figure,
    write_stress_metadata,
)
from morosidad_bancaria.modeling.temporal import (
    TemporalValidationError,
    load_validation_config,
)
from morosidad_bancaria.technical_closure import (
    TechnicalClosureError,
    build_acceptance_report,
    build_regime_membership,
    build_reproduction_manifest,
    evaluate_alerts_by_regime,
    evaluate_regression_by_regime,
    load_technical_closure_config,
    write_json,
    write_model_card,
    write_regime_figure,
    write_technical_report,
)


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use una fecha ISO YYYY-MM-DD") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="morosidad")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check-config", help="Valida configuración sin mostrar secretos")

    download = subparsers.add_parser("download-cmf", help="Descarga el cuadro objetivo de CMF")
    download.add_argument("--from-date", type=iso_date, required=True)
    download.add_argument("--to-date", type=iso_date, default=date.today())
    download.add_argument("--overwrite", action="store_true")
    subparsers.add_parser(
        "audit-cmf", help="Deduplica la serie objetivo y mide su cobertura local"
    )

    calendar_download = subparsers.add_parser(
        "download-cmf-calendar", help="Descarga comunicados oficiales CMF y SBIF"
    )
    calendar_download.add_argument("--overwrite", action="store_true")
    subparsers.add_parser(
        "build-cmf-calendar", help="Construye y audita las fechas efectivas de publicación"
    )

    bcch_catalog = subparsers.add_parser(
        "download-bcch-catalog", help="Descarga el catálogo de series del Banco Central"
    )
    bcch_catalog.add_argument("--frequency", default="MONTHLY")
    bcch_catalog.add_argument("--overwrite", action="store_true")

    bcch_search = subparsers.add_parser(
        "search-bcch-catalog", help="Busca texto en el catálogo local del Banco Central"
    )
    bcch_search.add_argument("query")

    bcch_series = subparsers.add_parser(
        "download-bcch-series", help="Descarga el conjunto inicial de series macro"
    )
    bcch_series.add_argument("--from-date", type=iso_date, default=date(2012, 1, 1))
    bcch_series.add_argument("--to-date", type=iso_date, default=date.today())
    bcch_series.add_argument("--overwrite", action="store_true")
    subparsers.add_parser("audit-bcch", help="Normaliza y audita las series macro locales")
    subparsers.add_parser(
        "build-modeling-base", help="Integra objetivo y predictores según available_date"
    )
    subparsers.add_parser(
        "build-features", help="Construye la matriz de variables point-in-time v1"
    )
    subparsers.add_parser(
        "backtest-baselines", help="Evalúa benchmarks en desarrollo con purga temporal"
    )
    subparsers.add_parser(
        "backtest-ml", help="Evalúa ElasticNet, Random Forest y XGBoost en desarrollo"
    )
    subparsers.add_parser(
        "analyze-robustness", help="Compara parsimonia e incertidumbre sin abrir holdout"
    )
    subparsers.add_parser(
        "explain-models", help="Calcula drivers fuera de muestra y meses críticos"
    )
    subparsers.add_parser(
        "analyze-horizons", help="Evalúa horizontes 3/6/12 y ventanas expansiva/móvil"
    )
    subparsers.add_parser(
        "backtest-stress", help="Evalúa alertas de estrés sin abrir el holdout"
    )
    subparsers.add_parser(
        "close-technical", help="Genera regímenes, model card y controles finales"
    )
    subparsers.add_parser(
        "run-all-local", help="Reconstruye localmente todo el análisis desde raw"
    )
    return parser


def check_config() -> int:
    credentials = load_credentials()
    config = load_project_config()
    print("Configuración válida.")
    print(f"CMF APIBEST: configurada; cuadro={config.cmf_best.chart_tag}")
    bcch_ready = bool(credentials.bcch_api_user and credentials.bcch_api_password)
    print(f"Banco Central: {'configurado' if bcch_ready else 'pendiente'}")
    return 0


def download_cmf(start: date, end: date, overwrite: bool) -> int:
    root = project_root()
    credentials = load_credentials()
    config = load_project_config()
    client = BestClient(config.cmf_best, credentials.cmf_best_api_key)
    results = client.download_history(
        config.cmf_best.chart_tag,
        start,
        end,
        root / "data" / "raw" / "cmf_best",
        root / "data" / "metadata" / "download_manifest.jsonl",
        overwrite=overwrite,
    )
    downloaded = sum(result.downloaded for result in results)
    print(
        f"Ventanas procesadas: {len(results)}; descargadas: {downloaded}; "
        f"existentes: {len(results) - downloaded}"
    )
    for result in results:
        state = "descargado" if result.downloaded else "ya existía"
        print(f"- {result.path.name}: {state}")
    return 0


def audit_cmf() -> int:
    root = project_root()
    config = load_project_config()
    raw_files = list((root / "data" / "raw" / "cmf_best").glob("*.json"))
    observations, report = extract_target(
        raw_files,
        config.cmf_best.chart_tag,
        config.cmf_best.target_series_code,
    )
    write_target_csv(observations, root / "data" / "interim" / "cmf_npl90_consumption.csv")
    write_coverage_report(report, root / "data" / "metadata" / "cmf_target_coverage.json")
    print(f"Cobertura: {report.first_observation} a {report.last_observation}")
    print(
        f"Observaciones: {report.observation_count}/{report.expected_month_count}; "
        f"meses faltantes: {len(report.missing_months)}"
    )
    print(f"Duplicados idénticos colapsados: {report.duplicate_series_entries_collapsed}")
    return 0


def download_cmf_calendar(overwrite: bool) -> int:
    root = project_root()
    config = load_project_config()
    results = download_calendar_sources(
        config.publication_calendar,
        root / "data" / "raw" / "cmf_publication_calendar",
        overwrite=overwrite,
    )
    for name, downloaded in results.items():
        print(f"- {name}: {'descargado' if downloaded else 'ya existía'}")
    return 0


def build_cmf_calendar() -> int:
    root = project_root()
    config = load_project_config()
    raw = root / "data" / "raw" / "cmf_publication_calendar"
    entries = combine_entries(
        parse_cmf_press(
            (raw / "cmf_press.html").read_bytes(),
            config.publication_calendar.cmf_press_url,
        )
        + parse_sbif_archive(
            (raw / "sbif_archive.html").read_bytes(),
            config.publication_calendar.sbif_archive_url,
        )
    )
    target_path = root / "data" / "interim" / "cmf_npl90_consumption.csv"
    with target_path.open(encoding="utf-8", newline="") as file:
        target_dates = [date.fromisoformat(row["observation_date"]) for row in csv.DictReader(file)]
    report = audit_calendar(entries, target_dates)
    target_set = set(target_dates)
    write_calendar(
        {item: entry for item, entry in entries.items() if item in target_set},
        root / "data" / "metadata" / "cmf_publication_calendar.csv",
    )
    report_path = root / "data" / "metadata" / "cmf_calendar_coverage.json"
    report_path.write_text(
        json.dumps(report.__dict__, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Fechas de publicación: {report.matched_months}/{report.target_months}; "
        f"faltantes: {len(report.missing_months)}"
    )
    print(
        "Días desde cierre mensual: "
        f"{report.minimum_days_after_month_end} a "
        f"{report.maximum_days_after_month_end}"
    )
    return 0 if not report.missing_months else 2


def download_bcch_catalog(frequency: str, overwrite: bool) -> int:
    root = project_root()
    credentials = load_credentials(require_bcch=True)
    config = load_project_config()
    client = BcchClient(
        config.bcch,
        credentials.bcch_api_user or "",
        credentials.bcch_api_password or "",
    )
    frequency = frequency.upper()
    destination = root / "data" / "raw" / "bcch" / f"catalog_{frequency.lower()}.json"
    downloaded = client.download_catalog(
        frequency,
        destination,
        root / "data" / "metadata" / "download_manifest.jsonl",
        overwrite=overwrite,
    )
    print(f"Catálogo BCCh {frequency}: {'descargado' if downloaded else 'ya existía'}")
    return 0


def search_bcch_catalog(query: str) -> int:
    root = project_root()
    catalog = load_catalog(root / "data" / "raw" / "bcch" / "catalog_monthly.json")
    words = query.casefold().split()
    matches = [
        item
        for item in catalog
        if all(word in str(item.get("spanishTitle", "")).casefold() for word in words)
    ]
    print(f"Coincidencias: {len(matches)}")
    for item in matches[:100]:
        print(
            f"{item.get('seriesId')} | {item.get('firstObservation')} | "
            f"{item.get('lastObservation')} | {item.get('spanishTitle')}"
        )
    return 0


def download_bcch_series(start: date, end: date, overwrite: bool) -> int:
    root = project_root()
    credentials = load_credentials(require_bcch=True)
    config = load_project_config()
    specs = load_series_specs(root / "configs" / "bcch_series.toml")
    client = BcchClient(
        config.bcch,
        credentials.bcch_api_user or "",
        credentials.bcch_api_password or "",
    )
    raw_directory = root / "data" / "raw" / "bcch"
    downloaded = 0
    for spec in specs:
        destination = raw_directory / f"series__{spec.name}.json"
        changed = client.download_series(
            spec.series_id,
            start,
            end,
            destination,
            root / "data" / "metadata" / "download_manifest.jsonl",
            overwrite=overwrite,
        )
        downloaded += changed
        print(f"- {spec.name}: {'descargada' if changed else 'ya existía'}")
    print(f"Series procesadas: {len(specs)}; descargadas: {downloaded}")
    return 0


def audit_bcch() -> int:
    root = project_root()
    specs = load_series_specs(root / "configs" / "bcch_series.toml")
    raw_directory = root / "data" / "raw" / "bcch"
    observations = {
        spec.name: parse_series_file(raw_directory / f"series__{spec.name}.json", spec)
        for spec in specs
    }
    reports = audit_series(
        specs,
        observations,
        target_start=date(2014, 3, 1),
        target_end=date(2026, 6, 1),
    )
    write_observations(observations, root / "data" / "interim" / "bcch_monthly.csv")
    write_coverage(reports, root / "data" / "metadata" / "bcch_coverage.csv")
    print("Cobertura BCCh sobre los 148 meses objetivo:")
    for report in reports:
        print(
            f"- {report.feature_name}: {report.target_period_observations}/148; "
            f"faltantes={report.missing_target_months}; fin={report.last_observation}"
        )
    return 0


def build_base() -> int:
    root = project_root()
    specs = load_series_specs(root / "configs" / "bcch_series.toml")
    raw_directory = root / "data" / "raw" / "bcch"
    features = {
        spec.name: parse_series_file(raw_directory / f"series__{spec.name}.json", spec)
        for spec in specs
    }
    rows, report = build_modeling_rows(
        load_target(root / "data" / "interim" / "cmf_npl90_consumption.csv"),
        load_publication_calendar(
            root / "data" / "metadata" / "cmf_publication_calendar.csv"
        ),
        specs,
        features,
        load_modeling_config(root / "configs" / "modeling.toml"),
    )
    write_modeling_base(rows, root / "data" / "processed" / "modeling_base.csv")
    write_modeling_coverage(
        report,
        root / "data" / "metadata" / "modeling_base_coverage.json",
    )
    print(
        f"Base: {report.rows} filas; desarrollo={report.development_rows}; "
        f"holdout={report.holdout_rows}; pronóstico={report.forecast_rows}"
    )
    print(
        f"Predictores={report.feature_count}; "
        f"faltantes={sum(report.missing_feature_values.values())}; "
        f"violaciones available_date={report.availability_violations}"
    )
    return 0 if report.availability_violations == 0 else 2


def build_features() -> int:
    root = project_root()
    config = load_feature_config(root / "configs" / "features.toml")
    rows, report = build_feature_rows(
        load_csv_rows(root / "data" / "processed" / "modeling_base.csv"),
        load_macro_history(root / "data" / "interim" / "bcch_monthly.csv"),
        config,
    )
    write_feature_rows(
        rows,
        root / "data" / "processed" / f"model_matrix_{config.name}.csv",
    )
    write_feature_metadata(
        config,
        report,
        root / "data" / "metadata" / "feature_set_v001.json",
        root / "data" / "metadata" / "feature_coverage.json",
    )
    print(
        f"Matriz {config.name}: {report.rows} filas; "
        f"variables={report.feature_count}; completas={report.complete_rows}"
    )
    print(
        f"Filas completas: desarrollo={report.development_complete_rows}; "
        f"holdout={report.holdout_complete_rows}; "
        f"pronóstico={report.forecast_complete_rows}"
    )
    return 0


def backtest_baselines() -> int:
    root = project_root()
    feature_config = load_feature_config(root / "configs" / "features.toml")
    predictions, metrics, folds, summary = run_backtest(
        load_model_matrix(
            root / "data" / "processed" / f"model_matrix_{feature_config.name}.csv"
        ),
        feature_config,
        load_validation_config(root / "configs" / "modeling.toml"),
    )
    tables = root / "reports" / "tables"
    write_csv(predictions, tables / "baseline_predictions_development.csv")
    write_csv(metrics, tables / "baseline_metrics_development.csv")
    write_backtest_metadata(
        folds,
        summary,
        root / "data" / "metadata" / "backtest_folds_v001.json",
    )
    print(
        f"Backtest: {summary.evaluation_origins} orígenes en {summary.folds} bloques; "
        f"holdout evaluado=0"
    )
    for row in metrics:
        if row["fold_id"] == "all":
            print(
                f"- {row['model']}: MAE={float(row['mae']):.4f}; "
                f"RMSE={float(row['rmse']):.4f}; "
                f"dirección={100 * float(row['directional_accuracy']):.1f}%"
            )
    return 0


def backtest_ml() -> int:
    root = project_root()
    feature_config = load_feature_config(root / "configs" / "features.toml")
    ml_config = load_ml_config(root / "configs" / "models.toml")
    matrix_path = (
        root / "data" / "processed" / f"model_matrix_{feature_config.name}.csv"
    )
    predictions, tuning, folds, summary = run_ml_backtest(
        load_model_matrix(matrix_path),
        feature_config,
        load_validation_config(root / "configs" / "modeling.toml"),
        ml_config,
    )
    tables = root / "reports" / "tables"
    baseline_predictions = load_csv_rows(
        tables / "baseline_predictions_development.csv"
    )
    baseline_origins = {row["observation_date"] for row in baseline_predictions}
    ml_origins = {row["observation_date"] for row in predictions}
    if baseline_origins != ml_origins:
        raise MlBacktestError("Los modelos ML no usan los mismos orígenes que los benchmarks")
    comparison = summarize_metrics([*baseline_predictions, *predictions])
    write_csv(predictions, tables / "ml_predictions_development.csv")
    write_csv(tuning, tables / "ml_tuning_development.csv")
    write_csv(comparison, tables / "model_comparison_development.csv")
    write_ml_metadata(
        ml_config,
        folds,
        summary,
        feature_names(feature_config),
        root / "data" / "metadata" / "ml_backtest_v001.json",
    )
    print(
        f"Backtest ML: {summary.evaluation_origins} orígenes; "
        f"ajustes internos={summary.inner_predictions_evaluated}; holdout evaluado=0"
    )
    for row in comparison:
        if row["fold_id"] == "all":
            print(
                f"- {row['model']}: MAE={float(row['mae']):.4f}; "
                f"mejora vs. cero={float(row['mae_improvement_vs_zero_pct']):.1f}%"
            )
    return 0


def analyze_robustness() -> int:
    root = project_root()
    feature_config = load_feature_config(root / "configs" / "features.toml")
    ml_config = load_ml_config(root / "configs" / "models.toml")
    robustness_config = load_robustness_config(root / "configs" / "robustness.toml")
    matrix = load_model_matrix(
        root
        / "data"
        / "processed"
        / f"model_matrix_{feature_config.name}.csv"
    )
    predictions, tuning, folds, summary = run_parsimonious_backtest(
        matrix,
        feature_config,
        load_validation_config(root / "configs" / "modeling.toml"),
        ml_config,
        robustness_config,
    )
    tables = root / "reports" / "tables"
    baseline_predictions = load_csv_rows(
        tables / "baseline_predictions_development.csv"
    )
    ml_predictions = load_csv_rows(tables / "ml_predictions_development.csv")
    existing_elastic = {
        row["observation_date"]: float(row["predicted_change_pp_h6"])
        for row in ml_predictions
        if row["model"] == "elastic_net"
    }
    full_elastic = {
        row["observation_date"]: float(row["predicted_change_pp_h6"])
        for row in predictions
        if row["model"] == "elastic_net_full_23"
    }
    if existing_elastic.keys() != full_elastic.keys() or any(
        abs(existing_elastic[item] - full_elastic[item]) > 1e-12
        for item in existing_elastic
    ):
        raise RobustnessError("La especificación full_23 no reproduce ElasticNet v1")

    comparison = summarize_metrics([*baseline_predictions, *predictions])
    stability_predictions = [
        *baseline_predictions,
        *ml_predictions,
        *[row for row in predictions if row["model"] != "elastic_net_full_23"],
    ]
    stability = stability_against_zero(stability_predictions, robustness_config)
    write_csv(predictions, tables / "parsimonious_predictions_development.csv")
    write_csv(tuning, tables / "parsimonious_tuning_development.csv")
    write_csv(comparison, tables / "parsimonious_model_comparison.csv")
    write_csv(stability, tables / "stability_vs_zero_development.csv")
    write_robustness_metadata(
        robustness_config,
        folds,
        summary,
        root / "data" / "metadata" / "robustness_v001.json",
    )
    print(
        f"Robustez: {summary.feature_sets} feature sets; "
        f"orígenes={summary.evaluation_origins}; holdout evaluado=0"
    )
    for row in comparison:
        if row["fold_id"] == "all" and row["model"].startswith("elastic_net_"):
            print(
                f"- {row['model']}: MAE={float(row['mae']):.4f}; "
                f"mejora vs. cero={float(row['mae_improvement_vs_zero_pct']):.1f}%"
            )
    return 0


def explain_models() -> int:
    root = project_root()
    feature_config = load_feature_config(root / "configs" / "features.toml")
    ml_config = load_ml_config(root / "configs" / "models.toml")
    explain_config = load_explainability_config(
        root / "configs" / "explainability.toml"
    )
    matrix = load_model_matrix(
        root
        / "data"
        / "processed"
        / f"model_matrix_{feature_config.name}.csv"
    )
    tables = root / "reports" / "tables"
    ml_predictions = load_csv_rows(tables / "ml_predictions_development.csv")
    baseline_predictions = load_csv_rows(
        tables / "baseline_predictions_development.csv"
    )
    attributions, summary = run_explainability(
        matrix,
        ml_predictions,
        feature_config,
        explain_config,
        ml_config.random_seed,
    )
    global_importance = aggregate_attributions(
        attributions,
        explain_config.coefficient_zero_tolerance,
        by_fold=False,
    )
    fold_importance = aggregate_attributions(
        attributions,
        explain_config.coefficient_zero_tolerance,
        by_fold=True,
    )
    rank_stability = driver_rank_stability(fold_importance)
    rank_correlations = fold_rank_correlations(fold_importance)
    critical_months = build_critical_months(
        matrix,
        baseline_predictions,
        ml_predictions,
        attributions,
        explain_config,
    )
    summary = replace(summary, critical_months=len(critical_months))
    write_csv(attributions, tables / "feature_attributions_oos.csv")
    write_csv(global_importance, tables / "feature_importance_global.csv")
    write_csv(fold_importance, tables / "feature_importance_by_fold.csv")
    write_csv(rank_stability, tables / "driver_rank_stability.csv")
    write_csv(rank_correlations, tables / "fold_rank_correlations.csv")
    write_csv(critical_months, tables / "critical_months.csv")
    write_explainability_metadata(
        explain_config,
        summary,
        root / "data" / "metadata" / "explainability_v001.json",
    )
    write_explainability_figures(
        global_importance,
        baseline_predictions,
        ml_predictions,
        root / "reports" / "figures",
        explain_config.top_global_features,
    )
    print(
        f"Explicabilidad: modelos={summary.models}; orígenes={summary.evaluation_origins}; "
        f"atribuciones={summary.attribution_rows}; holdout explicado=0"
    )
    for model_name in explain_config.models:
        top = [
            row
            for row in global_importance
            if row["model"] == model_name
            and float(row["rank"]) <= explain_config.top_global_features
        ][:3]
        print(f"- {model_name}: " + ", ".join(row["feature"] for row in top))
    return 0


def analyze_horizons() -> int:
    root = project_root()
    feature_config = load_feature_config(root / "configs" / "features.toml")
    ml_config = load_ml_config(root / "configs" / "models.toml")
    horizon_config = load_horizon_robustness_config(
        root / "configs" / "horizon_robustness.toml"
    )
    matrix = load_model_matrix(
        root
        / "data"
        / "processed"
        / f"model_matrix_{feature_config.name}.csv"
    )
    predictions, tuning, folds, summary = run_horizon_robustness(
        matrix,
        load_publication_calendar(
            root / "data" / "metadata" / "cmf_publication_calendar.csv"
        ),
        feature_config,
        load_validation_config(root / "configs" / "modeling.toml"),
        ml_config,
        horizon_config,
    )
    tables = root / "reports" / "tables"
    existing_predictions = load_csv_rows(tables / "ml_predictions_development.csv")
    existing_h6 = {
        row["observation_date"]: float(row["predicted_change_pp_h6"])
        for row in existing_predictions
        if row["model"] == "elastic_net"
    }
    reproduced_h6 = {
        row["observation_date"]: float(row["predicted_change_pp"])
        for row in predictions
        if row["scenario"] == "h6_expanding" and row["model"] == "elastic_net"
    }
    if existing_h6.keys() != reproduced_h6.keys() or any(
        abs(existing_h6[item] - reproduced_h6[item]) > 1e-12 for item in existing_h6
    ):
        raise HorizonRobustnessError("h6_expanding no reproduce el challenger congelado")

    metrics = summarize_horizon_metrics(predictions)
    bootstrap = horizon_bootstrap(predictions, horizon_config)
    window_comparison = window_bootstrap(predictions, horizon_config)
    write_csv(predictions, tables / "horizon_robustness_predictions.csv")
    write_csv(tuning, tables / "horizon_robustness_tuning.csv")
    write_csv(metrics, tables / "horizon_robustness_metrics.csv")
    write_csv(bootstrap, tables / "horizon_robustness_bootstrap.csv")
    write_csv(window_comparison, tables / "horizon_window_comparison.csv")
    write_horizon_metadata(
        horizon_config,
        folds,
        summary,
        root / "data" / "metadata" / "horizon_robustness_v001.json",
    )
    write_horizon_figure(
        metrics,
        root / "reports" / "figures" / "horizon_robustness.png",
    )
    print(
        f"Horizontes: escenarios={summary.scenarios}; "
        f"orígenes por escenario={summary.evaluation_origins_per_scenario}; "
        f"holdout evaluado=0"
    )
    for row in metrics:
        if row["fold_id"] == "all" and row["model"] == "elastic_net":
            print(
                f"- {row['scenario']}: MAE={float(row['mae']):.4f}; "
                f"mejora vs. cero={float(row['mae_improvement_vs_zero_pct']):.1f}%"
            )
    return 0


def backtest_stress() -> int:
    root = project_root()
    feature_config = load_feature_config(root / "configs" / "features.toml")
    stress_config = load_stress_alert_config(
        root / "configs" / "stress_alert.toml"
    )
    matrix = load_model_matrix(
        root
        / "data"
        / "processed"
        / f"model_matrix_{feature_config.name}.csv"
    )
    predictions, tuning, threshold_tuning, folds, summary = (
        run_stress_alert_backtest(
            matrix,
            feature_config,
            load_validation_config(root / "configs" / "modeling.toml"),
            stress_config,
        )
    )
    tables = root / "reports" / "tables"
    baseline_predictions = load_csv_rows(
        tables / "baseline_predictions_development.csv"
    )
    baseline_origins = {row["observation_date"] for row in baseline_predictions}
    alert_origins = {row["observation_date"] for row in predictions}
    if baseline_origins != alert_origins:
        raise StressAlertError("La alerta no usa los mismos orígenes del backtest")

    metrics = summarize_stress_metrics(predictions)
    calibration = build_calibration_table(
        predictions, stress_config.calibration_bins
    )
    bootstrap = brier_bootstrap(predictions, stress_config)
    errors = classification_errors(predictions)
    episodes = episode_detection(predictions)
    write_csv(predictions, tables / "stress_alert_predictions_development.csv")
    write_csv(tuning, tables / "stress_alert_tuning_development.csv")
    write_csv(
        threshold_tuning,
        tables / "stress_alert_threshold_tuning_development.csv",
    )
    write_csv(metrics, tables / "stress_alert_metrics_development.csv")
    write_csv(calibration, tables / "stress_alert_calibration_development.csv")
    write_csv(bootstrap, tables / "stress_alert_brier_bootstrap.csv")
    write_csv(errors, tables / "stress_alert_errors_development.csv")
    write_csv(episodes, tables / "stress_alert_episode_detection.csv")
    write_stress_metadata(
        stress_config,
        folds,
        summary,
        feature_names(feature_config),
        root / "data" / "metadata" / "stress_alert_v001.json",
    )
    write_stress_figure(
        predictions,
        calibration,
        root / "reports" / "figures" / "stress_alert_evaluation.png",
    )
    print(
        f"Alertas: orígenes={summary.evaluation_origins}; "
        f"modelos={summary.models_including_benchmark}; holdout evaluado=0"
    )
    for row in metrics:
        if row["fold_id"] == "all":
            print(
                f"- {row['model']}: AP={float(row['average_precision']):.3f}; "
                f"Brier={float(row['brier_score']):.3f}; "
                f"recall={100 * float(row['recall']):.1f}%; "
                f"precision={100 * float(row['precision']):.1f}%"
            )
    return 0


def close_technical() -> int:
    root = project_root()
    config = load_technical_closure_config(
        root / "configs" / "technical_closure.toml"
    )
    feature_config = load_feature_config(root / "configs" / "features.toml")
    matrix = load_model_matrix(
        root
        / "data"
        / "processed"
        / f"model_matrix_{feature_config.name}.csv"
    )
    tables = root / "reports" / "tables"
    baseline = load_csv_rows(tables / "baseline_predictions_development.csv")
    ml = load_csv_rows(tables / "ml_predictions_development.csv")
    regression_predictions = [
        row
        for row in [*baseline, *ml]
        if row["model"] in config.expected_regression_models
    ]
    alert_predictions = load_csv_rows(
        tables / "stress_alert_predictions_development.csv"
    )
    evaluation_dates = {row["observation_date"] for row in regression_predictions}
    membership = build_regime_membership(matrix, evaluation_dates, config)
    regression_regimes = evaluate_regression_by_regime(
        regression_predictions, membership, config
    )
    alert_regimes = evaluate_alerts_by_regime(
        alert_predictions, membership, config
    )
    write_csv(membership, tables / "regime_membership_development.csv")
    write_csv(regression_regimes, tables / "regression_metrics_by_regime.csv")
    write_csv(alert_regimes, tables / "stress_alert_metrics_by_regime.csv")
    write_regime_figure(
        regression_regimes,
        alert_regimes,
        root / "reports" / "figures" / "regime_performance.png",
    )
    write_model_card(
        load_csv_rows(tables / "model_comparison_development.csv"),
        load_csv_rows(tables / "stress_alert_metrics_development.csv"),
        regression_regimes,
        root / "docs" / "model_card_v1.md",
    )
    write_technical_report(
        regression_regimes,
        alert_regimes,
        root / "docs" / "technical_closure_v1.md",
    )
    acceptance = build_acceptance_report(root, config)
    write_json(
        acceptance,
        root / "data" / "metadata" / "technical_acceptance_v001.json",
    )
    manifest = build_reproduction_manifest(root, config)
    write_json(
        manifest,
        root / "data" / "metadata" / "reproduction_manifest_v001.json",
    )
    print(
        f"Cierre técnico: checks={acceptance['checks_passed']}/"
        f"{acceptance['checks_total']}; archivos con hash={manifest['file_count']}; "
        "holdout evaluado=0"
    )
    return 0 if acceptance["status"] == "passed" else 2


def run_all_local() -> int:
    stages = (
        ("auditoría CMF", audit_cmf),
        ("calendario CMF", build_cmf_calendar),
        ("auditoría Banco Central", audit_bcch),
        ("base point-in-time", build_base),
        ("features", build_features),
        ("benchmarks", backtest_baselines),
        ("modelos ML", backtest_ml),
        ("robustez", analyze_robustness),
        ("explicabilidad", explain_models),
        ("horizontes", analyze_horizons),
        ("alerta de estrés", backtest_stress),
        ("cierre técnico", close_technical),
    )
    for index, (name, stage) in enumerate(stages, start=1):
        print(f"[{index}/{len(stages)}] {name}")
        code = stage()
        if code != 0:
            raise TechnicalClosureError(
                f"La etapa '{name}' terminó con código {code}"
            )
    print("Pipeline local completo.")
    return 0


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check-config":
            code = check_config()
        elif args.command == "download-cmf":
            code = download_cmf(args.from_date, args.to_date, args.overwrite)
        elif args.command == "audit-cmf":
            code = audit_cmf()
        elif args.command == "download-cmf-calendar":
            code = download_cmf_calendar(args.overwrite)
        elif args.command == "build-cmf-calendar":
            code = build_cmf_calendar()
        elif args.command == "download-bcch-catalog":
            code = download_bcch_catalog(args.frequency, args.overwrite)
        elif args.command == "search-bcch-catalog":
            code = search_bcch_catalog(args.query)
        elif args.command == "download-bcch-series":
            code = download_bcch_series(args.from_date, args.to_date, args.overwrite)
        elif args.command == "audit-bcch":
            code = audit_bcch()
        elif args.command == "build-modeling-base":
            code = build_base()
        elif args.command == "build-features":
            code = build_features()
        elif args.command == "backtest-baselines":
            code = backtest_baselines()
        elif args.command == "backtest-ml":
            code = backtest_ml()
        elif args.command == "analyze-robustness":
            code = analyze_robustness()
        elif args.command == "explain-models":
            code = explain_models()
        elif args.command == "analyze-horizons":
            code = analyze_horizons()
        elif args.command == "backtest-stress":
            code = backtest_stress()
        elif args.command == "close-technical":
            code = close_technical()
        else:
            code = run_all_local()
    except (
        BacktestError,
        BcchApiError,
        ConfigurationError,
        BestApiError,
        FeatureEngineeringError,
        HorizonRobustnessError,
        ExplainabilityError,
        MlBacktestError,
        ModelingBaseError,
        PublicationCalendarError,
        RobustnessError,
        StressAlertError,
        TargetDataError,
        TechnicalClosureError,
        TemporalValidationError,
        ValueError,
    ) as error:
        raise SystemExit(f"Error: {error}") from None
    raise SystemExit(code)
