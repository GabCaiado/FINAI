"""Merchant catalogs for the synthetic data.

Written from public knowledge of Brazilian merchants. It is deliberately NOT derived from
app/ai/rules.py and must never import it: the golden set would otherwise be biased towards the
rules it is meant to evaluate (ARCHITECTURE section 16). Every person name is invented.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

FICTIONAL_NAMES: tuple[str, ...] = (
    "MARIANA VELLAMAR",
    "TIAGO ORLINDOR",
    "BEATRIZ QUINTAVALE",
    "RAFAEL SOUZAMAR",
    "LETICIA ARVELINDA",
    "GUSTAVO PELIMONTES",
    "CAMILA ZIMBRADO",
    "BRUNO FALCOVIA",
    "ANA CLARA MIRANDEL",
    "FELIPE OSTREVAL",
    "JULIANA JACARENDA",
    "DIEGO NUVELINO",
    "PATRICIA PEROLARI",
    "LUCAS BRANDOVAL",
    "FERNANDA TORRESMAR",
    "RODRIGO ALVAREDO",
    "AMANDA CORVELINO",
    "VINICIUS DOURAVAL",
    "ISABELA MONTEFIORI",
    "THIAGO LARANJEL",
    "CAROLINA SANTAVELA",
    "MATHEUS RIBAMAR",
    "NATALIA VENTURIM",
    "ARMANDO VELLAMAR",
)

CLIENT_NAMES: tuple[str, ...] = (
    "ESTUDIO LUMINARA",
    "AGENCIA PONTO VIVO",
    "STUDIO VERDEBRISA",
    "OFICINA PIXELMAR",
    "CASA DAS IDEIAS LTDA",
    "BRANDOVAL COMUNICACAO",
)

_PREFIXES = ("", "", "COMPRA CARTAO ", "COMPRA DEBITO ")
_SUFFIX_PROBABILITY = 0.3


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    description: str
    category: str
    lo_cents: int
    hi_cents: int
    sign: int  # -1 expense, +1 income


def _parse(table: str) -> tuple[CatalogEntry, ...]:
    """Lines of `DESCRIPTION|Category|lo-hi[|+]`; lo/hi are magnitudes in cents."""
    entries = []
    for line in table.strip().splitlines():
        parts = line.split("|")
        lo, hi = (int(x) for x in parts[2].split("-"))
        sign = 1 if len(parts) > 3 and parts[3] == "+" else -1
        entries.append(CatalogEntry(parts[0], parts[1], lo, hi, sign))
    return tuple(entries)


def decorate(description: str, rng: random.Random) -> str:
    """Make a clean merchant look like a bank line (prefix, short store number)."""
    text = rng.choice(_PREFIXES) + description
    if rng.random() < _SUFFIX_PROBABILITY:
        text += f" {rng.randint(0, 9999):04d}"
    return text


COMMON = _parse("""
IFOOD *RESTAURANTE|Alimentação|1800-6500
RAPPI BRASIL|Alimentação|2000-7000
MCDONALDS|Alimentação|2500-6000
BURGER KING|Alimentação|2500-6500
SUBWAY|Alimentação|2200-4500
OUTBACK STEAKHOUSE|Alimentação|9000-25000
PADARIA PAO QUENTE|Alimentação|600-3500
RESTAURANTE SABOR CASEIRO|Alimentação|2500-6000
STARBUCKS|Alimentação|1800-3800
SPOLETO|Alimentação|3000-5500
GIRAFFAS|Alimentação|2500-5500
CANTINA UNIVERSITARIA|Alimentação|800-2500
PIZZARIA DOM LUIGI|Alimentação|4500-9000
SORVETERIA GELATTO|Alimentação|1200-3000
CHURRASCARIA FOGO LENTO|Alimentação|6000-12000
CARREFOUR HIPERMERCADO|Mercado|3000-25000
PAO DE ACUCAR|Mercado|3000-22000
ASSAI ATACADISTA|Mercado|5000-30000
EXTRA SUPERMERCADOS|Mercado|3000-20000
ATACADAO|Mercado|5000-30000
SUPERMERCADO BOA ESTRELA|Mercado|2000-15000
HORTIFRUTI VERDE VIVO|Mercado|1500-6000
DIA SUPERMERCADO|Mercado|2000-12000
BIG BOMPRECO|Mercado|3000-18000
MERCADINHO SAO JOSE|Mercado|800-5000
ACOUGUE BOI NOBRE|Mercado|2500-9000
EMPORIO DA ESQUINA|Mercado|1500-7000
UBER *TRIP|Transporte|700-4500
99 POP|Transporte|600-3500
POSTO IPIRANGA|Transporte|8000-22000
POSTO SHELL|Transporte|8000-22000
RECARGA BILHETE UNICO|Transporte|2000-10000
ESTACIONAMENTO CENTRAL|Transporte|1000-4500
SEM PARAR PEDAGIO|Transporte|1500-6000
METRO RECARGA|Transporte|1500-8000
CABIFY|Transporte|1200-4000
ALUGUEL APARTAMENTO|Moradia|80000-250000
CONDOMINIO RESIDENCIAL|Moradia|35000-80000
ENEL DISTRIBUICAO|Moradia|8000-30000
SABESP|Moradia|4000-15000
COMGAS|Moradia|3000-12000
VIVO FIBRA|Moradia|9000-14000
IPTU PARCELA|Moradia|10000-40000
DROGASIL|Saúde|1500-12000
DROGARIA PACHECO|Saúde|1500-12000
DROGARIA RAIA|Saúde|1500-12000
PAGUE MENOS|Saúde|1200-9000
UNIMED PLANO SAUDE|Saúde|25000-70000
LABORATORIO FLEURY|Saúde|8000-30000
CLINICA ODONTO SORRISO|Saúde|15000-60000
SMART FIT ACADEMIA|Saúde|9900-12000
XEROX COPIAS CAMPUS|Educação|200-2000
LIVRARIA CULTURA|Educação|3000-14000
UDEMY|Educação|2700-9000
ALURA CURSOS|Educação|7000-12000
COURSERA|Educação|9000-25000
MENSALIDADE FACULDADE|Educação|60000-180000
PAPELARIA CENTRAL|Educação|500-4000
CURSO DE INGLES WIZARD|Educação|20000-40000
CINEMARK|Lazer|2800-9000
INGRESSO.COM|Lazer|4000-30000
STEAM GAMES|Lazer|2000-20000
PLAYSTATION STORE|Lazer|3000-30000
SYMPLA INGRESSOS|Lazer|3000-25000
BAR DO ZE|Lazer|2500-12000
BOLICHE ARENA|Lazer|3500-9000
PARQUE AQUATICO|Lazer|8000-20000
NETFLIX|Assinaturas|2790-5590
SPOTIFY|Assinaturas|1190-3490
DISNEY PLUS|Assinaturas|2790-4690
AMAZON PRIME|Assinaturas|1490-1990
HBO MAX|Assinaturas|2490-5590
YOUTUBE PREMIUM|Assinaturas|2490-4390
DEEZER|Assinaturas|1790-2690
GLOBOPLAY|Assinaturas|2290-4990
APPLE.COM/BILL|Assinaturas|690-3490
PLANO CELULAR TIM|Assinaturas|4900-9900
AMAZON MARKETPLACE|Compras|2500-40000
MERCADO LIVRE|Compras|2000-50000
MAGAZINE LUIZA|Compras|5000-80000
SHEIN|Compras|3000-20000
LOJAS RENNER|Compras|5000-25000
KABUM INFORMATICA|Compras|10000-90000
SHOPEE|Compras|1500-12000
CASAS BAHIA|Compras|8000-100000
AMERICANAS|Compras|2000-20000
TARIFA MANUTENCAO CONTA|Taxas e Serviços|1500-4500
ANUIDADE CARTAO|Taxas e Serviços|1500-6000
IOF OPERACAO|Taxas e Serviços|50-3000
JUROS ROTATIVO CARTAO|Taxas e Serviços|500-20000
SEGURO CELULAR|Taxas e Serviços|1500-5000
TARIFA SAQUE|Taxas e Serviços|500-1500
CREDITO SALARIO|Renda|150000-600000|+
SALARIO EMPRESA ALFA|Renda|150000-600000|+
BOLSA ESTAGIO|Renda|80000-200000|+
PAGAMENTO FREELA PROJETO|Renda|50000-300000|+
13O SALARIO|Renda|150000-400000|+
RENDIMENTO CONTA REMUNERADA|Renda|100-5000|+
""")

# Ambiguous: the text alone does not say what it was; the product rule decides (PIX to a person is
# a transfer, a bare "PAGAMENTO" is Outros). Person names are filled in by `ambiguous_entries`.
_AMBIGUOUS_FIXED = _parse("""
PAGAMENTO|Outros|500-30000
PAGAMENTO EFETUADO|Outros|1000-40000
PAGTO BOLETO|Outros|2000-60000
BOLETO BANCARIO|Outros|2000-60000
DEBITO AUTOMATICO|Outros|1500-30000
COMPRA 1234 LOJA|Compras|1500-25000
COMPRA 8841 LOJA|Compras|1500-25000
COMPRA 0372 ESTABELECIMENTO|Compras|1500-25000
COMPRA 5507 COMERCIO|Compras|1500-25000
SAQUE CAIXA ELETRONICO|Outros|2000-50000
SAQUE 24H|Outros|2000-50000
TRANSFERENCIA ENTRE CONTAS|Transferências|5000-100000
TED ENVIADA|Transferências|10000-200000
TED RECEBIDA|Transferências|10000-200000|+
DOC RECEBIDO|Transferências|10000-200000|+
PIX QRCODE ESTATICO|Outros|800-9000
PIX COBRANCA|Outros|1500-20000
AJUSTE DE SALDO|Outros|100-5000
ESTORNO|Outros|500-15000|+
RESGATE|Outros|5000-100000|+
""")


def ambiguous_entries() -> tuple[CatalogEntry, ...]:
    sent = tuple(
        CatalogEntry(f"PIX ENVIADO {n}", "Transferências", 1000, 40000, -1)
        for n in FICTIONAL_NAMES[:14]
    )
    received = tuple(
        CatalogEntry(f"PIX RECEBIDO {n}", "Transferências", 1000, 60000, 1)
        for n in FICTIONAL_NAMES[14:]
    )
    first_name_only = (CatalogEntry("PIX ENVIADO JOAO", "Transferências", 1000, 20000, -1),)
    return (*_AMBIGUOUS_FIXED, *sent, *received, *first_name_only)


# Hard: truncated, gateway-prefixed or opaque strings a model must reason about.
HARD = _parse("""
EC *PADARIA AURORA 0312|Alimentação|600-3500
PAG*GRILLNOVA|Alimentação|3000-9000
UBER   *EATS|Alimentação|2000-6000
IFD*COMERCIO DE ALIM|Alimentação|1800-6500
TICKET REFEICAO|Alimentação|2500-6000
PAYPAL *STEAMGAMES|Lazer|2000-20000
SYMPLA*INGRESSO|Lazer|3000-25000
MERCADOPAGO*BELEZAPURA|Compras|2500-15000
AMZ*MKTPLC|Compras|2500-40000
KAB*PECAS|Compras|5000-60000
GOOGLE *YOUTUBEPREMIUM|Assinaturas|2490-4390
AMAZON PRIME*VIDEO|Assinaturas|1490-1990
TIM S A|Assinaturas|4900-9900
DROG ARAUJO 22|Saúde|1500-12000
PAGSEGURO*ESTUDIOFIT|Saúde|9000-15000
SUPERM BH 0045|Mercado|3000-20000
POSTO CIDADE JARDIM|Transporte|8000-22000
99*CORRIDA|Transporte|600-3500
ENERGISA|Moradia|8000-30000
SERV CORREIOS|Taxas e Serviços|1500-8000
CARTORIO 2 OFICIO|Taxas e Serviços|3000-20000
DETRAN TAXA|Taxas e Serviços|5000-30000
RECEITA FEDERAL DARF|Taxas e Serviços|5000-40000
UNIVERSIDADE NORTE MENS|Educação|60000-180000
PGTO AUTOR LIVRARIA|Educação|2000-9000
CREDITO PROD CIENT|Renda|50000-200000|+
""")
