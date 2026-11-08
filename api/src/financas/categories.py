from enum import StrEnum


class Category(StrEnum):
    ALIMENTACAO = "alimentacao"
    MERCADO = "mercado"
    TRANSPORTE = "transporte"
    MORADIA = "moradia"
    CONTAS = "contas"
    SAUDE = "saude"
    EDUCACAO = "educacao"
    LAZER = "lazer"
    ASSINATURAS = "assinaturas"
    COMPRAS = "compras"
    TRANSFERENCIAS = "transferencias"
    TAXAS = "taxas"
    FATURA = "fatura"
    INVESTIMENTOS = "investimentos"
    RECEITAS = "receitas"
    OUTROS = "outros"


CATEGORY_LABELS: dict[Category, str] = {
    Category.ALIMENTACAO: "Alimentação",
    Category.MERCADO: "Mercado",
    Category.TRANSPORTE: "Transporte",
    Category.MORADIA: "Moradia",
    Category.CONTAS: "Contas da casa",
    Category.SAUDE: "Saúde",
    Category.EDUCACAO: "Educação",
    Category.LAZER: "Lazer",
    Category.ASSINATURAS: "Assinaturas",
    Category.COMPRAS: "Compras",
    Category.TRANSFERENCIAS: "Transferências",
    Category.TAXAS: "Taxas e juros",
    Category.FATURA: "Pagamento de fatura",
    Category.INVESTIMENTOS: "Investimentos",
    Category.RECEITAS: "Receitas",
    Category.OUTROS: "Outros",
}

# Money that only moves between the user's own pockets (paying the card bill,
# saving into an investment) is neither spending nor income on the dashboard.
NOT_CASH_FLOW: frozenset[Category] = frozenset({Category.FATURA, Category.INVESTIMENTOS})


class Source(StrEnum):
    """Which layer of the pipeline (or the user) decided a transaction's category."""

    USER_RULE = "user_rule"
    KEYWORD = "keyword"
    AI = "ai"
    MANUAL = "manual"
    REVIEW = "review"
