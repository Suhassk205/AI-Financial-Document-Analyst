"""ORM model registry.

Importing this package registers all models on `Base.metadata` so Alembic
autogenerate and relationship resolution see them. Add new models here per phase.
"""

from app.models.company import Company
from app.models.enums import ReportStatus, ReportType
from app.models.report import Report
from app.models.report_page import ReportPage

__all__ = [
    "Company",
    "Report",
    "ReportPage",
    "ReportStatus",
    "ReportType",
]
