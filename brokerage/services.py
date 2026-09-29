from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import hashlib
import uuid
from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import (Vehicle, VehiclePhoto, AuditEvent, Sale, Reservation, Enquiry, Viewing,
                     Notification, SiteSettings, Payment, RateLimit)

class Conflict(ValidationError): pass

def audit(actor, action, obj, details=None):
    return AuditEvent.objects.create(actor=actor if getattr(actor,'is_authenticated',False) else None,
        action=action, target=f'{obj._meta.model_name}:{obj.pk}', details=details or {})

def notify(subject, body):
    email=SiteSettings.current().notification_email
    return Notification.objects.create(subject=subject,body=body,recipient=email,state='pending' if email else 'inapp')

def notify_enquiry(enquiry):
    vehicle = enquiry.vehicle
    creator = vehicle.created_by if vehicle else None
    if creator and creator.is_active and creator.is_staff:
        email = creator.email.strip()
        subject = f'New enquiry: {vehicle.stock_reference}'
        body = f'New enquiry for {vehicle} ({vehicle.stock_reference}).\nReference {enquiry.reference}. Sign in to the staff workspace to review the customer details and respond.'
        if not email:
            body += '\nThe vehicle creator has no email address. Add it in Staff access.'
        return Notification.objects.create(subject=subject, body=body, recipient=email,
            state='pending' if email else 'inapp')
    return notify('New website enquiry',
        f'Reference {enquiry.reference}. Sign in to the staff workspace to review it.'
        + (' The vehicle creator is unavailable; administrator follow-up is required.' if vehicle else ''))


def rate_allowed(value, limit=8, seconds=900):
    key=hashlib.sha256(value.encode()).hexdigest()
    now=timezone.now()
    with transaction.atomic():
        item,_=RateLimit.objects.get_or_create(key=key,defaults={'expires_at':now+timedelta(seconds=seconds)})
        item=RateLimit.objects.select_for_update().get(pk=item.pk)
        if item.expires_at <= now:
            item.count=0; item.expires_at=now+timedelta(seconds=seconds)
        item.count+=1
        item.save()
        return item.count<=limit

def publication_errors(vehicle):
    issues=[]
    for field,label in [('make','Make'),('model','Model'),('year','Year'),('body_type','Body type'),
        ('fuel','Fuel'),('transmission','Transmission'),('colour','Colour'),('currency','Currency'),
        ('location','Location'),('condition','Condition'),('known_defects','Known defects disclosure')]:
        if not getattr(vehicle,field): issues.append(f'{label} is required.')
    if not vehicle.price or vehicle.price<=0: issues.append('Enter a positive asking price.')
    if not vehicle.assigned_to_id: issues.append('Assign a responsible staff member.')
    if not vehicle.agreement_confirmed: issues.append('Confirm the seller agreement.')
    if not vehicle.seller.verified: issues.append('Verify the seller before publishing.')
    if not vehicle.agreement_start or not vehicle.agreement_end: issues.append('Enter both agreement dates.')
    elif not vehicle.agreement_start<=timezone.localdate()<=vehicle.agreement_end: issues.append('The seller agreement is not currently valid.')
    if not vehicle.photos.exists(): issues.append('Upload at least one genuine vehicle photograph.')
    return issues

def check_version(vehicle, version):
    if vehicle.version != int(version): raise Conflict('This vehicle changed while you were editing. Reload it before trying again.')

def bump(vehicle):
    vehicle.version+=1
    vehicle.save()

@transaction.atomic
def transition(vehicle_id, version, action, actor, reason=''):
    v=Vehicle.objects.select_for_update().get(pk=vehicle_id)
    check_version(v,version)
    allowed={
      'review':({'draft','withdrawn'},'review','change_vehicle'),
      'draft':({'review'},'draft','change_vehicle'),
      'publish':({'review'},'available','publish_vehicle'),
      'withdraw':({'draft','review','available','reserved'},'withdrawn','change_vehicle'),
      'archive':({'sold','withdrawn'},'archived','change_vehicle'),
    }
    if action not in allowed: raise ValidationError('Unknown inventory action.')
    states,target,perm=allowed[action]
    if not actor.has_perm('brokerage.'+perm): raise ValidationError('You do not have permission for this action.')
    if v.status not in states: raise ValidationError('This action is not available for the current vehicle state.')
    if action in {'withdraw','archive','draft'} and not reason.strip(): raise ValidationError('Enter a reason for this action.')
    if action=='publish':
        errors=publication_errors(v)
        if errors: raise ValidationError(errors)
        v.published_at=timezone.now()
    before=v.status
    v.status=target
    bump(v)
    if action in {'withdraw','archive'}:
        Reservation.objects.filter(vehicle=v,active=True).update(active=False)
        Viewing.objects.filter(enquiry__vehicle=v,status__in=['requested','confirmed']).update(status='cancelled',outcome='Vehicle no longer available.')
    audit(actor,action,v,{'from':before,'to':target,'reason':reason})
    return v

def prepare_photo(upload):
    if upload.size>12*1024*1024: raise ValidationError(f'{upload.name}: photos must be 12 MB or smaller.')
    try:
        with Image.open(upload) as im:
            if im.format not in {'JPEG','PNG','WEBP'}: raise ValidationError('Use JPEG, PNG or WebP photos.')
            if im.width*im.height>36_000_000: raise ValidationError('Image dimensions are too large.')
            im.load()
            im=ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((1920,1440))
            content=BytesIO(); im.save(content,format='JPEG',quality=86,optimize=True)
            return ContentFile(content.getvalue(), name=f'{uuid.uuid4().hex}.jpg')
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError):
        raise ValidationError('One of the photos could not be read. Use an undamaged JPEG, PNG or WebP file.')

@transaction.atomic
def reserve(vehicle_id, version, actor, enquiry, expires_at, conditions, deposit_reference=''):
    v=Vehicle.objects.select_for_update().get(pk=vehicle_id)
    check_version(v,version)
    if v.status!='available': raise ValidationError('Only an available vehicle can be reserved.')
    if enquiry.vehicle_id!=v.pk: raise ValidationError('Choose an enquiry for this vehicle.')
    if expires_at<=timezone.now(): raise ValidationError('The reservation expiry must be in the future.')
    r=Reservation.objects.create(vehicle=v,enquiry=enquiry,expires_at=expires_at,conditions=conditions,
        deposit_reference=deposit_reference,created_by=actor)
    v.status='reserved'; bump(v)
    audit(actor,'reserve',v,{'reservation':r.pk,'expires':expires_at.isoformat()})
    return r

@transaction.atomic
def release_reservation(reservation_id, actor=None):
    initial=Reservation.objects.get(pk=reservation_id)
    v=Vehicle.objects.select_for_update().get(pk=initial.vehicle_id)
    r=Reservation.objects.select_for_update().get(pk=reservation_id)
    if not r.active: return
    r.active=False; r.save()
    if v.status=='reserved':
        v.status='review' if publication_errors(v) else 'available'
        bump(v)
    audit(actor,'release_reservation',v,{'reservation':r.pk,'result':v.status})

@transaction.atomic
def close_sale(vehicle_id, version, actor, buyer, amount, sale_date, evidence):
    if not actor.has_perm('brokerage.close_sale'): raise ValidationError('Sale confirmation permission is required.')
    v=Vehicle.objects.select_for_update().get(pk=vehicle_id)
    # Retrying a successful request is safe and does not create another sale.
    existing=Sale.objects.filter(vehicle=v,active=True).first()
    if existing:
        if existing.buyer_id==buyer.pk and existing.amount==amount: return existing
        raise Conflict('This vehicle already has a confirmed sale.')
    check_version(v,version)
    if v.status not in {'available','reserved'}: raise ValidationError('Only available or reserved vehicles can be sold.')
    if buyer.vehicle_id!=v.pk: raise ValidationError('The buyer enquiry must belong to this vehicle.')
    if amount<=0: raise ValidationError('Enter a positive final sale price.')
    if sale_date>timezone.localdate(): raise ValidationError('The sale date cannot be in the future.')
    commission=(amount*v.fee_value/100 if v.fee_type=='percent' else v.fee_value).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    sale=Sale.objects.create(vehicle=v,buyer=buyer,agent=actor,amount=amount,asking_price_at_sale=v.price,currency=v.currency,
        sale_date=sale_date,evidence=evidence,fee_type=v.fee_type,fee_value=v.fee_value,fee_payer=v.fee_payer,
        fee_notes=v.fee_notes,commission=commission)
    v.status='sold'; v.sold_at=timezone.now(); bump(v)
    Reservation.objects.filter(vehicle=v,active=True).update(active=False)
    Enquiry.objects.filter(vehicle=v).exclude(stage__in=['won','closed']).update(needs_review=True)
    buyer.stage='won'; buyer.needs_review=False; buyer.save()
    Viewing.objects.filter(enquiry__vehicle=v,status__in=['requested','confirmed']).update(status='cancelled',outcome='Vehicle sold. Contact the buyer before any new arrangements.')
    audit(actor,'sold',v,{'sale':sale.pk,'amount':str(amount),'currency':v.currency})
    notify(f'{v.stock_reference} marked sold','The public listing has been removed. Review related enquiries and cancelled viewings in the staff workspace.')
    return sale

@transaction.atomic
def reverse_sale(sale_id, actor, reason):
    original=Sale.objects.get(pk=sale_id)
    v=Vehicle.objects.select_for_update().get(pk=original.vehicle_id)
    sale=Sale.objects.select_for_update().get(pk=sale_id)
    if not actor.has_perm('brokerage.reverse_sale'): raise ValidationError('Sale reversal permission is required.')
    if not sale.active: raise ValidationError('This sale has already been reversed.')
    if not reason.strip(): raise ValidationError('A reversal reason is required.')
    if sale.payments.filter(reversed=False).exists():
        raise ValidationError('Reconcile and reverse all payment entries first, documenting actual refunds separately in each reversal reason.')
    sale.active=False; sale.reversal_reason=reason; sale.save()
    v.status='review'; v.sold_at=None; bump(v)
    audit(actor,'sale_reversed',sale,{'reason':reason,'vehicle_state':'review'})
    notify('Sale reversed',f'{v.stock_reference} requires fresh publication review.')

@transaction.atomic
def record_payment(sale_id, actor, **data):
    sale=Sale.objects.select_for_update().get(pk=sale_id)
    if not sale.active: raise ValidationError('Cannot post a payment to a reversed sale.')
    amount=data['amount']; kind=data['kind']; balances=sale.balances
    if amount<=0: raise ValidationError('Amount must be positive.')
    if kind in {'settlement','refund','commission_held','deduction'} and amount>balances['settlement_due']:
        raise ValidationError('This amount exceeds unallocated vehicle proceeds actually held.')
    if kind in {'commission','commission_held'} and amount>balances['commission_due']:
        raise ValidationError('This amount exceeds the outstanding commission.')
    if kind=='commission_held' and sale.fee_payer!='seller': raise ValidationError('Buyer-paid commission cannot be deducted from seller proceeds.')
    if kind=='deduction' and not data.get('notes','').strip(): raise ValidationError('Record the seller-approved deduction and its evidence in Notes.')
    payment=Payment.objects.create(sale=sale,recorded_by=actor,**data)
    audit(actor,'payment_recorded',payment,{'amount':str(amount),'kind':kind,'currency':sale.currency})
    return payment

@transaction.atomic
def reverse_payment(payment_id, actor, reason):
    original=Payment.objects.get(pk=payment_id)
    sale=Sale.objects.select_for_update().get(pk=original.sale_id)
    p=Payment.objects.select_for_update().get(pk=payment_id)
    if p.reversed: raise ValidationError('This entry has already been reversed.')
    if not reason.strip(): raise ValidationError('A reversal reason and reconciliation evidence are required.')
    p.reversed=True; p.reversal_reason=reason; p.save()
    if sale.balances['settlement_due']<0: raise ValidationError('Reverse dependent allocations or settlements before reversing these proceeds.')
    audit(actor,'payment_reversed',p,{'reason':reason})

def safe_csv(value):
    value=str(value if value is not None else '')
    return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value
