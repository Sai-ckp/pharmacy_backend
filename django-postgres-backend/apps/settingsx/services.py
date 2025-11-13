from __future__ import annotations

from django.db import transaction
from typing import Optional

from .models import SettingKV, DocCounter


def get_setting(key: str, default: str | None = None) -> str | None:
    row = SettingKV.objects.filter(pk=key).values_list("value", flat=True).first()
    if row is None:
        return default
    return row


@transaction.atomic
def set_setting(key: str, value: str) -> None:
    SettingKV.objects.update_or_create(key=key, defaults={"value": value})


@transaction.atomic
def next_doc_number(document_type: str, *, prefix: str = "", padding: int | None = None) -> str:
    counter = DocCounter.objects.select_for_update().get(document_type=document_type)
    num = counter.next_number
    eff_prefix = prefix if prefix != "" else counter.prefix
    eff_padding = padding if padding is not None else counter.padding_int
    code = f"{eff_prefix}{num:0{eff_padding}d}"
    counter.next_number = num + 1
    counter.save(update_fields=["next_number", "updated_at"])
    return code

