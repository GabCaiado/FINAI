import os

# Tests never hit the network or a real DB file.
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_finai.db")
