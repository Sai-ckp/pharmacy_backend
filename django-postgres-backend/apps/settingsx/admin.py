from django.contrib import admin
from .models import Settings, BusinessProfile, DocCounter, BackupArchive

admin.site.register(Settings)
admin.site.register(BusinessProfile)
admin.site.register(DocCounter)
admin.site.register(BackupArchive)

