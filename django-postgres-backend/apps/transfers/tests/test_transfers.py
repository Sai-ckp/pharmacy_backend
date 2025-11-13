from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.transfers.models import TransferVoucher, TransferLine
from apps.transfers.services import post_transfer, receive_transfer, cancel_transfer
from apps.inventory.models import InventoryMovement
from apps.locations.models import Location
from apps.catalog.models import Product, BatchLot


class Testtransfers(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="admin")

        self.loc1 = Location.objects.create(name="Main")
        self.loc2 = Location.objects.create(name="Branch")

        self.product = Product.objects.create(
            name="Test Drug",
            reorder_level=10,
        )

        self.batch = BatchLot.objects.create(
            product=self.product,
            batch_no="T001",
            expiry=timezone.now().date(),
        )

        InventoryMovement.objects.create(
            location=self.loc1,
            batch_lot=self.batch,
            qty_change_base=100,
        )

        self.voucher = TransferVoucher.objects.create(
            from_location=self.loc1,
            to_location=self.loc2,
            created_by=self.user
        )

        TransferLine.objects.create(
            voucher=self.voucher,
            batch_lot=self.batch,
            qty_base=20
        )

    def test_post_transfer_success(self):
        out = post_transfer(actor=self.user, voucher_id=self.voucher.id)
        self.assertEqual(out["status"], "IN_TRANSIT")

    def test_receive_transfer_success(self):
        post_transfer(actor=self.user, voucher_id=self.voucher.id)
        out = receive_transfer(actor=self.user, voucher_id=self.voucher.id)
        self.assertEqual(out["status"], "RECEIVED")

    def test_receive_idempotent(self):
        post_transfer(actor=self.user, voucher_id=self.voucher.id)
        receive_transfer(actor=self.user, voucher_id=self.voucher.id)
        out = receive_transfer(actor=self.user, voucher_id=self.voucher.id)
        self.assertEqual(out["status"], "RECEIVED")

    def test_cancel_transfer_in_transit(self):
        post_transfer(actor=self.user, voucher_id=self.voucher.id)
        out = cancel_transfer(actor=self.user, voucher_id=self.voucher.id)
        self.assertEqual(out["status"], "CANCELLED")
