import pytest
from fastapi.testclient import TestClient

from financas.app import create_app
from financas.config import Settings
from tests.helpers import login, make_settings, register_and_login, upload


def test_register_login_me_and_logout(client: TestClient) -> None:
    headers = register_and_login(client, "Ana@Example.com")

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "ana@example.com"  # e-mails are stored lowercase

    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_wrong_password_and_unknown_email_get_the_same_answer(client: TestClient) -> None:
    register_and_login(client)

    wrong_password = client.post(
        "/auth/token", data={"username": "ana@example.com", "password": "errada123"}
    )
    unknown_email = client.post(
        "/auth/token", data={"username": "ninguem@example.com", "password": "errada123"}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_duplicate_email_and_weak_password_are_rejected(client: TestClient) -> None:
    register_and_login(client)

    duplicate = client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "outra-senha-1"}
    )
    weak = client.post("/auth/register", json={"email": "bia@example.com", "password": "123"})

    assert duplicate.status_code == 409
    assert weak.status_code == 422


def test_protected_routes_need_a_valid_token(client: TestClient) -> None:
    assert client.get("/transactions").status_code == 401
    bogus = {"Authorization": "Bearer token-inventado"}
    assert client.get("/transactions", headers=bogus).status_code == 401


def test_users_only_see_their_own_data(client: TestClient) -> None:
    ana = register_and_login(client, "ana@example.com")
    upload(client, ana, "data;descricao;valor\n01/10/2026;Padaria;-10,00\n")
    bia = register_and_login(client, "bia@example.com")

    anas_transaction = client.get("/transactions", headers=ana).json()["items"][0]["id"]

    assert client.get("/transactions", headers=bia).json() == {"items": [], "total": 0}
    assert client.get("/imports", headers=bia).json() == []
    patch = client.patch(
        f"/transactions/{anas_transaction}", headers=bia, json={"category": "lazer"}
    )
    assert patch.status_code == 404
    assert client.get(f"/transactions/{anas_transaction}/similar", headers=bia).status_code == 404


def test_meta_reports_whether_ai_is_on(client: TestClient, settings: Settings) -> None:
    with_fake_ai = client.get("/meta").json()
    assert with_fake_ai["ai_enabled"] is True
    assert len(with_fake_ai["categories"]) == 16

    with TestClient(create_app(settings)) as no_ai_client:  # no key, no classifier
        assert no_ai_client.get("/meta").json() | {"categories": None} == {
            "ai_enabled": False,
            "ai_provider": None,
            "ai_model": None,
            "categories": None,
        }


@pytest.mark.parametrize(
    ("keys", "provider", "model"),
    [
        ({"anthropic_api_key": "sk-ant-test"}, "anthropic", "claude-haiku-5-5"),
        ({"nvidia_api_key": "nvapi-test"}, "nvidia", "minimaxai/minimax-m3.1-flash"),
        (
            {"nvidia_api_key": "nvapi-test", "nvidia_model": "exemplo/outro-modelo"},
            "nvidia",
            "exemplo/outro-modelo",
        ),
        ({"ai_provider": "nvidia", "anthropic_api_key": "sk-ant-test"}, None, None),
    ],
)
def test_meta_names_the_ai_provider_and_model(
    settings: Settings, keys: dict[str, str], provider: str | None, model: str | None
) -> None:
    # The real classifiers are built, but /meta never calls them.
    app = create_app(make_settings(database_url=settings.database_url, **keys))

    with TestClient(app) as test_client:
        meta = test_client.get("/meta").json()

    assert (meta["ai_enabled"], meta["ai_provider"], meta["ai_model"]) == (
        provider is not None,
        provider,
        model,
    )


def test_logout_revokes_only_that_token(client: TestClient) -> None:
    first = register_and_login(client)
    second = login(client, "ana@example.com")

    client.post("/auth/logout", headers=first)

    assert client.get("/auth/me", headers=second).status_code == 200  # only that token is revoked
