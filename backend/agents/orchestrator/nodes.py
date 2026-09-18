"""Implémentation des nœuds du graphe de l'Orchestrateur (graph.py).

Chaque nœud est une coroutine `async def node(state: MarketingState) -> dict`
qui retourne uniquement les champs modifiés (jamais l'état complet)  c'est
le contrat LangGraph standard, et c'est ce qui permet aux reducers
`Annotated[..., operator.add]` de `MarketingState` de fonctionner.

Dépendances vers des composants pas encore écrits (agents Phase 5, service
PyTorch d'anomaly detection, WebSocket) : importées paresseusement à
l'intérieur des fonctions concernées, avec repli explicite (log + Alert)
plutôt que crash à l'import  même principe que
`backend.tasks.queues.redis_queue` (Prompt 2.2) et
`backend.core.memory.embedding_manager` (Prompt 2.3).
"""

import json
import re
from datetime import datetime, timezone
from typing import Any

import structlog
from langgraph.types import interrupt

from backend.core.state.marketing_state import MarketingState
from backend.core.state.state_models import Alert, PlanItem, Task
from backend.core.state.validators import check_required_fields
from backend.agents.orchestrator.prompts import get_orchestrator_prompt
from backend.llm.gateway.llm_client import NexusLLMClient

logger = structlog.get_logger(__name__)

_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)

# Agents attendus par cluster  utilisé par plan_week_node pour répartir les
# tâches, et par validate_parallel_results_node pour savoir quoi vérifier.
_ACQUISITION_AGENTS = ("seo", "sea")
_ENGAGEMENT_AGENTS = ("content", "social", "email")
_MEASURE_AGENTS = ("analytics", "reporting")

# Écart relatif (KPI actuel vs cible) au-delà duquel une réallocation
# budgétaire est déclenchée (Prompt 4.2 : "Si écart > 20%").
_PERFORMANCE_GAP_THRESHOLD = 0.20


def _parse_llm_json(raw_response: str, *, node: str) -> tuple[dict[str, Any], list[Alert]]:
    """Parse la réponse JSON d'un appel LLM, en tolérant les blocs ```json```
    que certains modèles ajoutent malgré la consigne "ne retourne QUE le
    JSON". Ne lève jamais : un JSON illisible produit un dict vide + une
    Alert, cohérent avec le principe "continue sans bloquer" du Prompt 4.2."""
    candidate = raw_response.strip()
    fence_match = _JSON_FENCE_PATTERN.search(candidate)
    if fence_match:
        candidate = fence_match.group(1)
    else:
        object_match = _JSON_OBJECT_PATTERN.search(candidate)
        if object_match:
            candidate = object_match.group(0)

    try:
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("La réponse JSON n'est pas un objet.")
        return parsed, []
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("orchestrator_nodes.llm_json_parse_failed", node=node, error=str(exc), raw=raw_response[:500])
        alert = Alert(
            level="warning",
            source=node,
            message=f"Réponse LLM illisible en JSON pour {node} : {exc}",
            action_required=True,
        )
        return {}, [alert]


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def parse_objective_node(state: MarketingState) -> dict:
    """Décompose l'objectif business (texte libre) en budget/période/canaux
    prioritaires/KPIs cibles structurés, via le LLM d'orchestration
    (task_type="orchestration" -> Llama 3.3 70B, voir hybrid_router.py)."""
    llm_client = NexusLLMClient()
    prompt = get_orchestrator_prompt(
        "parse-objective",
        objective=state["objective"],
        budget=state.get("budget_total") or "non précisé",
        period="non précisée",
    )

    raw_response = await llm_client.complete(
        prompt=prompt,
        task_type="orchestration",
        client_id=state["client_id"],
        agent_name="orchestrator",
        trace_id=state["trace_id"],
        session_id=state["session_id"],
    )
    parsed, alerts = _parse_llm_json(raw_response, node="parse_objective")

    # budget_total fourni explicitement à create_initial_state() fait foi ;
    # le budget extrait du texte par le LLM ne comble qu'un budget non fourni.
    budget_total = state.get("budget_total") or float(parsed.get("budget") or 0.0)

    period_start = _parse_iso_datetime(parsed.get("period_start")) or state.get("period_start")
    period_end = _parse_iso_datetime(parsed.get("period_end")) or state.get("period_end")

    priority_channels: list[str] = parsed.get("priority_channels") or []
    channel_allocations = (
        {channel: round(budget_total / len(priority_channels), 2) for channel in priority_channels}
        if priority_channels and budget_total
        else state.get("channel_allocations") or {}
    )

    target_kpis = parsed.get("target_kpis") or {}
    # performance_summary n'a pas de champ dédié "target_kpis" dans
    # MarketingState (Prompt 4.1) : on l'y stocke sous cette clé, lue plus
    # tard par check_performance_node - voir docstring de ce nœud.
    performance_summary = {**(state.get("performance_summary") or {}), "target_kpis": target_kpis}

    logger.info("orchestrator_nodes.parse_objective_completed", client_id=state["client_id"], budget_total=budget_total)
    return {
        "budget_total": budget_total,
        "period_start": period_start,
        "period_end": period_end,
        "channel_allocations": channel_allocations,
        "performance_summary": performance_summary,
        "execution_mode": "planning",
        "alerts": alerts,
        "last_updated_at": datetime.now(timezone.utc),
    }


async def plan_week_node(state: MarketingState) -> dict:
    """Consulte l'historique PostgreSQL des campagnes similaires, génère un
    plan hebdomadaire structuré (list[PlanItem]) via le LLM, assigne les
    tâches par agent et calcule les allocations budgétaires initiales."""
    historical_summary = await _summarize_historical_campaigns(state["client_id"])

    llm_client = NexusLLMClient()
    prompt = get_orchestrator_prompt(
        "plan-week",
        objective=state["objective"],
        budget=state.get("budget_total", 0.0),
        channels=", ".join(state.get("channel_allocations", {}).keys()) or "non déterminés",
        historical_campaigns=historical_summary,
    )
    raw_response = await llm_client.complete(
        prompt=prompt,
        task_type="orchestration",
        client_id=state["client_id"],
        agent_name="orchestrator",
        trace_id=state["trace_id"],
        session_id=state["session_id"],
    )
    parsed, alerts = _parse_llm_json(raw_response, node="plan_week")

    weekly_plan: list[PlanItem] = []
    for raw_item in parsed.get("plan", []):
        try:
            weekly_plan.append(PlanItem.model_validate(raw_item))
        except Exception as exc:  # un item de plan invalide ne doit pas invalider tout le plan
            logger.warning("orchestrator_nodes.plan_item_invalid", raw_item=raw_item, error=str(exc))
            alerts.append(
                Alert(level="warning", source="plan_week", message=f"Entrée de plan invalide ignorée : {exc}")
            )

    assigned_tasks: dict[str, list[Task]] = {}
    for item in weekly_plan:
        task = Task(id=f"{item.agent}-{item.task_type}-{len(assigned_tasks.get(item.agent, []))}", agent=item.agent, type=item.task_type)
        assigned_tasks.setdefault(item.agent, []).append(task)

    logger.info("orchestrator_nodes.plan_week_completed", client_id=state["client_id"], plan_items=len(weekly_plan))
    return {
        "weekly_plan": weekly_plan,
        "assigned_tasks": assigned_tasks,
        "alerts": alerts,
        "execution_mode": "execution",
        "last_updated_at": datetime.now(timezone.utc),
    }


async def _summarize_historical_campaigns(client_id: str) -> str:
    """Résumé texte des campagnes passées du client, pour injection dans
    PLAN_WEEK_PROMPT. Renvoie une chaîne neutre si l'accès DB échoue
    (indisponibilité momentanée de PostgreSQL ne doit pas bloquer le
    planning, juste le priver de ce contexte historique)."""
    try:
        from backend.db.repositories.campaign_repository import CampaignRepository
        from backend.db.session import get_session

        async with get_session() as session:
            repo = CampaignRepository(session)
            campaigns = await repo.get_by_client(client_id, limit=5)
        if not campaigns:
            return "Aucune campagne historique trouvée pour ce client."
        return "\n".join(
            f"- {c.name} ({c.status.value}) : objectif={c.objective!r}, "
            f"budget={c.budget_total}, consommé={c.budget_consumed}"
            for c in campaigns
        )
    except Exception as exc:
        logger.warning("orchestrator_nodes.historical_campaigns_unavailable", client_id=client_id, error=str(exc))
        return "Historique indisponible."


async def route_to_cluster_node(state: MarketingState) -> dict:
    """Nœud de transition pur (pas d'effet de bord) avant la décision de
    routage (router.route_after_plan) : existe pour que le graphe ait un
    point d'ancrage nommé distinct de plan_week, conformément à la liste de
    nœuds du Prompt 4.2."""
    return {"active_agent": None, "last_updated_at": datetime.now(timezone.utc)}


async def fanout_acquisition_node(state: MarketingState) -> dict:
    """Transmet le contexte pertinent au subgraph du cluster Acquisition
    (voir backend/core/graph/acquisition_cluster.py, Prompt 4.3), assemblé
    comme nœud "acquisition_cluster" par main_graph.py.

    Note d'architecture : Send() de LangGraph ne peut cibler que des nœuds
    du graphe COURANT - "run_seo_agent"/"run_sea_agent" (Prompt 4.2 :
    "Send() vers Agent SEO et Agent SEA en parallèle") vivent en réalité un
    niveau plus bas, DANS le subgraph acquisition_cluster (Prompt 4.3). Le
    fanout SEO+SEA réel a donc lieu à l'intérieur de ce subgraph
    (acquisition_cluster.init_acquisition_node) ; ce nœud-ci se contente de
    router vers le subgraph lui-même - l'effet décrit par le Prompt 4.2 est
    obtenu par la composition des deux couches, pas par ce nœud seul.
    """
    return {"active_agent": "acquisition_cluster", "last_updated_at": datetime.now(timezone.utc)}


async def fanout_engagement_node(state: MarketingState) -> dict:
    """Voir fanout_acquisition_node : même principe, le fanout Content/Social/
    Email réel a lieu dans engagement_cluster.init_engagement_node."""
    return {"active_agent": "engagement_cluster", "last_updated_at": datetime.now(timezone.utc)}


async def validate_parallel_results_node(state: MarketingState) -> dict:
    """Vérifie que tous les agents planifiés (weekly_plan) ont bien produit
    leur champ de résultat attendu. Un champ manquant ajoute une Alert et
    laisse le graphe continuer (jamais de blocage ici)."""
    planned_agents = {item.agent for item in (state.get("weekly_plan") or [])}
    alerts: list[Alert] = []

    for agent_name in sorted(planned_agents):
        missing = check_required_fields(state, agent_name)
        if missing:
            alerts.append(
                Alert(
                    level="warning",
                    source="validate_parallel_results",
                    message=f"Agent {agent_name!r} : champs manquants après fanout : {missing}",
                    action_required=False,
                )
            )

    logger.info("orchestrator_nodes.validate_parallel_results", planned_agents=sorted(planned_agents), alert_count=len(alerts))
    return {"alerts": alerts, "last_updated_at": datetime.now(timezone.utc)}


async def consolidate_results_node(state: MarketingState) -> dict:
    """Fusionne/compile les résultats de tous les agents pour préparer
    l'étape de mesure de performance. N'a rien à recalculer : les reducers
    Annotated[..., operator.add] de MarketingState ont déjà fait la fusion
    pendant le fanout  ce nœud marque juste la transition et consigne quels
    agents ont contribué."""
    completed = state.get("completed_agents") or []
    logger.info("orchestrator_nodes.consolidate_results", completed_agents=completed)
    return {"active_agent": None, "last_updated_at": datetime.now(timezone.utc)}


async def check_performance_node(state: MarketingState) -> dict:
    """Compare les KPIs actuels (analytics_data, produit par l'Agent
    Analytics dans measure_cluster) aux cibles (performance_summary.target_kpis,
    écrites par parse_objective_node). Écart > 20% -> requires_reallocation.
    Détection d'anomalie PyTorch : service pas encore déployé (Prompt 5.6),
    repli explicite si indisponible."""
    target_kpis: dict[str, float] = (state.get("performance_summary") or {}).get("target_kpis", {})
    current_kpis: dict[str, float] = (state.get("analytics_data") or {}).get("kpis", {})

    llm_client = NexusLLMClient()
    prompt = get_orchestrator_prompt(
        "check-performance",
        target_kpis=json.dumps(target_kpis, ensure_ascii=False),
        current_kpis=json.dumps(current_kpis, ensure_ascii=False),
        period=f"{state.get('period_start')} -> {state.get('period_end')}",
    )
    raw_response = await llm_client.complete(
        prompt=prompt,
        task_type="analytics",
        client_id=state["client_id"],
        agent_name="orchestrator",
        trace_id=state["trace_id"],
        session_id=state["session_id"],
    )
    parsed, alerts = _parse_llm_json(raw_response, node="check_performance")

    requires_reallocation = bool(parsed.get("requires_reallocation", False))
    hitl_required = requires_reallocation and _reallocation_is_significant(target_kpis, current_kpis)

    anomaly_detected, anomaly_alerts = await _detect_anomalies_pytorch(current_kpis)
    alerts.extend(anomaly_alerts)

    performance_summary = {
        **(state.get("performance_summary") or {}),
        "current_kpis": current_kpis,
        "requires_reallocation": requires_reallocation,
        "underperforming_channels": parsed.get("underperforming_channels", []),
        "overperforming_channels": parsed.get("overperforming_channels", []),
        "reasoning": parsed.get("reasoning", ""),
        "anomaly_detected": anomaly_detected,
    }

    logger.info(
        "orchestrator_nodes.check_performance_completed",
        requires_reallocation=requires_reallocation,
        hitl_required=hitl_required,
        anomaly_detected=anomaly_detected,
    )
    return {
        "performance_summary": performance_summary,
        "hitl_required": hitl_required,
        "alerts": alerts,
        "last_updated_at": datetime.now(timezone.utc),
    }


def _reallocation_is_significant(target_kpis: dict[str, float], current_kpis: dict[str, float]) -> bool:
    """Un écart > 20% sur au moins un KPI cible déclenche une réallocation
    automatique ; un écart > 50% sur au moins un KPI est jugé assez important
    pour requérir une validation humaine avant d'agir (hitl_required)."""
    for name, target in target_kpis.items():
        current = current_kpis.get(name)
        if current is None or target == 0:
            continue
        gap = abs(current - target) / abs(target)
        if gap > 0.5:
            return True
    return False


async def _detect_anomalies_pytorch(current_kpis: dict[str, float]) -> tuple[bool, list[Alert]]:
    """Appelle le service PyTorch de détection d'anomalies
    (backend/pytorch_models/anomaly/anomaly_detector.py, Prompt 5.6  pas
    encore écrit). Repli : aucune anomalie signalée, pas d'Alert bloquante,
    juste un log  cohérent avec le principe "continue sans bloquer"."""
    try:
        from backend.pytorch_models.anomaly.anomaly_detector import AnomalyDetector  # type: ignore[import-not-found]
    except ImportError:
        logger.debug("orchestrator_nodes.anomaly_detector_not_available")
        return False, []

    try:
        detector = AnomalyDetector()
        result = detector.detect(list(current_kpis.values()))
        if result.is_anomaly:
            return True, [
                Alert(
                    level="critical",
                    source="check_performance",
                    message=f"Anomalie détectée sur les KPIs (score={result.score:.2f}).",
                    action_required=True,
                )
            ]
        return False, []
    except Exception as exc:
        logger.warning("orchestrator_nodes.anomaly_detection_failed", error=str(exc))
        return False, []


async def reallocate_budget_node(state: MarketingState) -> dict:
    """Réalloue channel_allocations en déplaçant du budget des canaux
    sous-performants vers les canaux surperformants identifiés par
    check_performance_node, proportionnellement (10% du budget des canaux
    sous-performants redistribué)."""
    summary = state.get("performance_summary") or {}
    underperforming: list[str] = summary.get("underperforming_channels", [])
    overperforming: list[str] = summary.get("overperforming_channels", [])
    allocations = dict(state.get("channel_allocations") or {})

    if underperforming and overperforming:
        shift_ratio = 0.10
        total_shifted = 0.0
        for channel in underperforming:
            if channel in allocations:
                shift = allocations[channel] * shift_ratio
                allocations[channel] -= shift
                total_shifted += shift
        if total_shifted:
            share = total_shifted / len(overperforming)
            for channel in overperforming:
                if channel in allocations:
                    allocations[channel] += share

    iterations = state.get("iterations", 0) + 1
    logger.info("orchestrator_nodes.reallocate_budget", allocations=allocations, iterations=iterations)
    return {
        "channel_allocations": allocations,
        "iterations": iterations,
        "execution_mode": "optimization",
        "last_updated_at": datetime.now(timezone.utc),
    }


async def hitl_checkpoint_node(state: MarketingState) -> dict:
    """Point de validation humaine : interrupt() suspend l'exécution du
    graphe et persiste l'état via le checkpointer (PostgresSaver) ; la
    reprise se fait via main_graph.resume(thread_id, hitl_response), qui
    réinjecte la réponse humaine via Command(resume=...)."""
    summary = state.get("performance_summary") or {}
    proposal = {
        "underperforming_channels": summary.get("underperforming_channels", []),
        "overperforming_channels": summary.get("overperforming_channels", []),
        "reasoning": summary.get("reasoning", ""),
    }
    context = {
        "client_id": state["client_id"],
        "campaign_id": state.get("campaign_id"),
        "budget_total": state.get("budget_total"),
        "budget_consumed": state.get("budget_consumed"),
        "channel_allocations": state.get("channel_allocations"),
    }
    payload = {
        "proposal": proposal,
        "context": context,
        "options": ["resume", "stop", "modify"],
    }

    await _notify_websocket(state, event="hitl_checkpoint", payload=payload)

    # interrupt() lève une exception interne capturée par l'exécuteur
    # LangGraph : l'exécution reprend ICI (avec `human_response` peuplé par
    # Command(resume=...)) lors du prochain appel à ainvoke()/astream() sur
    # le même thread_id.
    human_response = interrupt(payload)

    logger.info("orchestrator_nodes.hitl_checkpoint_resumed", response=human_response)
    return {
        "hitl_response": human_response if isinstance(human_response, dict) else {"action": "stop"},
        "hitl_required": False,
        "last_updated_at": datetime.now(timezone.utc),
    }


async def _notify_websocket(state: MarketingState, *, event: str, payload: dict) -> None:
    """Notifie l'interface React via WebSocket  backend/api/websocket/
    agent_broadcaster.py (Prompt 7.2), qui remplace le repli "log seul"
    documenté ici à l'écriture de ce nœud (Prompt 4.2, ce module n'existait
    pas encore). Scope TOUJOURS par `client_id` (jamais un broadcast
    global) : `hitl_checkpoint`/`crisis_detected` sont des données propres à
    UN client  un broadcast global les exposerait à tous les clients
    connectés, ce qu'un `ConnectionManager.broadcast()` générique (l'ancienne
    signature imaginée ici) aurait fait à tort.
    """
    try:
        from backend.api.websocket.agent_broadcaster import get_agent_broadcaster
    except ImportError:
        # "event" est un nom de paramètre réservé par structlog (premier
        # positionnel de logger.debug/info/...) : le passer en kwarg ici
        # provoquerait "got multiple values for argument 'event'" - vérifié
        # empiriquement (crash reproduit). D'où "ws_event" ci-dessous.
        logger.debug("orchestrator_nodes.websocket_not_available", ws_event=event, session_id=state.get("session_id"))
        return

    try:
        broadcaster = get_agent_broadcaster()
        client_id = state["client_id"]
        if event == "hitl_checkpoint":
            await broadcaster.broadcast_hitl_request({**payload, "client_id": client_id, "campaign_id": state.get("campaign_id")})
        else:
            await broadcaster.broadcast_alert(payload, client_id=client_id)
    except Exception as exc:
        logger.warning("orchestrator_nodes.websocket_notify_failed", ws_event=event, error=str(exc))


async def handle_crisis_node(state: MarketingState) -> dict:
    """Suspend les publications programmées, génère une réponse de crise
    (soumise à validation humaine, jamais publiée automatiquement) et
    notifie l'équipe."""
    llm_client = NexusLLMClient()
    summary = state.get("performance_summary") or {}
    crisis_context = json.dumps(
        {
            "underperforming_channels": summary.get("underperforming_channels", []),
            "anomaly_detected": summary.get("anomaly_detected", False),
            "recent_alerts": [a.message for a in (state.get("alerts") or [])[-5:]],
        },
        ensure_ascii=False,
    )
    prompt = get_orchestrator_prompt(
        "crisis-response",
        crisis_context=crisis_context,
        client_name=state["client_id"],
    )
    raw_response = await llm_client.complete(
        prompt=prompt,
        task_type="orchestration",
        client_id=state["client_id"],
        agent_name="orchestrator",
        trace_id=state["trace_id"],
        session_id=state["session_id"],
    )
    parsed, parse_alerts = _parse_llm_json(raw_response, node="handle_crisis")

    suspend_result = await _suspend_scheduled_publications(state)

    alert = Alert(
        level="critical",
        source="handle_crisis",
        message=parsed.get("response_summary", "Crise détectée  réponse en attente de validation humaine."),
        action_required=True,
    )

    await _notify_websocket(state, event="crisis_detected", payload={"summary": parsed, "suspended": suspend_result})

    logger.error("orchestrator_nodes.crisis_handled", client_id=state["client_id"], severity=parsed.get("severity"))
    return {
        "execution_mode": "crisis",
        "hitl_required": True,
        "alerts": [*parse_alerts, alert],
        "last_updated_at": datetime.now(timezone.utc),
    }


async def _suspend_scheduled_publications(state: MarketingState) -> bool:
    """Suspend les publications programmées via l'Agent Social (Prompt 5.4,
    pas encore écrit). Repli : log seul, aucune suspension réelle possible
    sans cet agent  la crise reste néanmoins signalée (hitl_required=True)."""
    try:
        from backend.agents.social.scheduler import suspend_all_scheduled  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("orchestrator_nodes.social_scheduler_not_available_cannot_suspend", client_id=state["client_id"])
        return False

    try:
        await suspend_all_scheduled(client_id=state["client_id"])
        return True
    except Exception as exc:
        logger.error("orchestrator_nodes.suspend_publications_failed", error=str(exc))
        return False


async def generate_report_node(state: MarketingState) -> dict:
    """Compile le rapport de synthèse final à partir de performance_summary
    et des compteurs de résultats produits (voir state_manager.get_state_summary,
    réutilisé comme base du rapport)."""
    from backend.core.state.state_manager import get_state_summary

    summary = get_state_summary(state)
    report = {
        **summary,
        "performance": state.get("performance_summary"),
    }
    logger.info("orchestrator_nodes.generate_report_completed", client_id=state["client_id"])
    return {
        "performance_summary": {**(state.get("performance_summary") or {}), "final_report": report},
        "execution_mode": state.get("execution_mode", "execution"),
        "last_updated_at": datetime.now(timezone.utc),
    }


async def error_handler_node(state: MarketingState) -> dict:
    """Point de recovery : consigne les erreurs déjà présentes dans l'état
    (accumulées via le reducer Annotated de `errors`) sous forme d'une Alert
    de synthèse, sans tenter de les corriger automatiquement (chaque erreur
    a déjà sa propre trace dans `errors`)."""
    errors = state.get("errors") or []
    logger.error("orchestrator_nodes.error_handler_triggered", error_count=len(errors))
    alert = Alert(
        level="critical",
        source="error_handler",
        message=f"{len(errors)} erreur(s) rencontrée(s) pendant l'exécution  voir `errors` pour le détail.",
        action_required=True,
    )
    return {"alerts": [alert], "last_updated_at": datetime.now(timezone.utc)}
