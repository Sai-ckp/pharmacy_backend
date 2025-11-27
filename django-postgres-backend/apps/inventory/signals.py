from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.inventory.models import InventoryMovement, BatchStock

@receiver(post_save, sender=InventoryMovement)
def update_batch_stock(sender, instance, **kwargs):
    stock, _ = BatchStock.objects.get_or_create(
        batch=instance.batch_lot,
        location=instance.location,
    )

    stock.quantity += instance.qty_change_base
    stock.save()
