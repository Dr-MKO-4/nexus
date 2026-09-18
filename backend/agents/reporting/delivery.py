"""Système de livraison des rapports  Prompt 5.8."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)

_PDF_DIR = "data/reports/pdf"


async def send_by_email(report: dict, recipient_emails: list[str]) -> bool:
    """Envoie le rapport par email via Mautic transactionnel : crée/retrouve
    un contact par destinataire, un template email avec le contenu du
    rapport, puis l'envoie à chacun (réutilise MauticClient tel quel  Mautic
    n'a pas d'API "email transactionnel" distincte de son système
    contact+template+send déjà utilisé par l'Agent Email)."""
    if not recipient_emails:
        return False

    try:
        from backend.tools.email.mautic_client import MauticClient
    except Exception as exc:
        logger.warning("delivery.mautic_import_failed", error=str(exc))
        return False

    try:
        mautic = MauticClient()
    except RuntimeError as exc:
        logger.warning("delivery.mautic_unconfigured", error=str(exc))
        return False

    subject = f"Rapport NEXUS AI  {report.get('period', '')}"
    body_html = _render_report_html(report)

    all_succeeded = True
    try:
        email_id = await mautic.create_email_template(
            {"name": f"nexus-report-{report.get('period', uuid4().hex[:8])}", "subject": subject, "customHtml": body_html}
        )
        for email in recipient_emails:
            try:
                contact_id = await mautic.create_contact({"email": email})
                sent = await mautic.send_email(email_id, contact_id)
                if not sent:
                    all_succeeded = False
            except Exception as exc:
                logger.warning("delivery.send_by_email_recipient_failed", email=email, error=str(exc))
                all_succeeded = False
    except Exception as exc:
        logger.warning("delivery.send_by_email_failed", error=str(exc))
        return False
    finally:
        await mautic.aclose()

    logger.info("delivery.report_emailed", recipient_count=len(recipient_emails), all_succeeded=all_succeeded)
    return all_succeeded


def _render_report_html(report: dict) -> str:
    """Rendu HTML minimal du rapport pour l'email  pas de template engine
    dédié dans ce projet, une interpolation simple suffit pour un contenu
    déjà structuré/validé (Pydantic) en amont."""
    summary = report.get("executive_summary", "")
    recommendations = report.get("recommendations", [])
    rec_items = "".join(f"<li>{r.get('action', '')}  {r.get('expected_impact', '')}</li>" for r in recommendations)
    return f"""<html><body>
<h1>Rapport NEXUS AI  {report.get('period', '')}</h1>
<p>{summary}</p>
<h2>Recommandations</h2>
<ul>{rec_items}</ul>
</body></html>"""


async def expose_via_api(report: dict) -> str:
    """Retourne l'URL REST d'accès au rapport pour le frontend. Suppose que
    `report` porte déjà un `report_id` (renseigné par `store_report`, appelé
    avant dans le graphe  voir agents/reporting/nodes.py: deliver_report_node) ;
    génère un id de repli sinon, plutôt que de lever, pour rester utilisable
    isolément.

    Point d'intégration non câblé (gap documenté, pas une omission
    silencieuse) : aucune route FastAPI `GET /api/reports/{{report_id}}` n'a
    été créée dans ce projet  ce Prompt (5.8) ne liste que les fichiers
    `backend/agents/reporting/*`, pas de route API. L'URL retournée suit la
    convention REST attendue, à servir réellement par une route à ajouter
    (hors périmètre de ce prompt)."""
    report_id = report.get("report_id") or str(uuid4())
    url = f"/api/reports/{report_id}"
    logger.info("delivery.report_exposed_via_api", report_id=report_id, url=url)
    return url


async def store_report(report: dict, client_id: str) -> str:
    """Sauvegarde dans PostgreSQL (table `reports`) + PDF optionnel (best-effort,
    `reportlab` si disponible  voir _generate_pdf)."""
    from backend.db.repositories.report_repository import ReportRepository
    from backend.db.session import get_session

    pdf_path = _generate_pdf(report)

    async with get_session() as session:
        obj = await ReportRepository(session).create(
            client_id=UUID(client_id),
            report_type="weekly",
            period=report.get("period"),
            content=report,
            pdf_path=pdf_path,
            delivered_at=datetime.now(timezone.utc),
        )
    report_id = str(obj.id)
    logger.info("delivery.report_stored", report_id=report_id, client_id=client_id, pdf_generated=pdf_path is not None)
    return report_id


def _generate_pdf(report: dict) -> str | None:
    """PDF optionnel (spec) : `reportlab` n'est pas une dépendance
    obligatoire du projet  retombe silencieusement sur `None` (pas de PDF)
    si absent, plutôt que de faire échouer le stockage du rapport pour un
    agrément visuel secondaire."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        logger.debug("delivery.reportlab_unavailable_skipping_pdf")
        return None

    from pathlib import Path

    output_dir = Path(_PDF_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"report_{report.get('period', uuid4().hex[:8])}_{uuid4().hex[:8]}.pdf"

    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 800, f"Rapport NEXUS AI  {report.get('period', '')}")
    pdf.setFont("Helvetica", 11)
    text = pdf.beginText(50, 770)
    for line in _wrap_text(report.get("executive_summary", ""), 90):
        text.textLine(line)
    pdf.drawText(text)
    pdf.save()

    logger.info("delivery.pdf_generated", path=str(path))
    return str(path)


def _wrap_text(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


async def notify_websocket(report_id: str, client_id: str) -> None:
    """Notification temps réel pour le frontend  `AgentBroadcaster.
    broadcast_report_ready` (backend/api/websocket/agent_broadcaster.py,
    Prompt 7.2), qui remplace le repli "log seul" documenté ici à
    l'écriture de cette fonction (Prompt 5.8, ce module n'existait pas
    encore) : dégrade toujours silencieusement en debug-log en cas d'échec,
    jamais bloquant pour la livraison du rapport."""
    try:
        from backend.api.websocket.agent_broadcaster import get_agent_broadcaster
    except ImportError:
        logger.debug("delivery.websocket_not_available", report_id=report_id, client_id=client_id)
        return

    try:
        await get_agent_broadcaster().broadcast_report_ready(client_id, report_id)
        logger.info("delivery.websocket_notified", report_id=report_id, client_id=client_id)
    except Exception as exc:
        logger.warning("delivery.websocket_notify_failed", report_id=report_id, error=str(exc))


__all__ = ["send_by_email", "expose_via_api", "store_report", "notify_websocket"]
