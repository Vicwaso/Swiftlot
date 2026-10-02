import secrets
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from brokerage.models import SiteSettings

class Command(BaseCommand):
    help='Create staff roles and a one-use owner setup link for local development.'
    def handle(self,*args,**options):
        roles={
          'Inventory manager': ['view_vehicle','add_vehicle','change_vehicle','publish_vehicle','view_seller','add_seller','change_seller','view_privatedocument','add_privatedocument','view_notification'],
          'Sales agent': ['view_vehicle','view_enquiry','add_enquiry','change_enquiry','view_viewing','add_viewing','change_viewing','view_task','add_task','change_task','view_offer','add_offer','change_offer','view_notification'],
          'Sales manager': ['view_vehicle','change_vehicle','close_sale','view_enquiry','add_enquiry','change_enquiry','view_viewing','add_viewing','change_viewing','view_task','add_task','change_task','view_offer','add_offer','change_offer','view_sale','change_sale','view_notification'],
          'Finance officer': ['view_vehicle','view_sale','view_payment','add_payment','change_payment','view_finance','view_notification','view_auditevent'],
          'Read-only reviewer': ['view_vehicle','view_seller','view_enquiry','view_viewing','view_task','view_offer','view_sale','view_finance','view_auditevent','view_notification'],
        }
        for name,permissions in roles.items():
            group,_=Group.objects.get_or_create(name=name)
            group.permissions.set(Permission.objects.filter(content_type__app_label='brokerage',codename__in=permissions))
        SiteSettings.current()
        self.stdout.write('Staff roles and website settings are ready.')
        if not get_user_model().objects.filter(is_superuser=True).exists():
            file=settings.BASE_DIR/'.bootstrap-token'
            if not file.exists(): file.write_text(secrets.token_urlsafe(32))
            self.stdout.write('One-time owner setup: '+settings.PUBLIC_ORIGIN+'/staff/setup/'+file.read_text().strip()+'/')
