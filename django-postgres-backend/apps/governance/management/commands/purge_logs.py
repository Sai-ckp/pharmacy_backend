from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.governance.models import AuditLog, SystemEvent, RetentionPolicy


class Command(BaseCommand):
    help = "Purge old logs based on RetentionPolicy"

    def handle(self, *args, **options):
        total = 0
        now = timezone.now()
        for pol in RetentionPolicy.objects.filter(hold_from_purge=False):
            if pol.keep_years <= 0:
                continue
            cutoff = now - timedelta(days=365 * pol.keep_years)
            if pol.module.lower() == "audit":
                deleted, _ = AuditLog.objects.filter(created_at__lt=cutoff).delete()
                total += deleted
            elif pol.module.lower() == "events":
                deleted, _ = SystemEvent.objects.filter(created_at__lt=cutoff).delete()
                total += deleted
        self.stdout.write(self.style.SUCCESS(f"Purged rows: {total}"))

