from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.utils import timezone
from brokerage.models import StaffSecurity
from brokerage.services import audit
class Command(BaseCommand):
    help='Server-owner recovery: reset MFA and invalidate sessions for one staff account.'
    def add_arguments(self,parser):
        parser.add_argument('username'); parser.add_argument('--confirm',action='store_true')
    def handle(self,*args,**options):
        if not options['confirm']: raise CommandError('Verify staff identity and add --confirm to reset MFA.')
        try: user=get_user_model().objects.get(username=options['username'],is_staff=True)
        except get_user_model().DoesNotExist: raise CommandError('Staff account not found.')
        StaffSecurity.objects.filter(user=user).delete()
        for session in Session.objects.filter(expire_date__gt=timezone.now()):
            if session.get_decoded().get('_auth_user_id')==str(user.pk): session.delete()
        audit(None,'mfa_reset_by_server_owner',user)
        self.stdout.write('MFA reset. All sessions for this account have been invalidated.')
