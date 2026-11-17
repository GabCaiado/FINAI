EXPENSE_CATEGORIES = [
    "Alimentação", "Mercado", "Transporte", "Moradia", "Saúde", "Educação",
    "Lazer", "Assinaturas", "Compras", "Taxas e Serviços", "Transferências", "Outros",
]
INCOME_CATEGORIES = ["Renda", "Transferências", "Outros"]
CATEGORIES = [*EXPENSE_CATEGORIES, "Renda"]  # 13 distinct values


def is_allowed(category: str, amount_cents: int) -> bool:
    """Positive amounts: Renda/Transferências/Outros. Negative: anything but Renda."""
    allowed = INCOME_CATEGORIES if amount_cents > 0 else EXPENSE_CATEGORIES
    return category in allowed
