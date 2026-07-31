"""SQLAlchemy models — imported here so Alembic / create_all discover them."""

from app.models.corpus_document import CorpusDocument  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.event import Event  # noqa: F401
from app.models.matter import Matter  # noqa: F401
