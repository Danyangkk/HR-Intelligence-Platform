from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.metrics.dictionary import MetricDefinition, get_metric, get_metric_by_id


class CalcError(ValueError):
    pass


@dataclass
class CalcResult:
    metric: str
    metric_id: str
    value: float
    formatted: str
    formula: str
    unit: str
    inputs_used: dict[str, float]
    citation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "metric_id": self.metric_id,
            "value": self.value,
            "formatted": self.formatted,
            "formula": self.formula,
            "unit": self.unit,
            "inputs_used": self.inputs_used,
            "citation": self.citation,
        }


def _num(value: Any, field: str) -> float:
    if value is None or value == "":
        raise CalcError(f"缺少输入：{field}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise CalcError(f"输入无效：{field}={value!r}") from exc


def _resolve_inputs(definition: MetricDefinition, inputs: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for field in definition.inputs:
        if field not in inputs:
            raise CalcError(f"缺少输入：{field}")
        out[field] = _num(inputs[field], field)
    return out


def calculate_metric(
    name_or_id: str,
    inputs: dict[str, Any],
    *,
    _stack: set[str] | None = None,
) -> CalcResult:
    definition = get_metric(name_or_id)
    if not definition:
        raise CalcError(f"未知指标：{name_or_id}")

    stack = set(_stack or ())
    if definition.id in stack:
        raise CalcError(f"指标循环依赖：{definition.name}")
    stack.add(definition.id)

    working_inputs = dict(inputs)
    if definition.depends_on:
        base_field = definition.inputs[0]
        if base_field not in working_inputs:
            for dep_id in definition.depends_on:
                dep = get_metric_by_id(dep_id)
                if not dep:
                    continue
                nested = calculate_metric(dep.name, working_inputs, _stack=stack)
                working_inputs[base_field] = nested.value

    resolved_inputs = _resolve_inputs(definition, working_inputs)
    value = _eval(definition, resolved_inputs)
    return _build_result(definition, value, resolved_inputs)


def calculate_operation(
    operation: str,
    *,
    numerator: float | None = None,
    denominator: float | None = None,
    current: float | None = None,
    previous: float | None = None,
    metric: str | None = None,
) -> CalcResult:
    op = operation.strip().lower()
    if op in {"ratio", "rate"}:
        if numerator is None or denominator is None:
            raise CalcError("ratio 需要 numerator 与 denominator")
        if denominator == 0:
            raise CalcError("分母不能为 0")
        value = float(numerator) / float(denominator)
        definition = get_metric(metric) if metric else None
        formula = definition.formula if definition else "分子 / 分母"
        name = definition.name if definition else "比率"
        metric_id = definition.id if definition else "ratio"
        unit = definition.unit if definition else "ratio"
        inputs_used = {"numerator": float(numerator), "denominator": float(denominator)}
    elif op in {"mom", "环比", "cost_mom"}:
        if current is None or previous is None:
            raise CalcError("mom 需要 current 与 previous")
        if previous == 0:
            raise CalcError("上期不能为 0")
        value = (float(current) - float(previous)) / float(previous)
        definition = get_metric(metric or "成本环比")
        formula = definition.formula if definition else "(本期 − 上期) / 上期"
        name = definition.name if definition else "环比"
        metric_id = definition.id if definition else "cost_mom"
        unit = definition.unit if definition else "ratio"
        inputs_used = {"本期": float(current), "上期": float(previous)}
    elif op in {"yoy", "同比", "cost_yoy"}:
        if current is None or previous is None:
            raise CalcError("yoy 需要 current 与 previous")
        if previous == 0:
            raise CalcError("去年同期不能为 0")
        value = (float(current) - float(previous)) / float(previous)
        definition = get_metric(metric or "成本同比")
        formula = definition.formula if definition else "(本期 − 去年同期) / 去年同期"
        name = definition.name if definition else "同比"
        metric_id = definition.id if definition else "cost_yoy"
        unit = definition.unit if definition else "ratio"
        inputs_used = {"本期": float(current), "去年同期": float(previous)}
    else:
        raise CalcError(f"不支持的操作：{operation}")

    citation = f"{name} = {formula}"
    return CalcResult(
        metric=name,
        metric_id=metric_id,
        value=value,
        formatted=_format_value(unit, value),
        formula=formula,
        unit=unit,
        inputs_used=inputs_used,
        citation=citation,
    )


def _eval(definition: MetricDefinition, inputs: dict[str, float]) -> float:
    vt = definition.value_type
    if vt == "count":
        if len(definition.inputs) != 1:
            raise CalcError(f"count 指标配置错误：{definition.name}")
        return inputs[definition.inputs[0]]
    if vt == "ratio":
        num_key, den_key = definition.inputs[0], definition.inputs[1]
        den = inputs[den_key]
        if den == 0:
            raise CalcError(f"分母不能为 0：{den_key}")
        return inputs[num_key] / den
    if vt == "average":
        a, b = definition.inputs[0], definition.inputs[1]
        return (inputs[a] + inputs[b]) / 2
    if vt == "complement":
        base = inputs[definition.inputs[0]]
        return 1.0 - base
    if vt == "subtract":
        a, b = definition.inputs[0], definition.inputs[1]
        return inputs[a] - inputs[b]
    if vt == "diff_positive":
        a, b = definition.inputs[0], definition.inputs[1]
        return max(inputs[a] - inputs[b], 0.0)
    if vt in {"mom", "yoy"}:
        current, previous = definition.inputs[0], definition.inputs[1]
        if inputs[previous] == 0:
            raise CalcError(f"分母不能为 0：{previous}")
        return (inputs[current] - inputs[previous]) / inputs[previous]
    raise CalcError(f"未实现的指标类型：{vt}")


def _format_value(unit: str, value: float) -> str:
    if unit == "ratio":
        return f"{value * 100:.2f}%"
    if unit == "count":
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:.2f}"
    if unit == "currency":
        return f"{value:,.2f}"
    if unit in {"hours", "score"}:
        return f"{value:.2f}"
    return f"{value:.4f}"


def _build_result(
    definition: MetricDefinition,
    value: float,
    inputs_used: dict[str, float],
) -> CalcResult:
    citation = f"{definition.name} = {definition.formula}"
    if definition.notes:
        citation = f"{citation}（{definition.notes}）"
    return CalcResult(
        metric=definition.name,
        metric_id=definition.id,
        value=value,
        formatted=_format_value(definition.unit, value),
        formula=definition.formula,
        unit=definition.unit,
        inputs_used=inputs_used,
        citation=citation,
    )
