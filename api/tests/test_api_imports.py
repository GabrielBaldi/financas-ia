import pytest
from fastapi.testclient import TestClient

from financas.app import create_app
from financas.categories import Category
from financas.config import Settings
from tests.helpers import SAMPLES, FakeClassifier, make_settings, register_and_login, upload

STATEMENT = """data;descrição;valor
01/10/2026;Compra no débito - Padaria Pão Quente;-12,00
01/10/2026;Compra no débito - Padaria Pão Quente;-12,00
02/10/2026;SUMUP *RECANTO VERDE;-64,00
03/10/2026;MP *LOJADOZE;-39,90
"""


def test_import_reports_what_each_layer_did(
    client: TestClient, headers: dict[str, str], fake_ai: FakeClassifier
) -> None:
    fake_ai.answers["SUMUP *RECANTO VERDE"] = (Category.ALIMENTACAO, 0.9)

    summary = upload(client, headers, STATEMENT)

    assert summary["file_format"] == "csv_generico"
    assert summary["account"] == {"id": 1, "name": "Conta Nubank"}
    assert (summary["total_rows"], summary["inserted"], summary["duplicates"]) == (4, 4, 0)
    assert (summary["by_keyword"], summary["by_ai"], summary["to_review"]) == (2, 1, 1)
    assert (summary["ai_input_tokens"], summary["ai_output_tokens"]) == (200, 40)
    assert summary["ai_cost_usd"] == (200 * 0.10 + 40 * 0.50) / 1_000_000


@pytest.mark.usefixtures("session_factory")  # creates the tables
def test_nvidia_imports_record_tokens_but_no_cost(
    settings: Settings, fake_ai: FakeClassifier
) -> None:
    """No price is configured for NVIDIA: Claude's prices must not be used to guess one."""
    nvidia = make_settings(database_url=settings.database_url, nvidia_api_key="nvapi-test")
    fake_ai.answers["SUMUP *RECANTO VERDE"] = (Category.ALIMENTACAO, 0.9)

    with TestClient(create_app(nvidia, classifier=fake_ai)) as client:
        summary = upload(client, register_and_login(client), STATEMENT)

    assert (summary["ai_input_tokens"], summary["ai_output_tokens"]) == (200, 40)
    assert summary["ai_cost_usd"] == 0


def test_reimporting_the_same_file_adds_nothing(
    client: TestClient, headers: dict[str, str]
) -> None:
    upload(client, headers, STATEMENT)

    again = upload(client, headers, STATEMENT)

    assert (again["inserted"], again["duplicates"]) == (0, 4)
    assert client.get("/transactions", headers=headers).json()["total"] == 4


def test_overlapping_statements_only_add_the_new_rows(
    client: TestClient, headers: dict[str, str]
) -> None:
    upload(client, headers, STATEMENT)

    overlap = upload(client, headers, STATEMENT + "04/10/2026;Farmácia Central;-25,00\n")

    assert (overlap["inserted"], overlap["duplicates"]) == (1, 4)


def test_the_same_row_in_another_account_is_not_a_duplicate(
    client: TestClient, headers: dict[str, str]
) -> None:
    upload(client, headers, STATEMENT, account="Conta Nubank")

    other = upload(client, headers, STATEMENT, account="Cartão Nubank")

    assert other["inserted"] == 4


def test_every_sample_file_imports(client: TestClient, headers: dict[str, str]) -> None:
    for sample in sorted(SAMPLES.iterdir()):
        summary = upload(client, headers, sample.read_bytes(), filename=sample.name)
        assert summary["inserted"] == summary["total_rows"], sample.name

    history = client.get("/imports", headers=headers).json()
    assert [item["filename"] for item in history][-1] == "extrato-generico.csv"


def test_bad_files_get_a_400_with_the_reason(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(
        "/imports",
        headers=headers,
        files={"file": ("planilha.csv", b"nome,idade\nAna,30\n", "text/csv")},
        data={"account_name": "Conta"},
    )

    assert response.status_code == 400
    assert "Formato não reconhecido" in response.json()["detail"]


def test_files_over_2_mb_are_refused(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(
        "/imports",
        headers=headers,
        files={"file": ("enorme.csv", b"x" * (2 * 1024 * 1024 + 1), "text/csv")},
        data={"account_name": "Conta"},
    )

    assert response.status_code == 413


def test_account_name_is_required(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(
        "/imports",
        headers=headers,
        files={"file": ("extrato.csv", STATEMENT.encode(), "text/csv")},
        data={"account_name": "   "},
    )

    assert response.status_code == 422
