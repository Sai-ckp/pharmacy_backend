from django.db import transaction
from apps.settingsx.models import DocCounter


@transaction.atomic
def next_doc_number(document_type: str) -> str:
    counter = DocCounter.objects.select_for_update().get(document_type=document_type)
    num = counter.next_number
    code = f"{counter.prefix}-{num:0{counter.padding_int}d}"
    counter.next_number = num + 1
    counter.save(update_fields=["next_number", "updated_at"])
    return code

