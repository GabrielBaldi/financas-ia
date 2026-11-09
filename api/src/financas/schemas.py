"""Request and response bodies of the HTTP API. Money is always integer cents."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from financas.categories import Category, Source
from financas.config import AIProvider
from financas.models import Origin


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (not a secret)
    expires_at: dt.datetime


class UserOut(ORMModel):
    id: int
    email: str


class CategoryOut(BaseModel):
    slug: Category
    label: str


class MetaOut(BaseModel):
    ai_enabled: bool
    ai_provider: AIProvider | None
    ai_model: str | None
    categories: list[CategoryOut]


class AccountOut(ORMModel):
    id: int
    name: str


class ImportOut(ORMModel):
    id: int
    filename: str
    file_format: str
    account: AccountOut
    created_at: dt.datetime
    total_rows: int
    inserted: int
    duplicates: int
    by_user_rule: int
    by_keyword: int
    by_ai: int
    to_review: int
    ai_input_tokens: int
    ai_output_tokens: int
    ai_cost_usd: float
    reconciled: int  # Telegram entries merged into rows of this statement


class TransactionOut(ORMModel):
    id: int
    account_id: int
    date: dt.date
    description: str
    amount_cents: int
    category: Category | None
    categorized_by: Source
    confidence: float | None
    suggested_category: Category | None
    origin: Origin
    note: str | None  # the user's words from Telegram, on a statement row that absorbed them


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int


class CategoryUpdate(BaseModel):
    category: Category


class SimilarOut(BaseModel):
    pattern: str
    count: int


class RuleIn(BaseModel):
    pattern: str = Field(min_length=3, max_length=120)
    category: Category


class RuleOut(ORMModel):
    id: int
    pattern: str
    category: Category
    created_at: dt.datetime


class RuleCreated(BaseModel):
    rule: RuleOut
    applied: int


class CategoryTotal(BaseModel):
    category: Category | None  # None = "A revisar"
    total_cents: int


class MonthTotal(BaseModel):
    month: str
    expenses_cents: int
    income_cents: int


class DashboardOut(BaseModel):
    month: str
    expenses_cents: int
    income_cents: int
    by_category: list[CategoryTotal]
    monthly: list[MonthTotal]


class TelegramStatusOut(BaseModel):
    linked: bool
    linked_at: dt.datetime | None
    default_account: AccountOut | None  # None: entries go to "Lançamentos manuais"


class PairingCodeOut(BaseModel):
    code: str = Field(examples=["048213"])
    expires_at: dt.datetime


class DefaultAccountIn(BaseModel):
    account_id: int | None
