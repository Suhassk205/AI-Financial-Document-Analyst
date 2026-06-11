"""ORM model registry.

Importing this package registers all models on `Base.metadata` so Alembic
autogenerate and relationship resolution see them. Add new models here per phase.
"""

from app.models.company import Company
from app.models.document_chunk import DocumentChunk
from app.models.enums import ReportStatus, ReportType
from app.models.financial_metric import FinancialMetric
from app.models.metric_comparison import MetricComparison
from app.models.financial_analytics import FinancialAnalytics
from app.models.risk_factor import RiskFactor
from app.models.risk_evolution import RiskEvolution
from app.models.management_tone import ManagementTone
from app.models.tone_evolution import ToneEvolution
from app.models.report import Report
from app.models.report_page import ReportPage
from app.models.report_section import ReportSection
from app.models.conversation_thread import ConversationThread
from app.models.conversation_message import ConversationMessage

__all__ = [
    "Company",
    "DocumentChunk",
    "FinancialMetric",
    "MetricComparison",
    "FinancialAnalytics",
    "RiskFactor",
    "RiskEvolution",
    "ManagementTone",
    "ToneEvolution",
    "Report",
    "ReportPage",
    "ReportSection",
    "ReportStatus",
    "ReportType",
    "ConversationThread",
    "ConversationMessage",
]

