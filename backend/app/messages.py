"""Central catalogue of user-facing backend texts (PT-BR).

Services and routers never inline user-visible strings: they import them from here, so wording
can be reviewed in one place. Constants are named after the error ``code`` they accompany.
"""

DEFAULT_ACCOUNT_NAME = "Conta principal"

UNAUTHORIZED = "Faça login para continuar."
RATE_LIMITED = "Muitas tentativas. Aguarde um instante e tente novamente."
EMAIL_ALREADY_REGISTERED = "Este e-mail já está cadastrado."
INVALID_CREDENTIALS = "E-mail ou senha incorretos."
NOT_FOUND = "Recurso não encontrado."
ACCOUNT_NAME_TAKEN = "Você já tem uma conta com este nome."
ACCOUNT_NOT_EMPTY = "Esta conta tem lançamentos. Remova-os antes de excluir a conta."
LAST_ACCOUNT = "Você precisa manter ao menos uma conta."
CONSENT_REQUIRED = "É necessário aceitar o aviso de privacidade para criar a conta."
MAPPING_REQUIRED = (
    "Não reconhecemos as colunas do arquivo. Indique quais colunas são data, descrição e valor."
)
INVALID_ROW = "Algumas linhas do arquivo não puderam ser lidas. Confira as linhas indicadas."
TOO_MANY_ROWS = "O arquivo tem linhas demais para uma única importação."
UNSUPPORTED_FILE = "Não conseguimos ler este arquivo. Envie um extrato em OFX ou CSV."
