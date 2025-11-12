from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Dispatch pending notifications"

    def handle(self, *args, **options):
        try:
            from apps.notifications.services import dispatch_pending
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Notifications module not available: {e}"))
            return
        count = dispatch_pending()
        self.stdout.write(self.style.SUCCESS(f"Dispatched: {count}"))

