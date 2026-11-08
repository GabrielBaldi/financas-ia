"""Measure the pipeline on a labeled set of fictional transactions.

    uv run python -m financas.evaluation [--dataset eval/transacoes_rotuladas.csv]

Always measures the rules alone. With ANTHROPIC_API_KEY set it also measures rules + AI and
reports the tokens and the estimated cost; without a key that part is skipped.
"""

import argparse
import csv
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from financas.categories import Category, Source
from financas.categorization.ai import TokenUsage, make_claude_classifier
from financas.categorization.pipeline import Categorizer, Decision, TransactionText
from financas.config import Settings, get_settings
from financas.importers.values import parse_amount
from financas.services.imports import AIPricing

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "eval" / "transacoes_rotuladas.csv"


@dataclass(frozen=True, slots=True)
class LabeledTransaction:
    description: str
    amount_cents: int
    expected: Category


@dataclass(frozen=True, slots=True)
class EvalReport:
    total: int
    decided: Counter[Source]  # how many each layer categorized
    correct: Counter[Source]  # how many of those were right
    mistakes: list[tuple[LabeledTransaction, Decision]]
    left_for_review: list[LabeledTransaction]
    usage: TokenUsage

    @property
    def categorized(self) -> int:
        return sum(self.decided.values())

    @property
    def coverage(self) -> float:
        return self.categorized / self.total

    @property
    def precision(self) -> float:
        """Accuracy among the transactions that got a category."""
        return sum(self.correct.values()) / self.categorized if self.categorized else 0.0

    @property
    def accuracy(self) -> float:
        """Accuracy over everything: a transaction left 'A revisar' counts as a miss."""
        return sum(self.correct.values()) / self.total


def load_dataset(path: Path) -> list[LabeledTransaction]:
    with path.open(encoding="utf-8", newline="") as file:
        return [
            LabeledTransaction(
                row["descricao"], parse_amount(row["valor"], ","), Category(row["categoria"])
            )
            for row in csv.DictReader(file, delimiter=";")
        ]


def evaluate(dataset: Sequence[LabeledTransaction], categorizer: Categorizer) -> EvalReport:
    result = categorizer.categorize(
        [TransactionText(item.description, item.amount_cents) for item in dataset], user_rules=[]
    )
    decided: Counter[Source] = Counter()
    correct: Counter[Source] = Counter()
    mistakes = []
    left_for_review = []
    for item, decision in zip(dataset, result.decisions, strict=True):
        if decision.category is None:
            left_for_review.append(item)
            continue
        decided[decision.source] += 1
        if decision.category is item.expected:
            correct[decision.source] += 1
        else:
            mistakes.append((item, decision))
    return EvalReport(len(dataset), decided, correct, mistakes, left_for_review, result.usage)


def format_report(title: str, report: EvalReport, pricing: AIPricing | None = None) -> str:
    lines = [
        f"== {title} ==",
        f"Transações:                 {report.total}",
        f"Cobertura (categorizadas):  {report.coverage:.1%} ({report.categorized})",
        f"Acerto nas categorizadas:   {report.precision:.1%}",
        f'Acerto geral:               {report.accuracy:.1%} ("A revisar" conta como erro)',
    ]
    for source in (Source.KEYWORD, Source.AI):
        if report.decided[source]:
            lines.append(
                f"  {source.value:<8} decidiu {report.decided[source]:>3}, "
                f"acertou {report.correct[source]:>3}"
            )
    if pricing is not None:
        cost = pricing.cost_usd(report.usage)
        lines.append(
            f"Tokens: {report.usage.input_tokens} entrada / {report.usage.output_tokens} saída"
            f" (custo estimado US$ {cost:.4f})"
        )
    if report.mistakes:
        lines.append("Erros:")
        lines.extend(
            f"  {item.description!r}: esperado {item.expected.value}, "
            f"veio {decision.category} ({decision.source.value})"
            for item, decision in report.mistakes
        )
    if report.left_for_review:
        lines.append("Ficaram para revisão:")
        lines.extend(f"  {item.description!r}" for item in report.left_for_review)
    return "\n".join(lines)


def run(dataset_path: Path, settings: Settings) -> str:
    dataset = load_dataset(dataset_path)
    sections = [format_report("Só regras", evaluate(dataset, Categorizer(None)))]

    if settings.anthropic_api_key is None:
        sections.append("== Regras + IA ==\nPulado: defina ANTHROPIC_API_KEY para medir.")
    else:
        classifier = make_claude_classifier(
            settings.anthropic_api_key.get_secret_value(), settings.ai_model
        )
        categorizer = Categorizer(classifier, settings.ai_min_confidence, settings.ai_batch_size)
        pricing = AIPricing(settings.ai_input_price_per_mtok, settings.ai_output_price_per_mtok)
        report = evaluate(dataset, categorizer)
        sections.append(format_report(f"Regras + IA ({settings.ai_model})", report, pricing))
    return "\n\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    print(run(args.dataset, get_settings()))


if __name__ == "__main__":
    main()
