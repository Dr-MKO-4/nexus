"""Agent Email : segmentation, séquences comportementales et automatisation des envois (Mautic)."""

from backend.agents.email.graph import build_email_graph
from backend.agents.email.state import EmailState

__all__ = ["build_email_graph", "EmailState"]
