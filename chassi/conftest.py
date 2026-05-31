"""Fixtures dos testes do chassi.

Fica na raiz (ao lado de `app/`) para o pytest inserir este diretório no sys.path
— assim `import app...` funciona. Nenhum teste toca Postgres, LM Studio ou rede:
o pool do banco, o httpx e a LLM são dublados em cada teste.
"""

from __future__ import annotations
