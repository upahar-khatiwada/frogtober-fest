"""Alias package: lets `uv run python -m api.<module>` work from api/.

api/ is a flat app (modules import each other as `schemas`, `nepal`, `db`, ...), so
there is no real `api` package. This one points its search path at api/ itself, so
`api.agents.scout` is api/agents/scout.py. It is only a module-path alias for CLIs;
application code keeps importing the flat names.
"""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent)]
