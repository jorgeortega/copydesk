"""Per-node model selection from .env. Model IDs are never hardcoded."""

import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


def model_for(node: str) -> BaseChatModel:
    load_dotenv()
    model_id = os.environ.get(f"COPYDESK_MODEL_{node.upper()}") or os.environ.get("COPYDESK_MODEL")
    if not model_id:
        raise RuntimeError(
            f"No model set for node '{node}'. Set COPYDESK_MODEL_{node.upper()} or COPYDESK_MODEL "
            "in .env (see .env.example)."
        )
    return init_chat_model(model_id)
