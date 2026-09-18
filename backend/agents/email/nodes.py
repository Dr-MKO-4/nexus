"""Implémentation des nœuds de l'Agent Email.

Génération avec Qwen3.5 72B (task_type="content_generation") via
`NexusLLMClient.complete_structured` (instructor/Pydantic), cohérent avec le
choix déjà fait pour les Agents SEO/SEA/Content/Social.
"""

from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

from backend.agents.email.prompts import get_email_prompt
from backend.agents.email.segmentation import segment_by_engagement, segment_by_lead_score, segment_by_purchase_history
from backend.agents.email.sequence_manager import calculate_next_send_time, check_already_received, get_sequence_for_segment
from backend.agents.email.state import EmailState
from backend.llm.gateway.llm_client import NexusLLMClient
from backend.tools.email.mautic_client import Contact, MauticClient

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

# Heure d'envoi par défaut (locale) tant qu'aucun historique d'ouverture par
# heure n'est exploité pour l'affiner (contrairement à
# agents.social.scheduler.get_optimal_slots, qui a un historique
# d'engagement social exploitable dès aujourd'hui)  repli documenté.
_DEFAULT_SEND_HOUR = 9


class EmailDraft(BaseModel):
    model_config = _STRICT_CONFIG

    body: str
    cta_text: str


class SubjectLineVariant(BaseModel):
    model_config = _STRICT_CONFIG

    text: str
    approach: str
    predicted_open_rate: float = Field(ge=0, le=1)


class SubjectLineVariants(BaseModel):
    model_config = _STRICT_CONFIG

    variants: list[SubjectLineVariant]


async def load_email_context_node(state: EmailState) -> dict:
    """Charge les contacts, l'historique des séquences envoyées et les taux
    d'ouverture/clic depuis PostgreSQL."""
    client_id = state["client_id"]
    contacts: list[Contact] = []
    sequence_history: list[dict] = []
    open_click_rates: dict = {}

    try:
        from backend.db.models.performance import PerformanceMetric
        from backend.db.repositories.audience_repository import ContactRepository, EmailSequenceRepository
        from backend.db.repositories.performance_repository import PerformanceMetricRepository
        from backend.db.session import get_session
        from datetime import datetime, timedelta, timezone

        async with get_session() as session:
            db_contacts = await ContactRepository(session).get_by_client(UUID(client_id))
            db_sequences = await EmailSequenceRepository(session).get_by_client(UUID(client_id))
            metrics = await PerformanceMetricRepository(session).get_by_channel_and_period(
                UUID(client_id), "email", datetime.now(timezone.utc) - timedelta(days=30), datetime.now(timezone.utc)
            )

        contacts = [
            Contact(
                id=str(c.id),
                email=c.email,
                first_name=c.first_name,
                last_name=c.last_name,
                segment_tags=c.segment_tags or [],
                behavior_data=c.behavior_data or {},
                lead_score=c.lead_score,
                last_interaction_at=c.last_interaction_at.isoformat() if c.last_interaction_at else None,
                opted_out=c.opted_out,
            )
            for c in db_contacts
        ]
        sequence_history = [
            {
                "contact_id": str(s.contact_id),
                "sequence_name": s.sequence_name,
                "current_step": s.current_step,
                "status": s.status.value,
            }
            for s in db_sequences
        ]
        for metric_name in ("open_rate", "click_rate"):
            values = [m.metric_value for m in metrics if m.metric_name == metric_name]
            if values:
                open_click_rates[metric_name] = sum(values) / len(values)
    except Exception as exc:
        logger.warning("email_nodes.load_context_failed", client_id=client_id, error=str(exc))

    logger.info(
        "email_nodes.context_loaded",
        client_id=client_id,
        contact_count=len(contacts),
        sequence_history_count=len(sequence_history),
    )
    return {"contacts": contacts, "sequence_history": sequence_history, "open_click_rates": open_click_rates}


async def segment_audience_node(state: EmailState) -> dict:
    """Segmente les contacts selon les comportements (engagement, historique
    d'achat, lead score)  segmentation.py."""
    contacts = [c for c in (state.get("contacts") or []) if not c.opted_out]

    combined: dict[str, list[Contact]] = {}
    combined.update(segment_by_engagement(contacts))
    combined.update(segment_by_purchase_history(contacts))
    combined.update(segment_by_lead_score(contacts))

    segments = {name: [c.model_dump() for c in members] for name, members in combined.items() if members}
    logger.info("email_nodes.audience_segmented", client_id=state["client_id"], segment_count=len(segments))
    return {"segments": segments}


async def select_sequence_node(state: EmailState) -> dict:
    """Sélectionne la séquence appropriée par segment (sequence_manager.py),
    en excluant les contacts l'ayant déjà reçue."""
    client_id = state["client_id"]
    segments = state.get("segments") or {}
    selected_sequences: list[dict] = []

    for segment_name, contact_dicts in segments.items():
        sequence_config = get_sequence_for_segment(segment_name)
        eligible_contact_ids: list[str] = []
        for contact in contact_dicts:
            already_received = await check_already_received(contact["id"], sequence_config.name)
            if not already_received:
                eligible_contact_ids.append(contact["id"])

        if eligible_contact_ids:
            selected_sequences.append(
                {
                    "segment": segment_name,
                    "sequence_name": sequence_config.name,
                    "steps_days": sequence_config.steps_days,
                    "contact_ids": eligible_contact_ids,
                }
            )

    logger.info("email_nodes.sequences_selected", client_id=client_id, sequence_count=len(selected_sequences))
    return {"selected_sequences": selected_sequences}


def _draft_prompt(sequence_name: str, segment: str, step: int, produit: str, contact_count: int) -> str:
    # Jeton de fusion Mautic (substitué par Mautic à l'envoi réel, voir
    # mautic_client.py) : un seul brouillon est généré par (segment, étape) et
    # réutilisé pour tous les contacts du segment  générer un brouillon par
    # contact multiplierait les appels LLM sans bénéfice proportionné, la
    # personnalisation nominative passe par ce jeton plutôt que par un appel
    # LLM dédié à chaque contact.
    prenom_token = "{contactfield=firstname}"

    if sequence_name == "welcome":
        return get_email_prompt("email-welcome-sequence", prénom=prenom_token, étape=f"J{step}", produit=produit)
    if sequence_name == "reactivation":
        return get_email_prompt(
            "email-reactivation",
            prénom=prenom_token,
            dernière_interaction="plusieurs semaines (contact inactif)",
            offre=produit,
        )
    return get_email_prompt(
        "email-body-generation",
        segment=segment,
        étape=f"J{step}",
        produit=produit,
        prénom=prenom_token,
        historique_interactions=f"Segment {segment!r}, {contact_count} contact(s) concerné(s).",
    )


async def generate_email_content_node(state: EmailState) -> dict:
    """Génère les corps d'emails avec Qwen3.5 72B  un brouillon par
    (segment, étape de séquence), personnalisation nominative via jeton de
    fusion Mautic (voir _draft_prompt)."""
    client_id = state["client_id"]
    contents = state.get("contents") or []
    produit = contents[0].title if contents and contents[0].title else "notre offre"

    llm_client = NexusLLMClient()
    email_drafts: list[dict] = []

    for sequence in state.get("selected_sequences") or []:
        segment, sequence_name = sequence["segment"], sequence["sequence_name"]
        contact_ids = sequence["contact_ids"]
        for step in sequence["steps_days"]:
            prompt = _draft_prompt(sequence_name, segment, step, produit, len(contact_ids))
            try:
                draft = await llm_client.complete_structured(
                    prompt=prompt,
                    response_model=EmailDraft,
                    task_type="content_generation",
                    client_id=client_id,
                    agent_name="email",
                )
                body, cta_text = draft.body, draft.cta_text
            except Exception as exc:
                logger.warning(
                    "email_nodes.generation_failed", client_id=client_id, sequence_name=sequence_name, step=step, error=str(exc)
                )
                body, cta_text = "", ""

            email_drafts.append(
                {
                    "segment": segment,
                    "sequence_name": sequence_name,
                    "step": step,
                    "contact_ids": contact_ids,
                    "body": body,
                    "cta_text": cta_text,
                }
            )

    logger.info("email_nodes.content_generated", client_id=client_id, draft_count=len(email_drafts))
    return {"email_drafts": email_drafts}


async def optimize_subject_lines_node(state: EmailState) -> dict:
    """Génère et score 3 variantes d'objet par brouillon d'email."""
    client_id = state["client_id"]
    email_drafts = state.get("email_drafts") or []
    llm_client = NexusLLMClient()
    subject_line_variants: list[dict] = []

    for index, draft in enumerate(email_drafts):
        variants: list[dict] = []
        selected_subject = ""
        try:
            prompt = get_email_prompt("email-subject-line-generation", email_body=draft.get("body", ""), segment=draft.get("segment", ""))
            result = await llm_client.complete_structured(
                prompt=prompt,
                response_model=SubjectLineVariants,
                task_type="content_generation",
                client_id=client_id,
                agent_name="email",
            )
            variants = [v.model_dump() for v in result.variants]
            if variants:
                selected_subject = max(variants, key=lambda v: v["predicted_open_rate"])["text"]
        except Exception as exc:
            logger.warning("email_nodes.subject_optimization_failed", client_id=client_id, draft_index=index, error=str(exc))

        subject_line_variants.append({"draft_index": index, "variants": variants, "selected_subject": selected_subject})

    logger.info("email_nodes.subject_lines_optimized", client_id=client_id, count=len(subject_line_variants))
    return {"subject_line_variants": subject_line_variants}


async def schedule_send_node(state: EmailState) -> dict:
    """Planifie l'envoi au meilleur moment (sequence_manager.calculate_next_send_time)."""
    client_id = state["client_id"]
    email_drafts = state.get("email_drafts") or []
    subject_by_index = {v["draft_index"]: v.get("selected_subject", "") for v in (state.get("subject_line_variants") or [])}

    send_schedule: list[dict] = []
    for index, draft in enumerate(email_drafts):
        scheduled_at = calculate_next_send_time(draft["step"], _DEFAULT_SEND_HOUR)
        subject = subject_by_index.get(index, "")
        for contact_id in draft["contact_ids"]:
            send_schedule.append(
                {
                    "contact_id": contact_id,
                    "sequence_name": draft["sequence_name"],
                    "step": draft["step"],
                    "subject": subject,
                    "body": draft["body"],
                    "scheduled_at": scheduled_at.isoformat(),
                }
            )

    logger.info("email_nodes.send_scheduled", client_id=client_id, scheduled_count=len(send_schedule))
    return {"send_schedule": send_schedule}


async def trigger_mautic_node(state: EmailState) -> dict:
    """Déclenche la séquence via Mautic API : une campagne par séquence,
    tous ses contacts y sont inscrits en un batch."""
    client_id = state["client_id"]
    send_schedule = state.get("send_schedule") or []

    by_sequence: dict[str, list[str]] = {}
    for item in send_schedule:
        by_sequence.setdefault(item["sequence_name"], []).append(item["contact_id"])

    trigger_results: list[dict] = []
    email_sequences_triggered: list[str] = []

    if by_sequence:
        try:
            mautic = MauticClient()
        except RuntimeError as exc:
            logger.warning("email_nodes.mautic_unconfigured", client_id=client_id, error=str(exc))
            return {"trigger_results": [], "email_sequences_triggered": []}

        try:
            for sequence_name, contact_ids in by_sequence.items():
                unique_contact_ids = list(dict.fromkeys(contact_ids))
                try:
                    campaign_id = await mautic.create_email_campaign(
                        {"name": f"nexus-{sequence_name}-{client_id}", "isPublished": True}
                    )
                    result = await mautic.trigger_campaign(campaign_id, unique_contact_ids)
                    trigger_results.append(
                        {
                            "sequence_name": sequence_name,
                            "campaign_id": campaign_id,
                            "status": result.status,
                            "contacts_triggered": result.contacts_triggered,
                        }
                    )
                    if result.status in ("success", "partial"):
                        email_sequences_triggered.append(sequence_name)
                except Exception as exc:
                    logger.warning("email_nodes.trigger_failed", client_id=client_id, sequence_name=sequence_name, error=str(exc))
                    trigger_results.append({"sequence_name": sequence_name, "status": "failed", "error": str(exc)})
        finally:
            await mautic.aclose()

    logger.info("email_nodes.mautic_triggered", client_id=client_id, triggered_sequences=email_sequences_triggered)
    return {"trigger_results": trigger_results, "email_sequences_triggered": email_sequences_triggered}


async def track_results_node(state: EmailState) -> dict:
    """Collecte les métriques post-envoi via Mautic API."""
    client_id = state["client_id"]
    trigger_results = [r for r in (state.get("trigger_results") or []) if r.get("campaign_id")]
    tracked_metrics: list[dict] = []

    if trigger_results:
        try:
            mautic = MauticClient()
        except RuntimeError as exc:
            logger.warning("email_nodes.mautic_unconfigured", client_id=client_id, error=str(exc))
            return {"tracked_metrics": []}

        try:
            for result in trigger_results:
                try:
                    stats = await mautic.get_campaign_stats(result["campaign_id"])
                    tracked_metrics.append(stats.model_dump())
                except Exception as exc:
                    logger.warning("email_nodes.stats_fetch_failed", client_id=client_id, campaign_id=result["campaign_id"], error=str(exc))
        finally:
            await mautic.aclose()

    logger.info("email_nodes.results_tracked", client_id=client_id, tracked_count=len(tracked_metrics))
    return {"tracked_metrics": tracked_metrics}


async def email_reporter_node(state: EmailState) -> dict:
    """Compile et retourne les résultats à l'orchestrateur/cluster appelant."""
    report = {
        "sequences_triggered": state.get("email_sequences_triggered") or [],
        "total_emails_scheduled": len(state.get("send_schedule") or []),
        "tracked_metrics": state.get("tracked_metrics") or [],
    }
    logger.info("email_nodes.completed", client_id=state["client_id"], sequences_triggered=report["sequences_triggered"])
    return {"email_report": report}
