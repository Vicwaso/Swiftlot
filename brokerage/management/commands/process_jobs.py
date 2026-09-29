import logging
import time
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction, connection, close_old_connections
from django.utils import timezone
from brokerage.models import Notification, Reservation, Offer, RateLimit
from brokerage.services import release_reservation, notify

logger=logging.getLogger(__name__)
class Command(BaseCommand):
    help='Deliver pending notifications and expire reservations. Use --loop for a worker.'
    def add_arguments(self,parser): parser.add_argument('--loop',action='store_true')
    def handle(self,*args,**options):
        while True:
            self.run_batch()
            if not options['loop']: break
            close_old_connections(); time.sleep(20)
    def run_batch(self):
        now=timezone.now()
        for reservation in Reservation.objects.filter(active=True,expires_at__lte=now):
            release_reservation(reservation.pk)
        for reservation in Reservation.objects.filter(active=True,reminded=False,expires_at__lte=now+timedelta(hours=1)):
            with transaction.atomic():
                if Reservation.objects.filter(pk=reservation.pk,active=True,reminded=False).update(reminded=True):
                    notify('Reservation expiring',f'{reservation.vehicle.stock_reference} is reserved until {reservation.expires_at}.')
        Offer.objects.filter(decision='pending',expires_at__lte=now).update(decision='expired')
        RateLimit.objects.filter(expires_at__lt=now-timedelta(days=1)).delete()
        ids=Notification.objects.filter(state__in=['pending','failed'],attempts__lt=5,next_attempt__lte=now).values_list('pk',flat=True)[:50]
        for pk in list(ids):
            with transaction.atomic():
                queryset=Notification.objects.select_for_update(skip_locked=True) if connection.features.has_select_for_update_skip_locked else Notification.objects.select_for_update()
                item=queryset.filter(pk=pk,state__in=['pending','failed'],attempts__lt=5,next_attempt__lte=now).first()
                if not item: continue
                item.attempts+=1
                try:
                    if not settings.EMAIL_HOST or not settings.DEFAULT_FROM_EMAIL: raise RuntimeError('Mail server is not configured.')
                    send_mail(item.subject,item.body,settings.DEFAULT_FROM_EMAIL,[item.recipient],fail_silently=False)
                    item.state='sent'; item.error=''
                except Exception as error:
                    item.state='failed'; item.error='Email delivery failed. Check the mail server configuration and worker logs.'
                    item.next_attempt=now+timedelta(minutes=2**item.attempts)
                    logger.warning('Notification %s failed (%s)',item.pk,type(error).__name__)
                item.save()
