import io
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from brokerage.models import *
from brokerage import services

TEST_STORAGE=settings.BASE_DIR/'test-results'/'uploads'
TEST_STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}

def image_file(name='test.jpg'):
    data=io.BytesIO(); Image.new('RGB',(40,30),(90,110,100)).save(data,'JPEG')
    return SimpleUploadedFile(name,data.getvalue(),content_type='image/jpeg')

def stock(owner,ref='TEST-001'):
    seller=Seller.objects.create(name='Test seller',phone='0000000000',verified=True,verification_notes='Test verification')
    v=Vehicle.objects.create(stock_reference=ref,seller=seller,assigned_to=owner,make='Test make',model='Test model',year=2022,
        body_type='SUV',mileage=10000,fuel='Petrol',transmission='Automatic',colour='Black',price=Decimal('1000000'),
        currency='KES',location='Test location',condition='Test condition',known_defects='Test disclosure',
        agreement_confirmed=True,agreement_start=timezone.localdate()-timedelta(days=1),agreement_end=timezone.localdate()+timedelta(days=30),fee_type='percent',fee_value=Decimal('2.5'))
    VehiclePhoto.objects.create(vehicle=v,image=image_file(),alt='Test vehicle')
    e=Enquiry.objects.create(vehicle=v,name='Test buyer',email='buyer@example.test',message='Test enquiry',privacy_consent=True)
    return v,e

@override_settings(MFA_REQUIRED=False,MEDIA_ROOT=TEST_STORAGE,STORAGES=TEST_STORAGES)
class SystemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=get_user_model().objects.create_superuser('owner','owner@example.test','test-long-password-567')
        cls.consumer=get_user_model().objects.create_user('consumer',password='test-long-password-567')
        cls.vehicle,cls.buyer=stock(cls.owner)
    def publish(self):
        self.vehicle=services.transition(self.vehicle.pk,self.vehicle.version,'review',self.owner)
        self.vehicle=services.transition(self.vehicle.pk,self.vehicle.version,'publish',self.owner)
    def login(self): self.client.force_login(self.owner)
    def test_public_pages_work_without_accounts(self):
        for url in ['/', '/contact/', '/information/how-it-works/', '/sitemap.xml','/robots.txt','/staff/login/']:
            self.assertEqual(self.client.get(url).status_code,200,url)
        self.assertNotContains(self.client.get('/'),'/staff/')
    def test_consumer_cannot_read_or_write_admin(self):
        urls=['/staff/',f'/staff/vehicles/{self.vehicle.pk}/','/staff/vehicles/add/','/staff/settings/','/staff/reports/','/staff/users/']
        for url in urls: self.assertEqual(self.client.get(url).status_code,302,url)
        self.client.force_login(self.consumer)
        for url in urls: self.assertEqual(self.client.get(url).status_code,403,url)
        self.assertEqual(self.client.post(reverse('vehicle_action',args=[self.vehicle.pk]),{'action':'publish','version':1}).status_code,403)
    def test_drafts_and_private_media_are_not_public(self):
        self.assertNotContains(self.client.get('/'),'Test make')
        self.assertEqual(self.client.get(reverse('vehicle',args=[self.vehicle.public_id])).status_code,404)
        self.assertEqual(self.client.get(reverse('photo',args=[self.vehicle.cover.public_id])).status_code,404)
        self.assertNotIn('private_notes',self.client.get('/availability/').content.decode())
    def test_incomplete_publication_rejected(self):
        self.vehicle.condition=''; self.vehicle.save()
        self.vehicle=services.transition(self.vehicle.pk,1,'review',self.owner)
        with self.assertRaises(ValidationError): services.transition(self.vehicle.pk,self.vehicle.version,'publish',self.owner)
        self.vehicle.refresh_from_db(); self.assertEqual(self.vehicle.status,'review')
    def test_listing_and_filters_show_published_stock(self):
        self.publish()
        self.assertContains(self.client.get('/?make=Test+make'),'Test model')
        self.assertEqual(self.client.get('/?make=Different').context['vehicles'].paginator.count,0)
        self.assertEqual(self.client.get(reverse('vehicle',args=[self.vehicle.public_id])).status_code,200)
        self.assertContains(self.client.get('/sitemap.xml'),str(self.vehicle.public_id))
    def test_sold_removed_from_all_public_surfaces(self):
        self.publish()
        photo=self.vehicle.cover
        sale=services.close_sale(self.vehicle.pk,self.vehicle.version,self.owner,self.buyer,Decimal('950000'),timezone.localdate(),'Test evidence')
        self.assertEqual(sale.commission,Decimal('23750.00'))
        self.assertNotContains(self.client.get('/'),'Test model')
        response=self.client.get(reverse('vehicle',args=[self.vehicle.public_id]))
        self.assertEqual(response.status_code,410); self.assertNotIn(b'Test model',response.content)
        self.assertIn('no-store',response['Cache-Control'])
        self.assertEqual(self.client.get(reverse('photo',args=[photo.public_id])).status_code,404)
        self.assertNotContains(self.client.get('/sitemap.xml'),str(self.vehicle.public_id))
        self.assertEqual(self.client.get('/availability/',{'ids':str(self.vehicle.public_id)}).json()['available'],[])
        self.assertTrue(Vehicle.objects.filter(pk=self.vehicle.pk).exists())
        self.login(); self.assertEqual(self.client.get(reverse('staff_vehicle',args=[self.vehicle.pk])).status_code,200)
    def test_sale_retry_is_idempotent(self):
        self.publish()
        args=[self.vehicle.pk,self.vehicle.version,self.owner,self.buyer,Decimal('950000'),timezone.localdate(),'Test evidence']
        first=services.close_sale(*args); second=services.close_sale(*args)
        self.assertEqual(first.pk,second.pk); self.assertEqual(Sale.objects.count(),1)
    def test_stale_edit_rejected(self):
        self.publish()
        with self.assertRaises(services.Conflict): services.transition(self.vehicle.pk,1,'withdraw',self.owner,'test')
    def test_enquiry_stale_after_sale_rejected(self):
        self.publish(); url=reverse('vehicle',args=[self.vehicle.public_id]); self.client.get(url)
        key=self.client.session['enquiry_tokens'][-1]
        services.close_sale(self.vehicle.pk,self.vehicle.version,self.owner,self.buyer,Decimal('900000'),timezone.localdate(),'Test evidence')
        response=self.client.post(url,{'submission_key':key,'name':'Another buyer','email':'other@example.test','preferred_contact':'email','kind':'enquiry','message':'Interested','privacy_consent':'on'})
        self.assertEqual(response.status_code,410); self.assertEqual(Enquiry.objects.count(),1)
    def test_enquiry_persists_without_email_and_duplicate_submit_safe(self):
        self.publish(); url=reverse('vehicle',args=[self.vehicle.public_id]); self.client.get(url)
        key=self.client.session['enquiry_tokens'][-1]
        data={'submission_key':key,'name':'Another buyer','email':'other@example.test','preferred_contact':'email','kind':'enquiry','message':'Interested','privacy_consent':'on'}
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertEqual(Enquiry.objects.filter(email='other@example.test').count(),1)
        self.assertTrue(Notification.objects.filter(state='inapp').exists())
    def test_submission_without_valid_session_token_rejected(self):
        response=self.client.post('/contact/',{'submission_key':uuid.uuid4(),'name':'Spam'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'expired')
    def test_reservations_hidden_and_safe_after_sale(self):
        self.publish()
        r=services.reserve(self.vehicle.pk,self.vehicle.version,self.owner,self.buyer,timezone.now()+timedelta(hours=1),'Test conditions')
        self.assertNotContains(self.client.get('/'),'Test model')
        self.vehicle.refresh_from_db()
        services.close_sale(self.vehicle.pk,self.vehicle.version,self.owner,self.buyer,Decimal('900000'),timezone.localdate(),'Test evidence')
        services.release_reservation(r.pk)
        self.vehicle.refresh_from_db(); self.assertEqual(self.vehicle.status,'sold')
    def test_expired_reservation_with_invalid_agreement_returns_to_review(self):
        self.publish()
        r=services.reserve(self.vehicle.pk,self.vehicle.version,self.owner,self.buyer,timezone.now()+timedelta(hours=1),'Test conditions')
        Vehicle.objects.filter(pk=self.vehicle.pk).update(agreement_end=timezone.localdate()-timedelta(days=1))
        services.release_reservation(r.pk)
        self.vehicle.refresh_from_db(); self.assertEqual(self.vehicle.status,'review')
    def test_sale_cancels_viewings_and_flags_other_enquiries(self):
        self.publish()
        other=Enquiry.objects.create(vehicle=self.vehicle,name='Other',phone='000',message='Test')
        viewing=Viewing.objects.create(enquiry=other,agent=self.owner,starts_at=timezone.now()+timedelta(days=1),ends_at=timezone.now()+timedelta(days=1,hours=1),location='Test',status='confirmed')
        services.close_sale(self.vehicle.pk,self.vehicle.version,self.owner,self.buyer,Decimal('900000'),timezone.localdate(),'Test evidence')
        viewing.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(viewing.status,'cancelled'); self.assertTrue(other.needs_review)
    def test_payment_settlement_uses_actual_money(self):
        self.publish(); sale=services.close_sale(self.vehicle.pk,self.vehicle.version,self.owner,self.buyer,Decimal('1000000'),timezone.localdate(),'Test')
        def pay(kind,amount): return services.record_payment(sale.pk,self.owner,kind=kind,amount=Decimal(amount),date=timezone.localdate(),method='Test',reference='REF',notes='Approved test')
        with self.assertRaises(ValidationError): pay('settlement','100')
        pay('proceeds','100000'); pay('commission_held','25000'); pay('deduction','5000'); pay('settlement','70000')
        self.assertEqual(sale.balances['settlement_due'],0); self.assertEqual(sale.balances['commission_due'],0)
        with self.assertRaises(ValidationError): pay('commission','1')
    def test_reversal_requires_reconciliation_and_never_republishes(self):
        self.publish(); sale=services.close_sale(self.vehicle.pk,self.vehicle.version,self.owner,self.buyer,Decimal('900000'),timezone.localdate(),'Test')
        p=services.record_payment(sale.pk,self.owner,kind='proceeds',amount=Decimal('100'),date=timezone.localdate(),method='Test',reference='REF',notes='')
        with self.assertRaises(ValidationError): services.reverse_sale(sale.pk,self.owner,'Test reversal')
        services.reverse_payment(p.pk,self.owner,'Refund reconciled')
        services.reverse_sale(sale.pk,self.owner,'Test reversal')
        self.vehicle.refresh_from_db(); self.assertEqual(self.vehicle.status,'review')
        self.assertNotContains(self.client.get('/'),'Test model')
    def test_bad_uploads_rejected_and_metadata_removed(self):
        with self.assertRaises(ValidationError): services.prepare_photo(SimpleUploadedFile('bad.jpg',b'<script>bad</script>'))
        prepared=services.prepare_photo(image_file())
        image=Image.open(prepared); self.assertEqual(image.format,'JPEG'); self.assertFalse(image.getexif())
    def test_photo_upload_and_reordering_work(self):
        self.login()
        response=self.client.post(reverse('photos_upload',args=[self.vehicle.pk]),{'version':self.vehicle.version,'rights_confirmed':'on','photos':[image_file('one.jpg'),image_file('two.jpg')]})
        self.assertEqual(response.status_code,302); self.assertEqual(self.vehicle.photos.count(),3)
        self.vehicle.refresh_from_db()
        data={'version':self.vehicle.version}
        for index,photo in enumerate(self.vehicle.photos.all()): data[f'alt_{photo.pk}']=f'View {index}'; data[f'order_{photo.pk}']=2-index
        self.client.post(reverse('photos_update',args=[self.vehicle.pk]),data)
        self.assertEqual(self.vehicle.cover.alt,'View 2')
    def test_cannot_remove_last_public_photo(self):
        self.publish(); self.login()
        self.client.post(reverse('photos_update',args=[self.vehicle.pk]),{'version':self.vehicle.version,f'delete_{self.vehicle.cover.pk}':'on'})
        self.assertEqual(self.vehicle.photos.count(),1)
    def test_private_pdf_requires_permission(self):
        doc=PrivateDocument.objects.create(vehicle=self.vehicle,label='Test contract',file=SimpleUploadedFile('test.pdf',b'%PDF-1.4\ntest'),uploaded_by=self.owner,scanned_at=timezone.now())
        self.assertEqual(self.client.get(reverse('document_download',args=[doc.pk])).status_code,302)
        self.client.force_login(self.consumer); self.assertEqual(self.client.get(reverse('document_download',args=[doc.pk])).status_code,403)
        self.login(); response=self.client.get(reverse('document_download',args=[doc.pk])); self.assertEqual(response.status_code,200); self.assertIn('attachment',response['Content-Disposition'])
    def test_staff_role_restrictions(self):
        call_command('bootstrap',stdout=io.StringIO())
        staff=get_user_model().objects.create_user('agent',password='test-long-password',is_staff=True)
        staff.groups.add(Group.objects.get(name='Sales agent')); self.client.force_login(staff)
        self.assertEqual(self.client.get('/staff/').status_code,200)
        self.assertEqual(self.client.get('/staff/settings/').status_code,403)
        self.assertEqual(self.client.get('/staff/reports/').status_code,403)
        self.assertEqual(self.client.get('/staff/vehicles/add/').status_code,403)
        self.assertEqual(self.client.get(reverse('vehicle_sell',args=[self.vehicle.pk])).status_code,403)
    def test_deactivated_staff_session_denied(self):
        self.login(); self.owner.is_active=False; self.owner.save()
        self.assertEqual(self.client.get('/staff/').status_code,302)
    def test_get_cannot_change_state(self):
        self.login(); self.assertEqual(self.client.get(reverse('vehicle_action',args=[self.vehicle.pk])).status_code,405)
    def test_every_staff_screen_renders(self):
        self.login()
        urls=['/staff/','/staff/vehicles/','/staff/vehicles/add/','/staff/settings/','/staff/reports/','/staff/audit/','/staff/notifications/','/staff/users/','/staff/users/add/','/staff/sales/','/staff/password/']
        urls+=[f'/staff/records/{kind}/' for kind in ['sellers','enquiries','viewings','tasks','offers']]
        urls+=[f'/staff/records/{kind}/add/' for kind in ['sellers','enquiries','viewings','tasks','offers']]
        urls+=[reverse('staff_vehicle',args=[self.vehicle.pk]),reverse('vehicle_preview',args=[self.vehicle.pk]),reverse('vehicle_edit',args=[self.vehicle.pk]),reverse('record_edit',args=['enquiries',self.buyer.pk])]
        for url in urls: self.assertEqual(self.client.get(url).status_code,200,url)
    def test_csv_injection_escape(self):
        self.assertEqual(services.safe_csv('=SUM(A1)'),"'=SUM(A1)")
        self.assertEqual(services.safe_csv('  +CMD'),"'  +CMD")
    def test_failed_notification_keeps_enquiry(self):
        Notification.objects.create(subject='Test',body='Test',recipient='test@example.test')
        call_command('process_jobs',stdout=io.StringIO())
        self.assertEqual(Notification.objects.get().state,'failed'); self.assertEqual(Enquiry.objects.count(),1)
    @override_settings(MFA_REQUIRED=True)
    def test_mfa_required_and_code_replay_blocked(self):
        import pyotp
        from brokerage.security import cipher
        self.login(); session=self.client.session; session['password_verified_at']=__import__('time').time(); session.save()
        self.assertRedirects(self.client.get('/staff/'),reverse('mfa'),fetch_redirect_response=False)
        self.assertEqual(self.client.get('/staff/security/').status_code,200)
        security=StaffSecurity.objects.get(user=self.owner); secret=cipher().decrypt(security.secret_encrypted.encode()).decode()
        code=pyotp.TOTP(secret).now()
        self.assertEqual(self.client.post('/staff/security/',{'code':code}).status_code,302)
        self.assertTrue(self.client.session['mfa_verified'])
        session=self.client.session; session['mfa_verified']=False; session.save()
        self.assertContains(self.client.post('/staff/security/',{'code':code}),'already used')
    def test_fixed_commission_snapshot(self):
        self.vehicle.fee_type='fixed'; self.vehicle.fee_value=Decimal('5000'); self.vehicle.save(); self.publish()
        sale=services.close_sale(self.vehicle.pk,self.vehicle.version,self.owner,self.buyer,Decimal('1000000'),timezone.localdate(),'Test')
        self.assertEqual(sale.commission,Decimal('5000'))
        Vehicle.objects.filter(pk=self.vehicle.pk).update(fee_value=Decimal('9000'))
        sale.refresh_from_db(); self.assertEqual(sale.commission,Decimal('5000'))
    def test_vehicle_form_save_and_stale_form_conflict(self):
        from django.forms.models import model_to_dict
        self.login()
        data=model_to_dict(self.vehicle)
        data={k:('' if v is None else v) for k,v in data.items()}
        data['make']='Edited make'; data['agreement_confirmed']='on'
        url=reverse('vehicle_edit',args=[self.vehicle.pk])
        response=self.client.post(url,data)
        self.assertEqual(response.status_code,302,response.context['form'].errors if response.status_code==200 else '')
        self.vehicle.refresh_from_db(); self.assertEqual(self.vehicle.make,'Edited make')
        response=self.client.post(url,data)
        self.assertContains(response,'changed while you were editing')
    def test_sale_and_finance_screens(self):
        self.publish(); self.login()
        self.assertEqual(self.client.get(reverse('vehicle_sell',args=[self.vehicle.pk])).status_code,200)
        data={'version':self.vehicle.version,'buyer':self.buyer.pk,'amount':'900000','sale_date':timezone.localdate().isoformat(),'evidence':'Test confirmation','confirm':'on'}
        self.assertEqual(self.client.post(reverse('vehicle_sell',args=[self.vehicle.pk]),data).status_code,302)
        sale=Sale.objects.get()
        self.assertEqual(self.client.get(reverse('sale_detail',args=[sale.pk])).status_code,200)
        self.assertContains(self.client.get('/staff/reports/'),'900,000')
        self.assertEqual(self.client.get('/staff/reports/?export=csv')['Content-Type'],'text/csv')
    def test_two_viewings_cannot_overlap(self):
        from brokerage.forms import ViewingForm
        self.publish()
        start=timezone.now()+timedelta(days=1)
        Viewing.objects.create(enquiry=self.buyer,agent=self.owner,starts_at=start,ends_at=start+timedelta(hours=1),location='Test',status='confirmed')
        form=ViewingForm({'enquiry':self.buyer.pk,'agent':self.owner.pk,'starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=30)).isoformat(),'location':'Test','status':'confirmed'})
        self.assertFalse(form.is_valid()); self.assertIn('already has',str(form.errors))
    @override_settings(DEBUG=False,CLAMAV_HOST='')
    def test_production_rejects_unscanned_documents(self):
        from brokerage.forms import DocumentForm
        form=DocumentForm({'label':'Test'},{'file':SimpleUploadedFile('test.pdf',b'%PDF-1.4 test')})
        self.assertFalse(form.is_valid()); self.assertIn('scanner',str(form.errors))
    def test_scanner_threat_rejected(self):
        from brokerage.scanning import scan_document
        with override_settings(CLAMAV_HOST='scanner'),patch('brokerage.scanning.socket.create_connection') as connection_mock:
            connection_mock.return_value.__enter__.return_value.recv.return_value=b'stream: Test-Threat FOUND\x00'
            with self.assertRaises(ValidationError): scan_document(SimpleUploadedFile('test.pdf',b'%PDF-1.4 test'))
    def test_csrf_protects_staff_mutations(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True); client.force_login(self.owner)
        self.assertEqual(client.post(reverse('vehicle_action',args=[self.vehicle.pk]),{'version':1,'action':'review'}).status_code,403)

@override_settings(MFA_REQUIRED=False,MEDIA_ROOT=TEST_STORAGE,STORAGES=TEST_STORAGES)
class RecoveryTests(TransactionTestCase):
    def test_encrypted_backup_restores_sold_state_and_media(self):
        from cryptography.fernet import Fernet
        owner=get_user_model().objects.create_superuser('restore_owner','owner@example.test','test-long-password')
        v,e=stock(owner,'RESTORE-001'); v.status='available'; v.save()
        services.close_sale(v.pk,v.version,owner,e,Decimal('1000000'),timezone.localdate(),'Test evidence')
        backup=settings.BASE_DIR/'test-results'/f'{uuid.uuid4().hex}.enc'
        try:
            with patch.dict(os.environ,{'BACKUP_KEY':Fernet.generate_key().decode()}):
                call_command('backup',str(backup),writes_paused=True,stdout=io.StringIO())
                self.assertNotIn(b'Test buyer',backup.read_bytes())
                call_command('flush',verbosity=0,interactive=False)
                call_command('restore_backup',str(backup),confirm_empty_restore=True,stdout=io.StringIO())
                restored=Vehicle.objects.get(stock_reference='RESTORE-001')
                self.assertEqual(restored.status,'sold')
                self.assertTrue(restored.cover.image.storage.exists(restored.cover.image.name))
                self.assertEqual(self.client.get(reverse('vehicle',args=[restored.public_id])).status_code,410)
        finally: backup.unlink(missing_ok=True)

@override_settings(MFA_REQUIRED=False,MEDIA_ROOT=TEST_STORAGE,STORAGES=TEST_STORAGES)
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def test_two_agents_cannot_sell_same_vehicle_twice(self):
        if connection.vendor!='postgresql': self.skipTest('Requires PostgreSQL row locks; SQLite is local preview only.')
        owner=get_user_model().objects.create_superuser('concurrent','owner@example.test','test-long-password')
        v,buyer=stock(owner,'RACE-001'); v.status='available'; v.save()
        def sell():
            close_old_connections()
            try:
                u=get_user_model().objects.get(pk=owner.pk); e=Enquiry.objects.get(pk=buyer.pk)
                return services.close_sale(v.pk,v.version,u,e,Decimal('900000'),timezone.localdate(),'Test').pk
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:sell(),range(2)))
        self.assertEqual(len(set(results)),1); self.assertEqual(Sale.objects.filter(active=True).count(),1)
