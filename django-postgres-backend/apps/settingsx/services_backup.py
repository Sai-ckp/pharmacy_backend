from __future__ import annotations

from django.core.management import call_command
from django.db import transaction
from pathlib import Path

from .services import get_setting
from .models import BackupArchive
from apps.governance.services import audit


@transaction.atomic
def restore_backup(*, archive_id: int, actor) -> dict:
    if (get_setting("ALLOW_RESTORE", "false") or "false").lower() != "true":
        return {"ok": False, "code": "RESTORE_DISABLED"}
    if not getattr(actor, "is_superuser", False):
        return {"ok": False, "code": "FORBIDDEN"}

    arc = BackupArchive.objects.select_for_update().get(id=archive_id)
    file_url = arc.file_url
    p = Path(file_url)
    if not str(p).startswith("/media/backups/"):
        return {"ok": False, "code": "INVALID_PATH"}
    if not p.exists():
        return {"ok": False, "code": "NOT_FOUND"}

    call_command("loaddata", str(p))
    audit(actor, table="backup_archives", row_id=arc.id, action="RESTORE", before=None, after={"file": str(p)})
    return {"ok": True}

