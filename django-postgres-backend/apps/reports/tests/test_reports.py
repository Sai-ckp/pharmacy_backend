import os
from django.test import TestCase
from django.utils import timezone

from apps.reports.models import ReportExport
from apps.reports.services import generate_report_file


class Testreports(TestCase):
    def test_sales_register_export(self):
        exp = ReportExport.objects.create(
            report_type="SALES_REGISTER",
            params={},
        )
        path = generate_report_file(exp)
        self.assertTrue(os.path.exists(os.path.join("media/exports", os.path.basename(path))))

    def test_h1_register_export(self):
        exp = ReportExport.objects.create(report_type="H1_REGISTER", params={})
        path = generate_report_file(exp)
        self.assertTrue(os.path.exists(os.path.join("media/exports", os.path.basename(path))))

    def test_ndps_daily_export(self):
        exp = ReportExport.objects.create(report_type="NDPS_DAILY", params={})
        path = generate_report_file(exp)
        self.assertTrue(os.path.exists(os.path.join("media/exports", os.path.basename(path))))
