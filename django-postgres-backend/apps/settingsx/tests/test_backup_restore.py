import os
from pathlib import Path
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.settingsx.models import BackupArchive, SettingKV
from apps.settingsx.services_backup import restore_backup


class BackupRestoreTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="admin", is_superuser=True)

    def test_disabled(self):
        arc = BackupArchive.objects.create(file_url="/media/backups/dummy.json", size_bytes=0, status="SUCCESS")
        out = restore_backup(archive_id=arc.id, actor=self.user)
        assert out["code"] == "RESTORE_DISABLED"

    def test_enabled_and_missing_file(self):
        SettingKV.objects.update_or_create(key="ALLOW_RESTORE", defaults={"value": "true"})
        arc = BackupArchive.objects.create(file_url="/media/backups/missing.json", size_bytes=0, status="SUCCESS")
        out = restore_backup(archive_id=arc.id, actor=self.user)
        assert out["code"] == "NOT_FOUND"

    def test_enabled_and_success(self):
        SettingKV.objects.update_or_create(key="ALLOW_RESTORE", defaults={"value": "true"})
        p = Path("/media/backups"); p.mkdir(parents=True, exist_ok=True)
        f = p / "empty.json"
        f.write_text("[]")
        arc = BackupArchive.objects.create(file_url=str(f), size_bytes=2, status="SUCCESS")
        out = restore_backup(archive_id=arc.id, actor=self.user)
        assert out["ok"] is True

