from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from brokerage.models import SiteSettings, Vehicle
from brokerage.services import publication_errors
class Command(BaseCommand):
    help='Check business configuration and published records before public launch.'
    def handle(self,*args,**options):
        s=SiteSettings.current(); failures=[]
        if s.business_name=='Vehicle Brokerage': failures.append('Set the actual business name.')
        if not s.currency: failures.append('Set the default business currency.')
        if not (s.phone or s.email): failures.append('Set a real public phone number or email.')
        if not s.privacy or not s.terms: failures.append('Publish approved privacy and brokerage terms.')
        if not s.about: failures.append('Set actual business information.')
        if settings.DEBUG: failures.append('Turn DEBUG off for production.')
        if not settings.MFA_REQUIRED: failures.append('Enable staff MFA.')
        if not settings.PUBLIC_ORIGIN.startswith('https://'): failures.append('Set a verified HTTPS public origin.')
        if not settings.EMAIL_HOST or not settings.DEFAULT_FROM_EMAIL or not s.notification_email: failures.append('Configure the notification recipient and mail server.')
        for v in Vehicle.objects.public():
            for error in publication_errors(v): failures.append(f'{v.stock_reference}: {error}')
        if failures: raise CommandError('\n'.join(failures))
        self.stdout.write(self.style.SUCCESS('Configuration and publication checks passed. Confirm backup, restore and browser acceptance evidence separately.'))
