import io
import json
import os
import zipfile
from pathlib import Path
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand,CommandError

class Command(BaseCommand):
    help='Create an encrypted application backup. Pause web and worker writes first.'
    def add_arguments(self,parser):
        parser.add_argument('output'); parser.add_argument('--writes-paused',action='store_true')
    def handle(self,*args,**options):
        if not options['writes_paused']: raise CommandError('Pause all web/worker writes and pass --writes-paused.')
        if os.getenv('S3_BUCKET'): raise CommandError('For S3 deployments use a database dump plus a versioned private bucket snapshot; see OPERATIONS.md.')
        key=os.getenv('BACKUP_KEY')
        if not key: raise CommandError('Set BACKUP_KEY to a Fernet key stored separately from the backup.')
        target=Path(options['output'])
        if target.exists(): raise CommandError('Refusing to overwrite an existing backup.')
        fixture=io.StringIO()
        call_command('dumpdata',exclude=['contenttypes','auth.permission','sessions','brokerage.ratelimit'],
                     natural_foreign=True,natural_primary=True,stdout=fixture)
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('database.json',fixture.getvalue())
            for file in settings.MEDIA_ROOT.rglob('*'):
                if file.is_file(): z.write(file,'storage/'+file.relative_to(settings.MEDIA_ROOT).as_posix())
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(Fernet(key.encode()).encrypt(data.getvalue()))
        self.stdout.write('Encrypted backup created. Retain SECRET_KEY separately to recover MFA secrets.')
