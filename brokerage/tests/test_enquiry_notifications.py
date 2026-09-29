from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.core import mail
from django.core.management import call_command
from brokerage.models import Vehicle, Seller, Enquiry, Notification, SiteSettings
from brokerage.services import notify_enquiry


class EnquiryNotificationTests(TestCase):
    def setUp(self):
        self.creator = get_user_model().objects.create_user('creator', email='creator@example.test', is_staff=True)
        self.other = get_user_model().objects.create_user('other', email='other@example.test', is_staff=True)
        seller = Seller.objects.create(name='Seller', phone='000')
        self.vehicle = Vehicle.objects.create(created_by=self.creator, assigned_to=self.other, seller=seller, stock_reference='TEST', make='Test', model='Car', year=2020, mileage=100, price=1000, currency='KES', status='available')
        SiteSettings.objects.create(pk=1, notification_email='admin@example.test')

    def test_public_submission_routes_once_to_creator(self):
        url = f'/vehicles/{self.vehicle.public_id}/'
        self.client.get(url)
        key = self.client.session['enquiry_tokens'][-1]
        data = dict(submission_key=key, name='Customer', email='buyer@example.test', preferred_contact='email', kind='enquiry', message='Interested', privacy_consent='on')
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.client.post(url, data)
        self.assertEqual(Notification.objects.count(), 1)
        alert = Notification.objects.get()
        self.assertEqual(alert.recipient, self.creator.email)
        self.assertEqual(alert.state, 'pending')

    def enquiry(self):
        return Enquiry.objects.create(vehicle=self.vehicle, name='Customer', message='Interested')

    def test_missing_email_keeps_inapp_notification(self):
        self.creator.email = ''
        self.creator.save()
        alert = notify_enquiry(self.enquiry())
        self.assertEqual(alert.state, 'inapp')
        self.assertEqual(alert.recipient, '')

    def test_inactive_creator_uses_admin_fallback(self):
        self.creator.is_active = False
        self.creator.save()
        self.assertEqual(notify_enquiry(self.enquiry()).recipient, 'admin@example.test')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', EMAIL_HOST='test', DEFAULT_FROM_EMAIL='swiftlot@example.test')
    def test_worker_delivers_to_creator(self):
        alert = notify_enquiry(self.enquiry())
        call_command('process_jobs')
        alert.refresh_from_db()
        self.assertEqual(alert.state, 'sent')
        self.assertEqual(mail.outbox[0].to, ['creator@example.test'])
