"""`run_recorder` for `LLMClient`: one agent_runs row per stage call (hard rule 9)."""

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from db.models import AgentRunRow
from schemas import AgentRunRecord


def make_run_recorder(session_factory: sessionmaker[Session]) -> Callable[[AgentRunRecord], None]:
    """Each record is committed in its own session, so it survives a failing stage."""

    def record(run: AgentRunRecord) -> None:
        with session_factory() as session:
            session.add(AgentRunRow(**run.model_dump(mode="json")))
            session.commit()

    return record
