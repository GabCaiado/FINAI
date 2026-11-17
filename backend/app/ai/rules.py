"""Global keyword/merchant rules (layer 2 of the classifier).

Input is a *cleaned* description (uppercase, ASCII, no dates or long digit runs; see
``parsers.clean``). Patterns are therefore written in uppercase without accents.

Rule order (first match wins), from most to least specific:
  1. Brands whose names are prefixed by another brand ("UBER EATS" before "UBER").
  2. Brands, grouped by category.
  3. Generic words ("PADARIA", "FARMACIA", "SUPERMERCADO", "POSTO").
  4. Income words ("SALARIO", "RENDIMENTO").
  5. Internal movements ("FATURA") and generic transfers ("PIX", "TED", "DOC").
  6. Bank fees and cash withdrawals.

Brand rules come before generic ones so "PIX PADARIA X" is food, not a transfer.
Sign rules (income vs expense) are NOT applied here: ``services/classify.py`` enforces them
after every layer, using the sign of the amount.
"""

import re
from typing import NamedTuple

from app.categories import CATEGORIES

RULE_CONFIDENCE = 0.95


class Rule(NamedTuple):
    pattern: re.Pattern[str]
    category: str
    merchant: str


class RuleHit(NamedTuple):
    category: str
    merchant: str
    confidence: float
    is_internal: bool = False


# (regex, category, merchant). Keep merchants unique: tests rely on it.
_SPEC: list[tuple[str, str, str]] = [
    # --- 1. Prefix conflicts -------------------------------------------------------------
    (r"\bUBER\W*EATS\b", "Alimentação", "Uber Eats"),
    (r"\b99\W*FOOD\b", "Alimentação", "99Food"),
    (r"\bAMAZON\W*PRIME\b|\bPRIME\W*VIDEO\b", "Assinaturas", "Amazon Prime"),
    (r"\bDROGASIL\b", "Saúde", "Drogasil"),
    # --- 2. Brands: food and delivery ----------------------------------------------------
    (r"\bIFOOD\b", "Alimentação", "iFood"),
    (r"\bRAPPI\b", "Alimentação", "Rappi"),
    (r"\bAIQFOME\b", "Alimentação", "Aiqfome"),
    (r"\bMC ?DONALD", "Alimentação", "McDonald's"),
    (r"\bBURGER ?KING\b", "Alimentação", "Burger King"),
    (r"\bSUBWAY\b", "Alimentação", "Subway"),
    (r"\bBOB'?S\b", "Alimentação", "Bob's"),
    (r"\bHABIB'?S\b", "Alimentação", "Habib's"),
    (r"\bSTARBUCKS\b", "Alimentação", "Starbucks"),
    # --- 2. Brands: groceries ------------------------------------------------------------
    (r"\bATACADAO\b", "Mercado", "Atacadão"),
    (r"\bASSAI\b", "Mercado", "Assaí"),
    (r"\bCARREFOUR\b", "Mercado", "Carrefour"),
    (r"\bNOVA ERA\b", "Mercado", "Nova Era"),
    (r"\bDB SUPERMERCADOS?\b", "Mercado", "DB Supermercados"),
    (r"\bPAO DE ACUCAR\b", "Mercado", "Pão de Açúcar"),
    # --- 2. Brands: transport ------------------------------------------------------------
    (r"\bUBER\b", "Transporte", "Uber"),
    (r"^99\b|\b99 ?(POP|TAXI|TECNOLOGIA)\b", "Transporte", "99"),
    (r"\bIN ?DRIVE\b", "Transporte", "inDrive"),
    (r"\bSHELL\b", "Transporte", "Shell"),
    (r"\bIPIRANGA\b", "Transporte", "Ipiranga"),
    (r"\bPETROBRAS\b|\bBR MANIA\b", "Transporte", "Petrobras"),
    (r"\bPEDAGIO\b|\bSEM PARAR\b|\bCONECTCAR\b", "Transporte", "Pedágio"),
    (r"\bESTACIONAMENTO\b|\bESTAPAR\b", "Transporte", "Estacionamento"),
    (r"\bLATAM\b|\bGOL LINHAS\b|\bAZUL LINHAS\b", "Transporte", "Companhia aérea"),
    # --- 2. Brands: health ---------------------------------------------------------------
    (r"\bDROGA RAIA\b|\bRAIA\b", "Saúde", "Droga Raia"),
    (r"\bPAGUE MENOS\b", "Saúde", "Pague Menos"),
    (r"\bULTRAFARMA\b", "Saúde", "Ultrafarma"),
    (r"\bUNIMED\b", "Saúde", "Unimed"),
    (r"\bHAPVIDA\b", "Saúde", "Hapvida"),
    (r"\bPLANO DE SAUDE\b|\bAMIL\b|\bBRADESCO SAUDE\b", "Saúde", "Plano de saúde"),
    (r"\bSMART ?FIT\b|\bBLUEFIT\b|\bACADEMIA\b", "Saúde", "Academia"),
    # --- 2. Brands: subscriptions --------------------------------------------------------
    (r"\bNETFLIX\b", "Assinaturas", "Netflix"),
    (r"\bSPOTIFY\b", "Assinaturas", "Spotify"),
    (r"\bDISNEY", "Assinaturas", "Disney+"),
    (r"\bHBO\b", "Assinaturas", "Max"),
    (r"\bYOUTUBE", "Assinaturas", "YouTube Premium"),
    (r"\bAPPLE\.?COM\b|\bICLOUD\b|\bITUNES\b", "Assinaturas", "Apple"),
    (r"\bGOOGLE (ONE|STORAGE)\b", "Assinaturas", "Google One"),
    (r"\bDEEZER\b", "Assinaturas", "Deezer"),
    (r"\bGLOBOPLAY\b", "Assinaturas", "Globoplay"),
    (r"\bCRUNCHYROLL\b", "Assinaturas", "Crunchyroll"),
    (r"\bOPENAI\b|\bCHATGPT\b", "Assinaturas", "ChatGPT"),
    # --- 2. Brands: leisure (before Microsoft: "MICROSOFT XBOX" is a game) ---------------
    (r"\bSTEAM|\bPLAYSTATION\b|\bXBOX\b|\bNINTENDO\b", "Lazer", "Games"),
    (r"\bMICROSOFT\b", "Assinaturas", "Microsoft"),
    (r"\bCINEMARK\b|\bCINEMA\b|\bKINOPLEX\b", "Lazer", "Cinema"),
    (r"\bSYMPLA\b|\bINGRESSO(S| COM)?\b", "Lazer", "Ingressos"),
    # --- 2. Brands: shopping -------------------------------------------------------------
    (r"\bMERCADO ?LIVRE\b", "Compras", "Mercado Livre"),
    (r"\bSHOPEE\b", "Compras", "Shopee"),
    (r"\bAMAZON\b", "Compras", "Amazon"),
    (r"\bMAGAZINE ?LUIZA\b|\bMAGALU\b", "Compras", "Magalu"),
    (r"\bAMERICANAS\b", "Compras", "Americanas"),
    (r"\bSHEIN\b", "Compras", "Shein"),
    (r"\bALIEXPRESS\b", "Compras", "AliExpress"),
    (r"\bRENNER\b", "Compras", "Renner"),
    (r"\bRIACHUELO\b", "Compras", "Riachuelo"),
    (r"\bCASAS BAHIA\b", "Compras", "Casas Bahia"),
    (r"\bKABUM\b", "Compras", "KaBuM"),
    # --- 2. Brands: housing utilities (Manaus) -------------------------------------------
    (r"\bAMAZONAS ENERGIA\b|\bMANAUS ENERGIA\b|\bENERGIA ELETRICA\b", "Moradia", "Energia"),
    (r"\bAGUAS DE MANAUS\b|\bSANEAMENTO\b", "Moradia", "Água"),
    (r"\bALUGUEL\b", "Moradia", "Aluguel"),
    (r"\bCONDOMINIO\b", "Moradia", "Condomínio"),
    (r"\bIPTU\b", "Moradia", "IPTU"),
    # --- 2. Brands: education ------------------------------------------------------------
    (r"\bUNINORTE\b", "Educação", "Uninorte"),
    (r"\bUFAM\b|\bUEA\b", "Educação", "Universidade pública"),
    (r"\bUDEMY\b|\bCOURSERA\b|\bALURA\b|\bDUOLINGO\b", "Educação", "Cursos online"),
    (r"\bLIVRARIA\b|\bSARAIVA\b", "Educação", "Livraria"),
    # --- 2. Brands: telecom --------------------------------------------------------------
    (r"\bCLARO\b", "Taxas e Serviços", "Claro"),
    (r"\bVIVO\b|\bTELEFONICA\b", "Taxas e Serviços", "Vivo"),
    (r"^TIM\b|\bTIM (CELULAR|S A|BRASIL|FIBRA)\b", "Taxas e Serviços", "TIM"),
    (r"^OI$|\bOI (FIBRA|MOVEL|S A)\b", "Taxas e Serviços", "Oi"),
    # --- 3. Generic words ----------------------------------------------------------------
    (r"\bPADARIA\b|\bPANIFICADORA\b", "Alimentação", "Padaria"),
    (
        r"\bRESTAURANTE\b|\bLANCHONETE\b|\bPIZZARIA\b|\bCHURRASCARIA\b|\bSORVETERIA\b"
        r"|\bCAFETERIA\b",
        "Alimentação",
        "Restaurante",
    ),
    (
        r"\bSUPERMERCADOS?\b|\bHIPERMERCADO\b|\bMERCADINHO\b|\bMERCEARIA\b",
        "Mercado",
        "Supermercado",
    ),
    (r"\bFARMACIA\b|\bDROGARIA\b", "Saúde", "Farmácia"),
    (
        r"\bCLINICA\b|\bHOSPITAL\b|\bLABORATORIO\b|\bODONTO\w*|\bDENTISTA\b",
        "Saúde",
        "Clínica ou hospital",
    ),
    (r"\bPOSTO\b|\bCOMBUSTIVEIS?\b", "Transporte", "Posto de combustível"),
    (
        r"\bFACULDADE\b|\bUNIVERSIDADE\b|\bESCOLA\b|\bCOLEGIO\b|\bMATRICULA\b",
        "Educação",
        "Instituição de ensino",
    ),
    # --- 4. Income words -----------------------------------------------------------------
    (r"\bSALARIO\b|\bFOLHA (DE )?(PAGAMENTO|PGTO)\b", "Renda", "Salário"),
    (
        r"\bBOLSA (AUXILIO|ESTAGIO|PESQUISA|ESTUDO)\b|\bAUXILIO ESTUDANTIL\b",
        "Renda",
        "Bolsa ou estágio",
    ),
    (r"\bRENDIMENTOS?\b", "Renda", "Rendimentos"),
    # --- 5. Internal movements and generic transfers --------------------------------------
    # Card-bill payments leave the checking account AND the bill's purchases are imported from
    # the card statement: treating the payment as "Transferências" avoids counting it twice.
    # (Utility bills named "FATURA" match their brand rule above first.)
    (r"\bFATURA\b", "Transferências", "Pagamento de fatura"),
    (r"\bPIX\b|\bTED\b|\bDOC\b|\bTRANSF(ERENCIA)?\b", "Transferências", "Transferência"),
    # --- 6. Fees and cash ----------------------------------------------------------------
    (r"\bTARIFA\b", "Taxas e Serviços", "Tarifa bancária"),
    (r"\bIOF\b", "Taxas e Serviços", "IOF"),
    (r"\bANUIDADE\b", "Taxas e Serviços", "Anuidade"),
    (r"\bJUROS\b|\bENCARGOS\b|\bMULTA\b", "Taxas e Serviços", "Juros e encargos"),
    (r"\bSEGURO\b|\bPORTO SEGURO\b", "Taxas e Serviços", "Seguro"),
    (r"\bSAQUE\b", "Outros", "Saque"),
]

# Merchants whose rows are internal movements (excluded from income/expense totals).
INTERNAL_MERCHANTS = frozenset({"Pagamento de fatura"})

RULES: tuple[Rule, ...] = tuple(Rule(re.compile(p), c, m) for p, c, m in _SPEC)

_invalid = {r.category for r in RULES} - set(CATEGORIES)
if _invalid:  # fail fast at import: a rule must never emit a category outside the list
    raise ValueError(f"Rules use categories outside the fixed list: {sorted(_invalid)}")


def apply_rules(description_clean: str) -> RuleHit | None:
    """Return the first matching rule for a cleaned description, or None."""
    for rule in RULES:
        if rule.pattern.search(description_clean):
            return RuleHit(
                rule.category, rule.merchant, RULE_CONFIDENCE, rule.merchant in INTERNAL_MERCHANTS
            )
    return None
