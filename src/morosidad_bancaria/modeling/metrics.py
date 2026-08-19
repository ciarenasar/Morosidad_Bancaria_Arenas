"""Métricas de pronóstico implementadas sin dependencias obligatorias."""

from __future__ import annotations

import math
import statistics


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def regression_metrics(actual: list[float], predicted: list[float]) -> dict[str, float | None]:
    if not actual or len(actual) != len(predicted):
        raise ValueError("Las métricas requieren vectores no vacíos del mismo largo")
    errors = [forecast - observed for observed, forecast in zip(actual, predicted)]
    absolute = [abs(value) for value in errors]
    mae = sum(absolute) / len(absolute)
    rmse = math.sqrt(sum(value * value for value in errors) / len(errors))
    directional = sum(
        _sign(observed) == _sign(forecast)
        for observed, forecast in zip(actual, predicted)
    ) / len(actual)

    actual_mean = sum(actual) / len(actual)
    predicted_mean = sum(predicted) / len(predicted)
    covariance = sum(
        (observed - actual_mean) * (forecast - predicted_mean)
        for observed, forecast in zip(actual, predicted)
    )
    actual_ss = sum((value - actual_mean) ** 2 for value in actual)
    predicted_ss = sum((value - predicted_mean) ** 2 for value in predicted)
    correlation = (
        covariance / math.sqrt(actual_ss * predicted_ss)
        if actual_ss > 0 and predicted_ss > 0
        else None
    )
    return {
        "n": len(actual),
        "mae": mae,
        "rmse": rmse,
        "median_absolute_error": statistics.median(absolute),
        "directional_accuracy": directional,
        "correlation": correlation,
    }


def _average_precision(actual: list[int], probability: list[float]) -> float | None:
    positives = sum(actual)
    if positives == 0:
        return None
    grouped: dict[float, list[int]] = {}
    for observed, score in zip(actual, probability):
        grouped.setdefault(score, []).append(observed)
    true_positives = 0
    false_positives = 0
    previous_recall = 0.0
    result = 0.0
    for score in sorted(grouped, reverse=True):
        labels = grouped[score]
        true_positives += sum(labels)
        false_positives += len(labels) - sum(labels)
        recall = true_positives / positives
        precision = true_positives / (true_positives + false_positives)
        result += precision * (recall - previous_recall)
        previous_recall = recall
    return result


def _roc_auc(actual: list[int], probability: list[float]) -> float | None:
    positive = [score for label, score in zip(actual, probability) if label == 1]
    negative = [score for label, score in zip(actual, probability) if label == 0]
    if not positive or not negative:
        return None
    wins = sum(
        1.0 if positive_score > negative_score else 0.5
        for positive_score in positive
        for negative_score in negative
        if positive_score >= negative_score
    )
    return wins / (len(positive) * len(negative))


def classification_metrics(
    actual: list[int],
    probability: list[float],
    *,
    decision_threshold: float = 0.5,
    predicted: list[int] | None = None,
) -> dict[str, float | int | None]:
    """Calcula métricas binarias, incluidas ranking, calibración y confusión."""
    if not actual or len(actual) != len(probability):
        raise ValueError("Las métricas requieren vectores no vacíos del mismo largo")
    if any(label not in (0, 1) for label in actual):
        raise ValueError("Las etiquetas de clasificación deben ser cero o uno")
    if any(not math.isfinite(score) or not 0.0 <= score <= 1.0 for score in probability):
        raise ValueError("Las probabilidades deben estar entre cero y uno")
    if predicted is None:
        if not 0.0 <= decision_threshold <= 1.0:
            raise ValueError("El umbral de decisión debe estar entre cero y uno")
        predicted = [int(score >= decision_threshold) for score in probability]
    if len(predicted) != len(actual) or any(label not in (0, 1) for label in predicted):
        raise ValueError("Las predicciones binarias deben ser cero o uno")

    true_positive = sum(y == 1 and forecast == 1 for y, forecast in zip(actual, predicted))
    false_positive = sum(y == 0 and forecast == 1 for y, forecast in zip(actual, predicted))
    true_negative = sum(y == 0 and forecast == 0 for y, forecast in zip(actual, predicted))
    false_negative = sum(y == 1 and forecast == 0 for y, forecast in zip(actual, predicted))
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    specificity = (
        true_negative / (true_negative + false_positive)
        if true_negative + false_positive
        else 0.0
    )
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    prevalence = sum(actual) / len(actual)
    mean_probability = sum(probability) / len(probability)
    return {
        "n": len(actual),
        "events": sum(actual),
        "prevalence": prevalence,
        "average_precision": _average_precision(actual, probability),
        "roc_auc": _roc_auc(actual, probability),
        "brier_score": sum(
            (score - observed) ** 2
            for observed, score in zip(actual, probability)
        )
        / len(actual),
        "mean_probability": mean_probability,
        "calibration_bias": mean_probability - prevalence,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "balanced_accuracy": (recall + specificity) / 2.0,
        "alert_rate": sum(predicted) / len(predicted),
        "true_positives": true_positive,
        "false_positives": false_positive,
        "true_negatives": true_negative,
        "false_negatives": false_negative,
    }
