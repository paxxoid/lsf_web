import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def quarm_db_status(request):
    state_path = (
        Path(os.environ.get("QUARM_SYNC_DIR", "/app/quarm_sync_data"))
        / "state.json"
    )

    status = None

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))

        filename = state["name"]
        version = filename.removeprefix("quarm_")

        for extension in (".tar.gz", ".sql.gz"):
            if version.endswith(extension):
                version = version.removesuffix(extension)
                break

        status = {
            "updated_at": datetime.fromisoformat(state["imported_at"]),
            "version": version,
        }

    except FileNotFoundError:
        pass  # No successful import recorded yet.
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("Unable to read Quarm update status", exc_info=True)

    return {"quarm_db_status": status}