"""Tầng LLM — điểm vào DUY NHẤT cho mọi thứ liên quan nhà cung cấp mô hình.

Không tầng nào khác (agents/, erp_query/, rag/) được import trực tiếp
providers.py hay catalog.py; chúng đi qua đây.
"""
from .budget import BudgetLedger, Verdict
from .catalog import CATALOG, CHAINS, ROLES, ModelSpec, chain_for, spec_for
from .router import (ChainExhausted, InvokeResult, RouteDecision,
                     RoutedChatModel, Router, SkippedLink, build_router,
                     make_llms)
from .store import InMemoryUsageStore, PostgresUsageStore, Usage

__all__ = [
    "BudgetLedger", "Verdict", "CATALOG", "CHAINS", "ROLES", "ModelSpec",
    "chain_for", "spec_for", "ChainExhausted", "InvokeResult", "RouteDecision",
    "RoutedChatModel", "Router", "SkippedLink", "build_router", "make_llms",
    "InMemoryUsageStore", "PostgresUsageStore", "Usage",
]
