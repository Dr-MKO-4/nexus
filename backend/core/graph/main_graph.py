"""Assemblage du graphe principal NEXUS AI : orchestrateur + 3 subgraphs de
clusters, avec PostgresSaver comme checkpointer.

`build_orchestrator_graph()` (Prompt 4.2) retourne un `StateGraph` non
compilé, précisément pour que ce module puisse y ajouter les 3 subgraphs de
cluster comme nœuds avant l'unique appel à `.compile()`  voir la docstring
de backend/agents/orchestrator/graph.py pour le détail de ce pattern de
composition.
"""

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command, StateSnapshot

from backend.agents.orchestrator.graph import (
    ACQUISITION_CLUSTER_NODE,
    ENGAGEMENT_CLUSTER_NODE,
    MEASURE_CLUSTER_NODE,
    RECURSION_LIMIT,
    build_orchestrator_graph,
)
from backend.config.settings import settings
from backend.core.graph.acquisition_cluster import build_acquisition_cluster_graph
from backend.core.graph.engagement_cluster import build_engagement_cluster_graph
from backend.core.graph.measure_cluster import build_measure_cluster_graph
from backend.core.state.marketing_state import MarketingState
from backend.core.state.state_manager import create_initial_state

logger = structlog.get_logger(__name__)


class MainGraph:
    """Point d'entrée unique pour exécuter/reprendre/inspecter un scan NEXUS AI.

    S'instancie via `await MainGraph.create()` (pas `__init__` directement) :
    le checkpointer PostgresSaver a besoin d'un `setup()` async et reste
    ouvert pour toute la durée de vie de l'objet (fermé via `aclose()`) 
    typiquement ouvert une fois dans le lifespan FastAPI, fermé à l'arrêt.
    """

    def __init__(self, compiled_graph: Any, checkpointer_ctx: AsyncIterator[AsyncPostgresSaver]) -> None:
        self._graph = compiled_graph
        self._checkpointer_ctx = checkpointer_ctx

    @classmethod
    async def create(cls) -> "MainGraph":
        # psycopg (v3), pas asyncpg : driver imposé par langgraph-checkpoint-postgres,
        # distinct de celui utilisé par SQLAlchemy (backend/db/session.py).
        # DATABASE_URL (schéma "postgresql://") est directement compatible,
        # contrairement à asyncpg qui exige la réécriture "+asyncpg".
        checkpointer_ctx = AsyncPostgresSaver.from_conn_string(str(settings.DATABASE_URL))
        checkpointer = await checkpointer_ctx.__aenter__()
        await checkpointer.setup()

        builder = build_orchestrator_graph()
        builder.add_node(ACQUISITION_CLUSTER_NODE, build_acquisition_cluster_graph())
        builder.add_node(ENGAGEMENT_CLUSTER_NODE, build_engagement_cluster_graph())
        builder.add_node(MEASURE_CLUSTER_NODE, build_measure_cluster_graph())

        # PAS de interrupt_before=INTERRUPT_BEFORE ici : hitl_checkpoint_node
        # appelle déjà interrupt() lui-même (mécanisme dynamique, voir
        # nodes.py). Combiner les deux casse la reprise - vérifié
        # empiriquement (RuntimeError "Called get_config outside of a
        # runnable context" au second ainvoke). INTERRUPT_BEFORE reste
        # exporté comme documentation de "quel nœud est un point HITL", pas
        # comme configuration active de compile().
        compiled = builder.compile(checkpointer=checkpointer)
        logger.info("main_graph.compiled")
        return cls(compiled, checkpointer_ctx)

    async def aclose(self) -> None:
        await self._checkpointer_ctx.__aexit__(None, None, None)

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}

    async def run(
        self, objective: str, client_id: str, budget: float, **create_initial_state_kwargs: Any
    ) -> AsyncGenerator[dict, None]:
        """Démarre un nouveau scan et stream les mises à jour d'état au fil de
        l'exécution  chaque élément yield est déjà diffusé côté WebSocket
        par les nœuds eux-mêmes (best-effort, voir
        orchestrator.nodes._notify_websocket), pas re-diffusé ici pour éviter
        un double envoi.

        Le thread_id LangGraph (identifiant de checkpoint) est confondu avec
        MarketingState.session_id par simplicité : c'est le seul champ de
        l'état visible dans chaque chunk streamé permettant à l'appelant de
        retrouver l'identifiant à passer à resume()/get_history() ensuite,
        sans inventer un canal de retour séparé. Distinct du session_id de
        backend.core.memory.session_manager (Prompt 2.2, mémoire de travail
        Redis TTL 24h)  même nom, portée différente, aucun couplage réel."""
        thread_id = create_initial_state_kwargs.pop("session_id", None) or str(uuid.uuid4())
        initial_state: MarketingState = create_initial_state(
            objective, client_id, budget, session_id=thread_id, **create_initial_state_kwargs
        )
        logger.info("main_graph.run_started", thread_id=thread_id, client_id=client_id)

        async for update in self._graph.astream(initial_state, config=self._config(thread_id), stream_mode="values"):
            yield update

    async def resume(self, thread_id: str, hitl_response: dict) -> AsyncGenerator[dict, None]:
        """Reprend un scan suspendu sur hitl_checkpoint, avec la réponse
        humaine `{"action": "resume"|"stop"|"modify", ...}`  réinjectée via
        Command(resume=...), lue par orchestrator.nodes.hitl_checkpoint_node
        à la reprise de l'`interrupt()`."""
        logger.info("main_graph.resume", thread_id=thread_id, action=hitl_response.get("action"))
        async for update in self._graph.astream(
            Command(resume=hitl_response), config=self._config(thread_id), stream_mode="values"
        ):
            yield update

    async def get_history(self, thread_id: str) -> list[StateSnapshot]:
        """Historique des checkpoints du thread (time-travel), le plus
        récent en premier  comportement natif de aget_state_history."""
        config = {"configurable": {"thread_id": thread_id}}
        return [snapshot async for snapshot in self._graph.aget_state_history(config)]


__all__ = ["MainGraph"]
