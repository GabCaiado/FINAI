import pytest

from app.ai.rules import RULE_CONFIDENCE, RULES, RuleHit, apply_rules
from app.categories import CATEGORIES

# (cleaned description, expected category, expected merchant). At least one sample per rule:
# test_every_rule_is_reachable fails if a rule is shadowed by an earlier one.
SAMPLES: list[tuple[str, str, str]] = [
    # prefix conflicts
    ("UBER *EATS PEDIDO", "Alimentação", "Uber Eats"),
    ("99FOOD RESTAURANTE X", "Alimentação", "99Food"),
    ("AMAZON PRIME BR", "Assinaturas", "Amazon Prime"),
    ("RAIA DROGASIL MANAUS", "Saúde", "Drogasil"),
    # food and delivery
    ("IFOOD *RESTAURANTE X", "Alimentação", "iFood"),
    ("RAPPI BRASIL", "Alimentação", "Rappi"),
    ("AIQFOME PEDIDO", "Alimentação", "Aiqfome"),
    ("MCDONALDS MANAUS SHOPPING", "Alimentação", "McDonald's"),
    ("BURGER KING 0123", "Alimentação", "Burger King"),
    ("SUBWAY ADRIANOPOLIS", "Alimentação", "Subway"),
    ("BOBS PONTA NEGRA", "Alimentação", "Bob's"),
    ("HABIBS", "Alimentação", "Habib's"),
    ("STARBUCKS MANAUARA", "Alimentação", "Starbucks"),
    # groceries
    ("ATACADAO MANAUS", "Mercado", "Atacadão"),
    ("ASSAI ATACADISTA", "Mercado", "Assaí"),
    ("CARREFOUR HIPER", "Mercado", "Carrefour"),
    ("NOVA ERA SUPERMERCADOS", "Mercado", "Nova Era"),
    ("DB SUPERMERCADOS", "Mercado", "DB Supermercados"),
    ("PAO DE ACUCAR 123", "Mercado", "Pão de Açúcar"),
    # transport
    ("UBER *TRIP", "Transporte", "Uber"),
    ("99 TAXI", "Transporte", "99"),
    ("99POP", "Transporte", "99"),
    ("INDRIVE", "Transporte", "inDrive"),
    ("POSTO SHELL AV TORQUATO", "Transporte", "Shell"),
    ("IPIRANGA AUTO CENTER", "Transporte", "Ipiranga"),
    ("POSTO PETROBRAS", "Transporte", "Petrobras"),
    ("SEM PARAR", "Transporte", "Pedágio"),
    ("ESTAPAR ESTACIONAMENTO", "Transporte", "Estacionamento"),
    ("LATAM AIRLINES", "Transporte", "Companhia aérea"),
    # health
    ("DROGA RAIA", "Saúde", "Droga Raia"),
    ("PAGUE MENOS 1234", "Saúde", "Pague Menos"),
    ("ULTRAFARMA", "Saúde", "Ultrafarma"),
    ("UNIMED MANAUS", "Saúde", "Unimed"),
    ("HAPVIDA SAUDE", "Saúde", "Hapvida"),
    ("PLANO DE SAUDE MENSAL", "Saúde", "Plano de saúde"),
    ("SMART FIT MENSALIDADE", "Saúde", "Academia"),
    # subscriptions
    ("NETFLIX.COM", "Assinaturas", "Netflix"),
    ("SPOTIFY AB", "Assinaturas", "Spotify"),
    ("DISNEY PLUS", "Assinaturas", "Disney+"),
    ("HBO MAX", "Assinaturas", "Max"),
    ("YOUTUBEPREMIUM", "Assinaturas", "YouTube Premium"),
    ("APPLE.COM/BILL", "Assinaturas", "Apple"),
    ("GOOGLE ONE", "Assinaturas", "Google One"),
    ("DEEZER BRASIL", "Assinaturas", "Deezer"),
    ("GLOBOPLAY", "Assinaturas", "Globoplay"),
    ("CRUNCHYROLL", "Assinaturas", "Crunchyroll"),
    ("OPENAI *CHATGPT SUBSCR", "Assinaturas", "ChatGPT"),
    ("MICROSOFT*365", "Assinaturas", "Microsoft"),
    # leisure
    ("STEAMGAMES.COM", "Lazer", "Games"),
    ("MICROSOFT*XBOX", "Lazer", "Games"),
    ("CINEMARK MANAUARA", "Lazer", "Cinema"),
    ("SYMPLA INGRESSOS", "Lazer", "Ingressos"),
    # shopping
    ("MERCADOLIVRE*VENDEDOR", "Compras", "Mercado Livre"),
    ("SHOPEE", "Compras", "Shopee"),
    ("AMAZON MARKETPLACE", "Compras", "Amazon"),
    ("MAGAZINE LUIZA", "Compras", "Magalu"),
    ("AMERICANAS COM", "Compras", "Americanas"),
    ("SHEIN", "Compras", "Shein"),
    ("ALIEXPRESS", "Compras", "AliExpress"),
    ("LOJAS RENNER", "Compras", "Renner"),
    ("RIACHUELO", "Compras", "Riachuelo"),
    ("CASAS BAHIA", "Compras", "Casas Bahia"),
    ("KABUM", "Compras", "KaBuM"),
    # housing
    ("AMAZONAS ENERGIA", "Moradia", "Energia"),
    ("AGUAS DE MANAUS", "Moradia", "Água"),
    ("ALUGUEL APTO", "Moradia", "Aluguel"),
    ("CONDOMINIO RESIDENCIAL", "Moradia", "Condomínio"),
    ("IPTU PARCELA", "Moradia", "IPTU"),
    # education
    ("UNINORTE MENSALIDADE", "Educação", "Uninorte"),
    ("UFAM TAXA", "Educação", "Universidade pública"),
    ("UDEMY", "Educação", "Cursos online"),
    ("LIVRARIA SARAIVA", "Educação", "Livraria"),
    # telecom
    ("CLARO S A", "Taxas e Serviços", "Claro"),
    ("VIVO FIBRA", "Taxas e Serviços", "Vivo"),
    ("TIM S A", "Taxas e Serviços", "TIM"),
    ("OI FIBRA", "Taxas e Serviços", "Oi"),
    # generic words
    ("PADARIA PAO QUENTE", "Alimentação", "Padaria"),
    ("RESTAURANTE SABOR DA TERRA", "Alimentação", "Restaurante"),
    ("SUPERMERCADO BOM PRECO", "Mercado", "Supermercado"),
    ("FARMACIA POPULAR", "Saúde", "Farmácia"),
    ("CLINICA ODONTOLOGICA SORRISO", "Saúde", "Clínica ou hospital"),
    ("AUTO POSTO AMAZONAS", "Transporte", "Posto de combustível"),
    ("ESCOLA MUNICIPAL", "Educação", "Instituição de ensino"),
    # income
    ("SALARIO EMPRESA X", "Renda", "Salário"),
    ("BOLSA ESTAGIO", "Renda", "Bolsa ou estágio"),
    ("RENDIMENTOS POUPANCA", "Renda", "Rendimentos"),
    # transfers
    ("PIX ENVIADO JOAO", "Transferências", "Transferência"),
    ("TED RECEBIDA", "Transferências", "Transferência"),
    # fees and cash
    ("TARIFA PACOTE SERVICOS", "Taxas e Serviços", "Tarifa bancária"),
    ("IOF COMPRA INTERNACIONAL", "Taxas e Serviços", "IOF"),
    ("ANUIDADE DIFERENCIADA", "Taxas e Serviços", "Anuidade"),
    ("JUROS ROTATIVO", "Taxas e Serviços", "Juros e encargos"),
    ("SEGURO CARTAO", "Taxas e Serviços", "Seguro"),
    ("SAQUE 24H", "Outros", "Saque"),
]


def test_has_enough_rules_and_samples():
    assert len(RULES) >= 60
    assert len(SAMPLES) >= 40


@pytest.mark.parametrize(("text", "category", "merchant"), SAMPLES)
def test_samples(text: str, category: str, merchant: str):
    hit = apply_rules(text)
    assert hit == RuleHit(category, merchant, RULE_CONFIDENCE)


def test_no_rule_returns_category_outside_the_fixed_list():
    assert {r.category for r in RULES} <= set(CATEGORIES)


def test_merchant_names_are_unique():
    merchants = [r.merchant for r in RULES]
    assert len(merchants) == len(set(merchants))


def test_every_rule_is_reachable():
    """Each rule must be the one that fires for at least one sample (no shadowed rules)."""
    covered = {merchant for _, _, merchant in SAMPLES}
    missing = {r.merchant for r in RULES} - covered
    assert not missing, f"rules without a sample: {sorted(missing)}"


@pytest.mark.parametrize(
    "text",
    ["PAGAMENTO", "LOJA", "COMPRA LOJA", "MARIA DA SILVA", "", "XPTO 123 COMERCIO"],
)
def test_unknown_text_has_no_hit(text: str):
    assert apply_rules(text) is None


def test_brand_rule_wins_over_generic_transfer():
    hit = apply_rules("PIX PADARIA PAO QUENTE")
    assert hit is not None and hit.category == "Alimentação"


def test_word_boundaries_avoid_false_positives():
    assert apply_rules("UBERABA COMERCIO") is None
    assert apply_rules("AMAZONAS COMERCIO") is None
