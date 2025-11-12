from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ProductCategory, MedicineForm, Uom
from apps.settingsx.models import PaymentMethod, PaymentTerm
from apps.inventory.models import RackLocation


class MastersCountsView(APIView):
    def get(self, request):
        data = {
            "categories": ProductCategory.objects.count(),
            "forms": MedicineForm.objects.count(),
            "uoms": Uom.objects.count(),
            "payment_methods": PaymentMethod.objects.count(),
            "payment_terms": PaymentTerm.objects.count(),
            "rack_locations": RackLocation.objects.count(),
        }
        return Response(data)

