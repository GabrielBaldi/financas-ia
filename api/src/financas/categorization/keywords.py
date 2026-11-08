"""Built-in keyword rules for common Brazilian merchants and statement terms.

Rules are checked in order and the first match wins, so specific entries come first:
'uber eats' (food) is listed before 'uber' (transport), 'amazon prime' before 'amazon',
and the generic 'pix'/'transferencia' words come last. Keywords are already normalized
(see financas.text.normalize) and match whole words only.
"""

from dataclasses import dataclass
from enum import StrEnum

from financas.categories import Category
from financas.text import contains_phrase


class Direction(StrEnum):
    IN = "in"
    OUT = "out"


@dataclass(frozen=True, slots=True)
class KeywordRule:
    category: Category
    keywords: tuple[str, ...]
    direction: Direction | None = None  # None: matches money in and out

    def matches(self, normalized_description: str, amount_cents: int) -> bool:
        if self.direction is Direction.IN and amount_cents <= 0:
            return False
        if self.direction is Direction.OUT and amount_cents >= 0:
            return False
        return any(contains_phrase(normalized_description, word) for word in self.keywords)


# fmt: off
KEYWORD_RULES: tuple[KeywordRule, ...] = (
    KeywordRule(
        Category.FATURA,
        ("pagamento de fatura", "pagamento fatura", "pgto fatura", "pagamento recebido"),
    ),
    KeywordRule(
        Category.INVESTIMENTOS,
        ("aplicacao", "resgate", "rdb", "cdb", "lci", "lca", "tesouro direto", "nuinvest",
         "corretora", "poupanca", "renda fixa", "dinheiro guardado", "caixinha"),
    ),
    KeywordRule(
        Category.TAXAS,
        ("iof", "tarifa", "anuidade", "juros", "multa", "encargos", "ipva", "licenciamento",
         "darf", "imposto de renda", "cesta de servicos"),
    ),
    KeywordRule(
        Category.ASSINATURAS,
        ("netflix", "spotify", "amazon prime", "prime video", "primevideo", "disney", "hbo",
         "hbomax", "globoplay", "youtube", "google one", "icloud", "apple com bill", "deezer",
         "paramount", "crunchyroll", "audible", "kindle unlimited", "canva", "chatgpt"),
    ),
    KeywordRule(
        Category.ALIMENTACAO,
        ("ifood", "ifd", "uber eats", "rappi", "ze delivery", "aiqfome", "restaurante",
         "lanchonete", "lanches", "padaria", "panificadora", "confeitaria", "pizzaria", "pizza",
         "hamburgueria", "burger", "burger king", "mcdonalds", "mc donalds", "subway",
         "starbucks", "cafeteria", "cafe", "churrascaria", "acai", "sorveteria", "pastelaria",
         "outback", "habibs", "giraffas", "spoleto", "bobs", "coco bambu", "madero", "sushi",
         "temakeria", "esfiha"),
    ),
    KeywordRule(
        Category.COMPRAS,
        ("amazon", "mercado livre", "mercadolivre", "shopee", "shein", "aliexpress", "temu",
         "magalu", "magazine luiza", "americanas", "casas bahia", "ponto frio", "renner",
         "riachuelo", "cea", "zara", "centauro", "netshoes", "kabum", "leroy merlin", "tok stok",
         "decathlon", "havan", "boticario", "natura", "sephora", "fast shop", "pernambucanas",
         "hering", "petz", "cobasi"),
    ),
    KeywordRule(
        Category.MERCADO,
        ("supermercado", "supermercados", "mercado", "mercadinho", "minimercado",
         "hipermercado", "atacadao", "atacarejo", "assai", "carrefour", "pao de acucar",
         "extra hiper", "sams club", "makro", "hortifruti", "hortifrutti", "sacolao", "acougue",
         "mercearia", "zona sul", "guanabara", "st marche", "bompreco", "condor", "angeloni",
         "savegnago", "verdemar"),
    ),
    KeywordRule(
        Category.TRANSPORTE,
        ("uber", "99app", "99 app", "99pop", "99 pop", "99 taxi", "99taxi", "99 tecnologia",
         "cabify", "indrive", "indriver", "taxi", "metro", "cptm", "sptrans", "bilhete unico",
         "riocard", "onibus", "posto", "auto posto", "combustivel", "combustiveis", "gasolina",
         "shell", "ipiranga", "petrobras", "br mania", "estacionamento", "estapar", "zona azul",
         "sem parar", "conectcar", "veloe", "pedagio", "buser", "clickbus", "blablacar",
         "localiza", "movida", "unidas", "auto pecas", "lava rapido"),
    ),
    KeywordRule(
        Category.SAUDE,
        ("farmacia", "farmacias", "drogaria", "drogarias", "drogasil", "droga raia", "drogaraia",
         "pague menos", "panvel", "drogao", "ultrafarma", "unimed", "amil", "hapvida",
         "notredame", "bradesco saude", "sulamerica", "laboratorio", "clinica", "hospital",
         "consulta", "odonto", "odontologia", "dentista", "fisioterapia", "psicologo",
         "psicologa", "fleury", "smart fit", "smartfit", "bluefit", "academia", "gympass",
         "wellhub", "totalpass", "otica"),
    ),
    KeywordRule(
        Category.CONTAS,
        ("conta de luz", "energia", "enel", "cemig", "light", "copel", "cpfl", "celesc",
         "coelba", "neoenergia", "equatorial", "energisa", "sabesp", "copasa", "cedae", "sanepar",
         "embasa", "compesa", "caesb", "agua", "saneamento", "comgas", "naturgy", "ultragaz",
         "liquigas", "vivo", "claro", "tim", "oi fibra", "oi movel", "internet", "fibra",
         "telefonia", "sky"),
    ),
    KeywordRule(
        Category.MORADIA,
        ("aluguel", "condominio", "iptu", "quinto andar", "quintoandar", "imobiliaria",
         "seguro residencial", "diarista"),
    ),
    KeywordRule(
        Category.EDUCACAO,
        ("alura", "udemy", "coursera", "rocketseat", "descomplica", "duolingo", "escola",
         "colegio", "faculdade", "universidade", "curso", "cursos", "livraria", "saraiva",
         "estante virtual", "mensalidade escolar", "papelaria"),
    ),
    KeywordRule(
        Category.LAZER,
        ("cinema", "cinemark", "kinoplex", "cinepolis", "ingresso", "ingressos", "sympla",
         "eventim", "teatro", "show", "museu", "parque", "steam", "playstation", "psn", "xbox",
         "nintendo", "bar", "boteco", "choperia", "cervejaria", "pub", "hotel", "pousada",
         "airbnb", "booking", "decolar", "latam", "gol linhas", "azul linhas", "turismo"),
    ),
    KeywordRule(Category.OUTROS, ("saque", "banco24horas")),
    KeywordRule(
        Category.RECEITAS,
        ("salario", "folha de pagamento", "proventos", "pro labore", "rendimento", "rendimentos",
         "reembolso", "estorno", "cashback", "pix", "transferencia", "ted", "doc", "deposito",
         "recebido", "recebida"),
        Direction.IN,
    ),
    KeywordRule(
        Category.TRANSFERENCIAS,
        ("pix", "transferencia", "ted", "doc", "enviado", "enviada"),
        Direction.OUT,
    ),
)
# fmt: on


def match_keywords(normalized_description: str, amount_cents: int) -> Category | None:
    for rule in KEYWORD_RULES:
        if rule.matches(normalized_description, amount_cents):
            return rule.category
    return None
