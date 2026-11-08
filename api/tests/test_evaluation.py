from pathlib import Path

from financas.categories import Category
from financas.categorization.pipeline import Categorizer
from financas.config import Settings
from financas.evaluation import DEFAULT_DATASET, LabeledTransaction, evaluate, load_dataset, run
from tests.helpers import FakeClassifier


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
    assert "Pulado: defina ANTHROPIC_API_KEY" in output


def test_custom_dataset_path(tmp_path: Path, settings: Settings) -> None:
    dataset = tmp_path / "mini.csv"
    dataset.write_text("descricao;valor;categoria\nNETFLIX.COM;-39,90;assinaturas\n", "utf-8")

    assert "Cobertura (categorizadas):  100.0% (1)" in run(dataset, settings)
