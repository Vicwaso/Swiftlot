from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from brokerage.models import Enquiry, SiteSettings, Viewing, Task, Offer
from brokerage.services import audit

class Command(BaseCommand):
    help='Dry-run by default. Anonymize old closed enquiries not linked to any sale.'
    def add_arguments(self,parser): parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        cutoff=timezone.now()-timedelta(days=SiteSettings.current().retention_days)
        eligible=Enquiry.objects.filter(stage='closed',updated_at__lt=cutoff,sale__isnull=True).exclude(name='Removed contact')
        self.stdout.write(f'{eligible.count()} eligible closed enquiries. Sales and their buyer records are excluded.')
        if not options['apply']: return
        with transaction.atomic():
            for e in eligible.select_for_update():
                e.name='Removed contact'; e.email=''; e.phone=''; e.message='Contact information removed under the retention policy.'
                e.notes=''; e.closure_reason=''; e.next_action=''; e.save()
                Viewing.objects.filter(enquiry=e).update(outcome='')
                Task.objects.filter(enquiry=e).update(notes='',title='Retained completed enquiry task')
                Offer.objects.filter(enquiry=e).update(notes='')
                audit(None,'contact_anonymized',e)
