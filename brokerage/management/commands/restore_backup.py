import io
import os
import zipfile
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from brokerage.models import Vehicle, SiteSettings

class Command(BaseCommand):
    help='Restore an encrypted backup into an empty migrated database with web and worker stopped.'
    def add_arguments(self,parser): parser.add_argument('input'); parser.add_argument('--confirm-empty-restore',action='store_true')
    def handle(self,*args,**options):
        if not options['confirm_empty_restore']: raise CommandError('Stop web/worker and confirm with --confirm-empty-restore.')
        if os.getenv('S3_BUCKET'): raise CommandError('For S3 deployments restore the database and private bucket versions using OPERATIONS.md.')
        if get_user_model().objects.exists() or Vehicle.objects.exists() or SiteSettings.objects.exists(): raise CommandError('Restore requires an empty, migrated database. Do not run bootstrap first.')
        key=os.getenv('BACKUP_KEY')
        if not key: raise CommandError('Set BACKUP_KEY.')
        try: data=Fernet(key.encode()).decrypt(Path(options['input']).read_bytes())
        except InvalidToken: raise CommandError('Backup authentication failed.')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if name=='database.json': continue
                if not name.startswith('storage/') or '..' in Path(name).parts or Path(name).is_absolute(): raise CommandError('Unsafe backup member.')
            from django.core import serializers
            with transaction.atomic():
                deferred=[]
                for obj in serializers.deserialize('json',z.read('database.json'),handle_forward_references=True):
                    obj.save()
                    if obj.deferred_fields: deferred.append(obj)
                for obj in deferred: obj.save_deferred_fields()
            for name in z.namelist():
                if name.startswith('storage/'):
                    target=settings.MEDIA_ROOT/Path(name).relative_to('storage')
                    target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(z.read(name))
        # Reset database sequences after restoring explicit primary keys.
        from django.apps import apps
        from django.db import connection
        from django.core.management.color import no_style
        with connection.cursor() as cursor:
            for statement in connection.ops.sequence_reset_sql(no_style(),apps.get_models()): cursor.execute(statement)
        self.stdout.write('Restored. Use the original SECRET_KEY; validate sold states and private files before reopening.')
