from functools import lru_cache

from langchain_openai import ChatOpenAI

from .settings import settings


@lru_cache
def get_llm() -> ChatOpenAI:
    """Modelo apontando para o LM Studio (API compatível com OpenAI).

    temperature=0 para reduzir alucinação. A saída estruturada (Pydantic) é
    feita pelo create_agent via response_format, que usa tool-calling.
    """
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=0,
    )
