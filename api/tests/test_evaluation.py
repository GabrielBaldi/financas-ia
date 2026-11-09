import json
from functools import partial
from pathlib import Path

import httpx2
import pytest

from financas.categories import Category
from financas.categorization import factory
from financas.categorization.pipeline import Categorizer
from financas.config import Settings
from financas.evaluation import DEFAULT_DATASET, LabeledTransaction, evaluate, load_dataset, run
from tests.helpers import FakeClassifier, make_settings


def test_dataset_has_about_100_rows_and_every_category() -> None:
    dataset = load_dataset(DEFAULT_DATASET)

    assert len(dataset) >= 100
    assert {item.expected for item in dataset} == set(Category)


def test_metrics_separate_coverage_from_accuracy() -> None:
    dataset = [
        LabeledTransaction("UBER *TRIP", -2000, Category.TRANSPORTE),  # rule, right
        LabeledTransaction("MERCADO PAGO*ROUPAS", -9000, Category.COMPRAS),  # rule, wrong
        LabeledTransaction("SUMUP *BISTRO", -5000, Category.ALIMENTACAO),  # AI, right
        LabeledTransaction("PAG*DESCONHECIDO", -1000, Category.OUTROS),  # nobody knows
    ]
    ai = FakeClassifier({"SUMUP *BISTRO": (Category.ALIMENTACAO, 0.9)})

    report = evaluate(dataset, Categorizer(ai))

    assert report.coverage == 0.75
    assert report.precision == 2 / 3
    assert report.accuracy == 0.5
    assert [item.description for item, _ in report.mistakes] == ["MERCADO PAGO*ROUPAS"]
    assert [item.description for item in report.left_for_review] == ["PAG*DESCONHECIDO"]


def test_ai_part_is_skipped_without_a_key(settings: Settings) -> None:
    output = run(DEFAULT_DATASET, settings)

    assert "== Só regras ==" in output
    assert "Pulado: defina ANTHROPIC_API_KEY ou NVIDIA_API_KEY para medir." in output


def fake_nvidia(request: httpx2.Request) -> httpx2.Response:
    """Answers "outros" with high confidence for every transaction it is sent."""
    user_message = json.loads(request.content)["messages"][1]["content"]
    ids = [json.loads(line)["id"] for line in user_message.splitlines()[1:]]
    answer = {"results": [{"id": i, "category": "outros", "confidence": 0.9} for i in ids]}
    return httpx2.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(answer)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1500, "completion_tokens": 300},
        },
    )


def test_with_an_nvidia_key_it_measures_rules_plus_nvidia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        factory,
        "make_openai_compatible_classifier",
        partial(
            factory.make_openai_compatible_classifier, transport=httpx2.MockTransport(fake_nvidia)
        ),
    )

    output = run(DEFAULT_DATASET, make_settings(nvidia_api_key="nvapi-teste"))

    assert "== Regras + IA (NVIDIA · minimaxai/minimax-m3.1-flash) ==" in output
    assert "Cobertura (categorizadas):  100.0% (102)" in output
    assert "Tokens: 1500 entrada / 300 saída" in output
    assert "custo estimado" not in output  # no price is configured for NVIDIA


def test_with_an_anthropic_key_it_measures_rules_plus_claude_and_the_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(factory, "make_claude_classifier", lambda *_: FakeClassifier())

    output = run(DEFAULT_DATASET, make_settings(anthropic_api_key="sk-ant-teste"))

    assert "== Regras + IA (Anthropic · claude-haiku-5-5) ==" in output
    assert "(custo estimado US$ " in output


def test_custom_dataset_path(tmp_path: Path, settings: Settings) -> None:
    dataset = tmp_path / "mini.csv"
    dataset.write_text("descricao;valor;categoria\nNETFLIX.COM;-39,90;assinaturas\n", "utf-8")

    assert "Cobertura (categorizadas):  100.0% (1)" in run(dataset, settings)
