import csv
import hmac
import io
import json
import secrets
import time
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import pyotp
import qrcode
import qrcode.image.svg
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction, models
from django.db.models import Count, Q, Sum, Case, When, F, FloatField
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from .forms import *
from .models import *
from .security import cipher, staff_required
from . import services

def error_messages(request,error):
    for message in error.messages: messages.error(request,message)

def page(request, queryset, size=20):
    if not queryset.ordered: queryset=queryset.order_by('-pk')
    return Paginator(queryset,size).get_page(request.GET.get('page'))

def inventory(request):
    base=Vehicle.objects.public().prefetch_related('photos').annotate(mileage_km=Case(
        When(mileage_unit='miles',then=F('mileage')*1.609344),default=F('mileage'),output_field=FloatField()))
    vehicles=base
    term=request.GET.get('q','').strip()[:100]
    if term: vehicles=vehicles.filter(Q(make__icontains=term)|Q(model__icontains=term)|Q(variant__icontains=term)|Q(stock_reference__icontains=term))
    for field in ['make','model','fuel','transmission','body_type','location','currency']:
        if request.GET.get(field): vehicles=vehicles.filter(**{field:request.GET[field]})
    for param,lookup in [('min_price','price__gte'),('max_price','price__lte'),('min_year','year__gte'),('max_year','year__lte'),('max_mileage','mileage_km__lte')]:
        value=request.GET.get(param,'')
        if value:
            try:
                n=Decimal(value)
                if n.is_finite() and 0<=n<=10**12: vehicles=vehicles.filter(**{lookup:n})
            except Exception: pass
    sort=request.GET.get('sort','newest')
    currencies=list(base.order_by().values_list('currency',flat=True).distinct())
    sort_options=[('newest','Newest listed'),('year','Newest year'),('mileage','Lowest mileage')]
    if len(currencies)<=1 or request.GET.get('currency'): sort_options += [('price','Price low to high'),('-price','Price high to low')]
    order={'newest':'-published_at','year':'-year','mileage':'mileage_km','price':'price','-price':'-price'}
    if sort not in dict(sort_options): sort='newest'
    vehicles=vehicles.order_by(order[sort],'-id')
    filters={f:list(base.order_by(f).values_list(f,flat=True).distinct()) for f in ['make','model','fuel','transmission','body_type','location','currency']}
    query=request.GET.copy(); query.pop('page',None)
    return render(request,'public/inventory.html',{'vehicles':page(request,vehicles,12),'filters':filters,'sort_options':sort_options,'sort':sort,'query':query.urlencode()})

def enquiry_form(request):
    if request.method=='POST': return PublicEnquiryForm(request.POST)
    key=str(uuid.uuid4())
    tokens=request.session.get('enquiry_tokens',[])
    request.session['enquiry_tokens']=(tokens+[key])[-20:]
    return PublicEnquiryForm(initial={'submission_key':key})

def accept_enquiry(request,form,vehicle=None):
    key=request.POST.get('submission_key','')
    if key not in request.session.get('enquiry_tokens',[]):
        form.add_error(None,'This form has expired. Reload the page and try again.'); return None
    existing=Enquiry.objects.filter(submission_key=key).first()
    if existing:
        request.session['receipt']=str(existing.reference)
        return redirect('receipt')
    if not form.is_valid(): return None
    if not services.rate_allowed('enquiry:'+request.META.get('REMOTE_ADDR',''),limit=12,seconds=3600):
        form.add_error(None,'Too many requests. Please try again later.'); return None
    with transaction.atomic():
        if vehicle:
            vehicle=Vehicle.objects.select_for_update().get(pk=vehicle.pk)
            if vehicle.status!='available': return render(request,'public/unavailable.html',status=410)
        e=form.save(commit=False); e.vehicle=vehicle
        if e.kind=='viewing' and not vehicle:
            form.add_error('kind','Select a vehicle first to request a viewing.'); return None
        e.stage='viewing_requested' if e.kind=='viewing' else 'new'
        e.save()
        services.notify_enquiry(e)
        request.session['receipt']=str(e.reference)
    return redirect('receipt')

def vehicle_detail(request,public_id):
    v=get_object_or_404(Vehicle,public_id=public_id)
    if v.status!='available':
        if v.status in {'sold','archived'}: return render(request,'public/unavailable.html',status=410)
        raise Http404
    form=enquiry_form(request)
    if request.method=='POST':
        result=accept_enquiry(request,form,v)
        if result: return result
    return render(request,'public/vehicle.html',{'vehicle':v,'form':form,'photos':v.photos.all(),'preview':False})

def contact(request):
    form=enquiry_form(request)
    form.fields['kind'].widget=forms.HiddenInput()
    form.fields['requested_time'].widget=forms.HiddenInput()
    if request.method=='POST':
        result=accept_enquiry(request,form)
        if result: return result
    return render(request,'public/contact.html',{'form':form})

def receipt(request):
    ref=request.session.get('receipt')
    if not ref: return redirect('inventory')
    return render(request,'public/receipt.html',{'reference':ref})

def content_page(request,slug):
    mapping={'about':('About the brokerage','about'),'how-it-works':('How brokerage works','process'),
        'privacy':('Privacy','privacy'),'terms':('Enquiry and brokerage terms','terms')}
    if slug not in mapping: raise Http404
    title,field=mapping[slug]
    return render(request,'public/content.html',{'title':title,'content':getattr(SiteSettings.current(),field),'slug':slug})

def availability(request):
    ids=request.GET.get('ids','').split(',')[:50]
    valid=[]
    for item in ids:
        try: valid.append(uuid.UUID(item))
        except ValueError: pass
    return JsonResponse({'available':[str(i) for i in Vehicle.objects.public().filter(public_id__in=valid).values_list('public_id',flat=True)]})

def photo(request,public_id):
    image=get_object_or_404(VehiclePhoto.objects.select_related('vehicle'),public_id=public_id)
    if image.vehicle.status!='available':
        if not (request.user.is_authenticated and request.user.is_active and request.user.is_staff and request.user.has_perm('brokerage.view_vehicle') and (not settings.MFA_REQUIRED or request.session.get('mfa_verified'))): raise Http404
    try: response=FileResponse(image.image.open('rb'),content_type='image/jpeg')
    except FileNotFoundError: raise Http404
    return response

def sitemap(request):
    from xml.sax.saxutils import escape
    urls=[settings.PUBLIC_ORIGIN+reverse('inventory')]
    urls.extend(settings.PUBLIC_ORIGIN+reverse('vehicle',args=[v]) for v in Vehicle.objects.public().values_list('public_id',flat=True))
    return HttpResponse('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+escape(u)+'</loc></url>' for u in urls)+'</urlset>',content_type='application/xml')

def robots(request):
    return HttpResponse('User-agent: *\nDisallow: /staff/\nDisallow: /files/\nSitemap: '+settings.PUBLIC_ORIGIN+'/sitemap.xml\n',content_type='text/plain')

def staff_login(request):
    form=StaffLoginForm(request,data=request.POST or None)
    if request.method=='POST':
        ip=request.META.get('REMOTE_ADDR','')
        allowed=services.rate_allowed('login-ip:'+ip,30) and services.rate_allowed('login-user:'+request.POST.get('username','').casefold(),10)
        if not allowed: form.add_error(None,'Too many sign-in attempts. Wait 15 minutes before trying again.')
        elif form.is_valid():
            login(request,form.get_user())
            request.session['mfa_verified']=False
            request.session['password_verified_at']=time.time()
            services.audit(request.user,'sign_in',request.user)
            return redirect('mfa' if settings.MFA_REQUIRED else 'dashboard')
    return render(request,'staff/login.html',{'form':form})

@require_POST
def staff_logout(request):
    logout(request)
    return redirect('staff_login')

def setup_owner(request,token):
    token_file=settings.BASE_DIR/'.bootstrap-token'
    if get_user_model().objects.filter(is_superuser=True).exists() or not token_file.exists(): raise Http404
    if not hmac.compare_digest(token,token_file.read_text().strip()): raise Http404
    form=OwnerForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            if get_user_model().objects.filter(is_superuser=True).exists(): raise Http404
            u=form.save(commit=False); u.is_staff=True; u.is_superuser=True; u.save()
            services.audit(u,'owner_created',u)
        token_file.unlink(missing_ok=True)
        messages.success(request,'Owner account created. Sign in to secure it with your authenticator.')
        return redirect('staff_login')
    return render(request,'staff/form.html',{'form':form,'title':'Create your owner account','submit':'Create owner account','public_form':True,'intro':'This one-time setup creates the account that controls the private admin area.'})

def mfa(request):
    if not request.user.is_authenticated: return redirect('staff_login')
    if not request.user.is_staff or not request.user.is_active: raise PermissionDenied
    if time.time()-request.session.get('password_verified_at',0)>600 and not request.session.get('mfa_verified'):
        logout(request); return redirect('staff_login')
    security,_=StaffSecurity.objects.get_or_create(user=request.user)
    if security.enabled and request.session.get('mfa_verified'): return redirect('dashboard')
    if not security.secret_encrypted:
        security.secret_encrypted=cipher().encrypt(pyotp.random_base32().encode()).decode(); security.save()
    secret=cipher().decrypt(security.secret_encrypted.encode()).decode()
    if request.method=='POST':
        if not services.rate_allowed(f'mfa:{request.user.pk}',8): messages.error(request,'Too many attempts. Try again in 15 minutes.')
        else:
            with transaction.atomic():
                security=StaffSecurity.objects.select_for_update().get(pk=security.pk)
                totp=pyotp.TOTP(secret); step=int(time.time())//30
                matched=next((s for s in range(step-1,step+2) if s>security.last_step and hmac.compare_digest(totp.at(s*30),request.POST.get('code','').strip())),None)
                if matched is not None:
                    security.last_step=matched; security.enabled=True; security.save()
                    request.session.cycle_key(); request.session['mfa_verified']=True
                    services.audit(request.user,'mfa_verified',request.user)
                    return redirect('dashboard')
                messages.error(request,'The code was invalid or already used. Try the next code.')
    return render(request,'staff/mfa.html',{'enrolling':not security.enabled,'secret':secret if not security.enabled else ''})

def mfa_qr(request):
    if not request.user.is_authenticated or not request.user.is_staff or time.time()-request.session.get('password_verified_at',0)>600: raise PermissionDenied
    security=get_object_or_404(StaffSecurity,user=request.user,enabled=False)
    secret=cipher().decrypt(security.secret_encrypted.encode()).decode()
    uri=pyotp.TOTP(secret).provisioning_uri(name=request.user.username,issuer_name=SiteSettings.current().business_name)
    image=qrcode.make(uri,image_factory=qrcode.image.svg.SvgPathImage)
    return HttpResponse(image.to_string(),content_type='image/svg+xml')

@staff_required()
def dashboard(request):
    ctx={'inventory_counts':[],'enquiries':[],'tasks':[],'viewings':[],'notifications':[]}
    if request.user.has_perm('brokerage.view_vehicle'):
        counts=dict(Vehicle.objects.values('status').annotate(n=Count('id')).values_list('status','n'))
        ctx['inventory_counts']=[(key,label,counts.get(key,0)) for key,label in Vehicle.Status.choices]
        ctx['reservations']=Reservation.objects.filter(active=True).select_related('vehicle').order_by('expires_at')[:5]
    if request.user.has_perm('brokerage.view_enquiry'): ctx['enquiries']=Enquiry.objects.filter(Q(stage='new')|Q(needs_review=True)).select_related('vehicle')[:6]
    if request.user.has_perm('brokerage.view_task'): ctx['tasks']=Task.objects.filter(done=False).select_related('assigned_to')[:6]
    if request.user.has_perm('brokerage.view_viewing'): ctx['viewings']=Viewing.objects.filter(starts_at__gte=timezone.now(),status__in=['requested','confirmed']).select_related('enquiry').order_by('starts_at')[:5]
    if request.user.has_perm('brokerage.view_notification'): ctx['notifications']=Notification.objects.all()[:5]
    ctx['setup_needed']=not all([SiteSettings.current().currency,SiteSettings.current().privacy,SiteSettings.current().terms])
    return render(request,'staff/dashboard.html',ctx)

@staff_required('view_vehicle')
def staff_inventory(request):
    qs=Vehicle.objects.select_related('seller','assigned_to').prefetch_related('photos')
    q=request.GET.get('q','')[:100]
    if q: qs=qs.filter(Q(make__icontains=q)|Q(model__icontains=q)|Q(stock_reference__icontains=q)|Q(seller__name__icontains=q))
    status=request.GET.get('status','')
    if status: qs=qs.filter(status=status)
    return render(request,'staff/inventory.html',{'vehicles':page(request,qs),'statuses':Vehicle.Status.choices})

@staff_required('view_vehicle')
def staff_vehicle(request,pk):
    v=get_object_or_404(Vehicle.objects.select_related('seller','assigned_to'),pk=pk)
    return render(request,'staff/vehicle.html',{'vehicle':v,'publication_errors':services.publication_errors(v),
        'photo_form':PhotoUploadForm(),'document_form':DocumentForm(),'history':AuditEvent.objects.filter(target=f'vehicle:{pk}')[:12],
        'reservation':v.reservations.filter(active=True).first(),'sale':v.sales.filter(active=True).first()})

@staff_required()
def vehicle_edit(request,pk=None):
    perm='change_vehicle' if pk else 'add_vehicle'
    if not request.user.has_perm('brokerage.'+perm): raise PermissionDenied
    initial={'currency':SiteSettings.current().currency,'assigned_to':request.user,'stock_reference':'STK-'+secrets.token_hex(3).upper()}
    v=get_object_or_404(Vehicle,pk=pk) if pk else None
    if v and v.status in {'sold','archived'}:
        messages.error(request,'Closed vehicle details are locked. Reverse the sale or retain the historical record.')
        return redirect('staff_vehicle',pk=pk)
    form=VehicleForm(request.POST or None,instance=v,initial=initial if not v else None)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                obj=form.save(commit=False)
                if pk:
                    current=Vehicle.objects.select_for_update().get(pk=pk)
                    services.check_version(current,form.cleaned_data.get('version') or 0)
                    if current.status in {'sold','archived'}: raise ValidationError('The vehicle has been closed and cannot be edited.')
                    before={f:str(getattr(current,f)) for f in form.changed_data if f!='version'}
                    obj.status=current.status; obj.version=current.version+1
                    if obj.status=='available':
                        issues=services.publication_errors(obj)
                        if issues: raise ValidationError(issues)
                else: before={}; obj.version=1; obj.created_by=request.user
                obj.save()
                services.audit(request.user,'vehicle_updated' if pk else 'vehicle_created',obj,{'before':before,'after':{f:str(getattr(obj,f)) for f in before}})
            messages.success(request,'Vehicle saved. Upload photos and review it before publication.' if not pk else 'Vehicle updated.')
            return redirect('staff_vehicle',pk=obj.pk)
        except ValidationError as error: form.add_error(None,error)
    groups=[('Vehicle details',['stock_reference','seller','assigned_to','make','model','variant','year','registration_year','body_type']),
        ('Specifications',['mileage','mileage_unit','fuel','transmission','engine','drive_type','colour','seats','features']),
        ('Price and location',['price','currency','negotiable','location']),
        ('Description and condition',['description','condition','known_defects','service_history','inspection_notes','inspection_date','accident_history','ownership_info']),
        ('Private seller information',['registration_number','vin','seller_minimum','private_notes','agreement_confirmed','agreement_start','agreement_end','fee_type','fee_value','fee_payer','fee_notes'])]
    return render(request,'staff/vehicle_form.html',{'form':form,'groups':[(label,[form[f] for f in fields]) for label,fields in groups],'vehicle':v})

@require_POST
@staff_required('change_vehicle')
def vehicle_action(request,pk):
    try: services.transition(pk,int(request.POST.get('version','0')),request.POST.get('action'),request.user,request.POST.get('reason',''))
    except (ValueError,ValidationError) as error:
        if isinstance(error,ValidationError): error_messages(request,error)
        else: messages.error(request,'Invalid record version.')
    else: messages.success(request,'Vehicle status updated.')
    return redirect('staff_vehicle',pk=pk)

@staff_required('view_vehicle')
def vehicle_preview(request,pk):
    v=get_object_or_404(Vehicle,pk=pk)
    return render(request,'public/vehicle.html',{'vehicle':v,'photos':v.photos.all(),'preview':True})

@require_POST
@staff_required('change_vehicle')
def photos_upload(request,pk):
    form=PhotoUploadForm(request.POST,request.FILES)
    if form.is_valid():
        try:
            processed=[services.prepare_photo(f) for f in form.cleaned_data['photos']]
            with transaction.atomic():
                v=Vehicle.objects.select_for_update().get(pk=pk)
                services.check_version(v,request.POST.get('version',0))
                if v.status in {'sold','archived'}: raise ValidationError('Photos of closed vehicles cannot be changed.')
                pos=v.photos.count()
                for index,content in enumerate(processed): VehiclePhoto.objects.create(vehicle=v,image=content,position=pos+index,alt=f'{v} photograph {pos+index+1}')
                services.bump(v); services.audit(request.user,'photos_uploaded',v,{'count':len(processed)})
            messages.success(request,'Photos uploaded. Set descriptive captions and the cover photo below.')
        except ValidationError as error: error_messages(request,error)
    else:
        for errors in form.errors.values():
            for error in errors: messages.error(request,error)
    return redirect('staff_vehicle',pk=pk)

@require_POST
@staff_required('change_vehicle')
def photos_update(request,pk):
    try:
        with transaction.atomic():
            v=Vehicle.objects.select_for_update().get(pk=pk)
            services.check_version(v,request.POST.get('version',0))
            if v.status in {'sold','archived'}: raise ValidationError('Photos of closed vehicles cannot be changed.')
            remaining=0
            for photo in v.photos.all():
                if request.POST.get(f'delete_{photo.pk}'):
                    photo.delete()
                else:
                    photo.alt=request.POST.get(f'alt_{photo.pk}','').strip()[:180]
                    if not photo.alt: raise ValidationError('Each photo needs a meaningful description.')
                    photo.position=max(0,min(999,int(request.POST.get(f'order_{photo.pk}','0')))); photo.save(); remaining+=1
            if v.status=='available' and not remaining: raise ValidationError('An available vehicle must retain at least one photograph.')
            services.bump(v); services.audit(request.user,'photos_updated',v)
        messages.success(request,'Photo captions and order saved. The lowest position is the cover.')
    except (ValidationError,ValueError) as error:
        if isinstance(error,ValidationError): error_messages(request,error)
        else: messages.error(request,'Enter numeric photo positions.')
    return redirect('staff_vehicle',pk=pk)

@require_POST
@staff_required('add_privatedocument')
def document_upload(request,pk):
    form=DocumentForm(request.POST,request.FILES)
    if form.is_valid():
        doc=form.save(commit=False); doc.vehicle=get_object_or_404(Vehicle,pk=pk); doc.uploaded_by=request.user
        doc.scanned_at=getattr(form.cleaned_data['file'],'scanned_at',None); doc.save()
        services.audit(request.user,'document_uploaded',doc); messages.success(request,'Private document saved.')
    else:
        for errors in form.errors.values():
            for error in errors: messages.error(request,error)
    return redirect('staff_vehicle',pk=pk)

@staff_required('view_privatedocument')
def document_download(request,pk):
    doc=get_object_or_404(PrivateDocument,pk=pk)
    if not settings.DEBUG and not doc.scanned_at:
        return HttpResponse('This document must pass a malware scan before it can be downloaded in production.',status=503,content_type='text/plain')
    services.audit(request.user,'document_download',doc)
    try: return FileResponse(doc.file.open('rb'),as_attachment=True,filename=Path(doc.file.name).name,content_type='application/pdf')
    except FileNotFoundError: raise Http404

@staff_required('change_vehicle')
def vehicle_reserve(request,pk):
    v=get_object_or_404(Vehicle,pk=pk)
    form=ReserveForm(request.POST or None,vehicle=v,initial={'version':v.version})
    if request.method=='POST' and form.is_valid():
        try: services.reserve(pk,actor=request.user,**form.cleaned_data)
        except ValidationError as error: form.add_error(None,error)
        else: messages.success(request,'Vehicle reserved and removed from public stock.'); return redirect('staff_vehicle',pk=pk)
    return render(request,'staff/form.html',{'form':form,'title':f'Reserve {v.stock_reference}','submit':'Reserve vehicle','intro':'Choose an enquiry for this vehicle. Reserved vehicles are hidden from consumers.'})

@require_POST
@staff_required('change_vehicle')
def reservation_release(request,pk):
    r=get_object_or_404(Reservation,pk=pk)
    services.release_reservation(pk,request.user)
    messages.success(request,'Reservation released. Publication checks have been reapplied.')
    return redirect('staff_vehicle',pk=r.vehicle_id)

@staff_required('close_sale')
def vehicle_sell(request,pk):
    v=get_object_or_404(Vehicle,pk=pk)
    form=SaleForm(request.POST or None,vehicle=v,initial={'version':v.version,'amount':v.price})
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data.copy(); data.pop('confirm')
        try: sale=services.close_sale(pk,actor=request.user,**data)
        except ValidationError as error: form.add_error(None,error)
        else:
            messages.success(request,'Sale recorded. The vehicle is no longer on the consumer website.')
            return redirect('staff_vehicle',pk=pk)
    return render(request,'staff/form.html',{'form':form,'title':f'Mark {v.stock_reference} as sold','submit':'Confirm sale','intro':f'Currency: {v.currency}. This removes the listing, prevents new enquiries and cancels pending viewings. Create the buyer enquiry first if necessary.'})

RECORDS={
 'sellers':(Seller,SellerForm,'Sellers',['name','phone','email','verified']),
 'enquiries':(Enquiry,EnquiryForm,'Enquiries',['name','vehicle','stage','assigned_to','follow_up_at']),
 'viewings':(Viewing,ViewingForm,'Viewings',['enquiry','starts_at','agent','status']),
 'tasks':(Task,TaskForm,'Tasks',['title','assigned_to','due_at','done']),
 'offers':(Offer,OfferForm,'Offers',['enquiry','amount','currency','decision']),
}

@staff_required()
def record_list(request,kind):
    if kind not in RECORDS: raise Http404
    model,form,title,fields=RECORDS[kind]
    if not request.user.has_perm('brokerage.view_'+model._meta.model_name): raise PermissionDenied
    qs=model.objects.all()
    q=request.GET.get('q','').strip()[:100]
    if q:
        query=Q()
        for f in model._meta.fields:
            if isinstance(f,(models.CharField,models.TextField)) and f.name not in {'private_notes','notes'}: query|=Q(**{f.name+'__icontains':q})
        qs=qs.filter(query)
    if kind=='enquiries':
        qs=qs.select_related('vehicle','assigned_to')
        if request.GET.get('stage'): qs=qs.filter(stage=request.GET['stage'])
        if request.GET.get('review'): qs=qs.filter(needs_review=True)
    items=page(request,qs)
    rows=[]
    for obj in items:
        cells=[]
        for field in fields:
            value=getattr(obj,'get_'+field+'_display',lambda:getattr(obj,field))()
            if isinstance(value,bool): value='Yes' if value else 'No'
            cells.append(value)
        rows.append((obj,cells))
    return render(request,'staff/records.html',{'title':title,'kind':kind,'rows':rows,'page':items,
        'headers':[model._meta.get_field(f).verbose_name.title() for f in fields],
        'can_add':request.user.has_perm('brokerage.add_'+model._meta.model_name)})

@staff_required()
def record_edit(request,kind,pk=None):
    if kind not in RECORDS: raise Http404
    model,Form,title,fields=RECORDS[kind]
    can_change=request.user.has_perm('brokerage.'+('change_' if pk else 'add_')+model._meta.model_name)
    if not can_change and (not pk or not request.user.has_perm('brokerage.view_'+model._meta.model_name)): raise PermissionDenied
    obj=get_object_or_404(model,pk=pk) if pk else None
    form=Form(request.POST or None,instance=obj)
    if not can_change:
        for f in form.fields.values(): f.disabled=True
    if request.method=='POST':
        if not can_change: raise PermissionDenied
        if form.is_valid():
            try:
                with transaction.atomic():
                    item=form.save(commit=False)
                    if model==Viewing and item.status in {'requested','confirmed'}:
                        if not item.enquiry.vehicle_id: raise ValidationError('Choose an enquiry linked to a vehicle.')
                        vehicle=Vehicle.objects.select_for_update().get(pk=item.enquiry.vehicle_id)
                        get_user_model().objects.select_for_update().get(pk=item.agent_id)
                        if vehicle.status not in {'available','reserved'}: raise ValidationError('This vehicle is no longer available.')
                        if item.status=='confirmed' and Viewing.objects.filter(agent=item.agent,status='confirmed',starts_at__lt=item.ends_at,ends_at__gt=item.starts_at).exclude(pk=item.pk).exists(): raise ValidationError('This agent already has a confirmed viewing at this time.')
                    if model==Enquiry and item.vehicle_id:
                        vehicle=Vehicle.objects.select_for_update().get(pk=item.vehicle_id)
                        if not pk and vehicle.status not in {'available','reserved'}: raise ValidationError('This vehicle is no longer available for a new enquiry.')
                        if item.stage!='new' and not item.first_contact_at: item.first_contact_at=timezone.now()
                    if model==Seller and item.verified:
                        item.verified_at=timezone.now(); item.verified_by=request.user
                    item.save(); form.save_m2m()
                    services.audit(request.user,'record_updated' if pk else 'record_created',item,{'fields':form.changed_data})
                    if model==Task and ('assigned_to' in form.changed_data or not pk): services.notify('Task assigned',f'Task {item.pk}: {item.title}')
                messages.success(request,'Record saved.')
                return redirect('record_list',kind=kind)
            except ValidationError as error: form.add_error(None,error)
    related=[]
    if model==Enquiry and obj:
        match=Q()
        if obj.email: match|=Q(email__iexact=obj.email)
        if obj.phone: match|=Q(phone=obj.phone)
        related=Enquiry.objects.filter(match).exclude(pk=obj.pk)[:5] if match else []
    return render(request,'staff/form.html',{'form':form,'title':('Edit ' if pk else 'Add ')+model._meta.verbose_name,'submit':'Save record' if can_change else None,'related':related})

@staff_required('view_sale')
def sales_list(request):
    qs=Sale.objects.select_related('vehicle','buyer','agent')
    if request.GET.get('state')=='reversed': qs=qs.filter(active=False)
    else: qs=qs.filter(active=True)
    return render(request,'staff/sales.html',{'sales':page(request,qs)})

@staff_required('view_sale')
def sale_detail(request,pk):
    sale=get_object_or_404(Sale.objects.select_related('vehicle','buyer','agent'),pk=pk)
    return render(request,'staff/sale.html',{'sale':sale,'balances':sale.balances,'payment_form':PaymentForm(),'handover_form':HandoverForm(instance=sale)})

@require_POST
@staff_required('add_payment')
def payment_add(request,pk):
    form=PaymentForm(request.POST)
    if form.is_valid():
        try: services.record_payment(pk,request.user,**form.cleaned_data)
        except ValidationError as error: error_messages(request,error)
        else: messages.success(request,'Payment recorded.')
    else:
        for errors in form.errors.values():
            for error in errors: messages.error(request,error)
    return redirect('sale_detail',pk=pk)

@require_POST
@staff_required('change_payment')
def payment_reverse(request,pk):
    p=get_object_or_404(Payment,pk=pk)
    try: services.reverse_payment(pk,request.user,request.POST.get('reason',''))
    except ValidationError as error: error_messages(request,error)
    else: messages.success(request,'Entry reversed. Original evidence remains in the audit history.')
    return redirect('sale_detail',pk=p.sale_id)

@require_POST
@staff_required('reverse_sale')
def sale_reverse(request,pk):
    try: services.reverse_sale(pk,request.user,request.POST.get('reason',''))
    except ValidationError as error: error_messages(request,error)
    else: messages.success(request,'Sale reversed. Vehicle returned to pending review, not to public stock.')
    return redirect('sale_detail',pk=pk)

@require_POST
@staff_required('change_sale')
def handover(request,pk):
    sale=get_object_or_404(Sale,pk=pk,active=True)
    form=HandoverForm(request.POST,instance=sale)
    if form.is_valid(): form.save(); services.audit(request.user,'handover_updated',sale); messages.success(request,'Handover updated.')
    return redirect('sale_detail',pk=pk)

@staff_required('view_finance')
def reports(request):
    sales=Sale.objects.filter(active=True).select_related('vehicle','agent','buyer').prefetch_related('payments')
    start=parse_date(request.GET.get('start','')); end=parse_date(request.GET.get('end',''))
    if start: sales=sales.filter(sale_date__gte=start)
    if end: sales=sales.filter(sale_date__lte=end)
    if request.GET.get('currency'): sales=sales.filter(currency=request.GET['currency'])
    if request.GET.get('agent','').isdigit(): sales=sales.filter(agent_id=request.GET['agent'])
    if request.GET.get('vehicle'): sales=sales.filter(vehicle__stock_reference__icontains=request.GET['vehicle'])
    totals={}
    for sale in sales:
        t=totals.setdefault(sale.currency,{'currency':sale.currency,'sales':0,'value':Decimal(0),'discount':Decimal(0),'earned':Decimal(0),'collected':Decimal(0),'commission_due':Decimal(0),'settlement_due':Decimal(0)})
        b=sale.balances; t['sales']+=1; t['value']+=sale.amount; t['earned']+=sale.commission
        t['discount']+=sale.asking_price_at_sale-sale.amount
        for key in ['commission_due','settlement_due']: t[key]+=b[key]
        t['collected']+=b['commission_collected']
    if request.GET.get('export')=='csv':
        response=HttpResponse(content_type='text/csv'); response['Content-Disposition']='attachment; filename="sales-report.csv"'
        writer=csv.writer(response); writer.writerow(['Stock reference','Sale date','Currency','Sale price','Commission','Commission collected','Seller settlement due','Agent'])
        for s in sales:
            b=s.balances; writer.writerow([services.safe_csv(v) for v in [s.vehicle.stock_reference,s.sale_date,s.currency,s.amount,s.commission,b['commission_collected'],b['settlement_due'],s.agent.username]])
        services.audit(request.user,'report_export',SiteSettings.current(),{'start':str(start),'end':str(end),'rows':sales.count()})
        return response
    inventory=Vehicle.objects.values('status').annotate(total=Count('id')).order_by('status')
    stages=Enquiry.objects.values('stage').annotate(total=Count('id')).order_by('stage')
    sources=Enquiry.objects.values('source').annotate(total=Count('id')).order_by('-total')
    response_hours=[(e.first_contact_at-e.created_at).total_seconds()/3600 for e in Enquiry.objects.exclude(first_contact_at=None)]
    enquiry_total=Enquiry.objects.count()
    operations={'conversion':round(100*Enquiry.objects.filter(stage='won').count()/enquiry_total,1) if enquiry_total else 0,
        'response_hours':round(sum(response_hours)/len(response_hours),1) if response_hours else None,
        'response_sample':len(response_hours),'enquiry_total':enquiry_total}
    workloads=Enquiry.objects.exclude(stage__in=['won','closed']).values('assigned_to__username').annotate(total=Count('id')).order_by('-total')
    viewing_outcomes=Viewing.objects.values('status').annotate(total=Count('id')).order_by('status')
    return render(request,'staff/reports.html',{'totals':totals.values(),'inventory':inventory,'stages':stages,'sources':sources,
        'operations':operations,'workloads':workloads,'viewing_outcomes':viewing_outcomes,
        'aged':Vehicle.objects.filter(status='available',published_at__lt=timezone.now()-timedelta(days=60))[:20],
        'agents':get_user_model().objects.filter(is_staff=True),'currencies':Sale.objects.order_by().values_list('currency',flat=True).distinct()})

@staff_required('change_sitesettings')
def site_settings(request):
    form=SettingsForm(request.POST or None,instance=SiteSettings.current())
    if request.method=='POST' and form.is_valid():
        obj=form.save(); services.audit(request.user,'settings_updated',obj,{'fields':form.changed_data}); messages.success(request,'Website settings saved.'); return redirect('site_settings')
    return render(request,'staff/form.html',{'form':form,'title':'Website and business settings','submit':'Save settings','intro':'Only enter real business details and approved policies. Blank optional content is omitted from the public website.'})

@staff_required('view_auditevent')
def audit_history(request):
    qs=AuditEvent.objects.select_related('actor')
    if request.GET.get('q'): qs=qs.filter(Q(target__icontains=request.GET['q'])|Q(action__icontains=request.GET['q']))
    return render(request,'staff/audit.html',{'events':page(request,qs)})

@staff_required('view_notification')
def notifications(request): return render(request,'staff/notifications.html',{'notifications':page(request,Notification.objects.all())})

@require_POST
@staff_required('change_notification')
def notification_retry(request,pk):
    item=get_object_or_404(Notification,pk=pk)
    if item.state=='failed':
        item.state='pending'; item.next_attempt=timezone.now(); item.attempts=0; item.save()
        services.audit(request.user,'notification_retry',item)
    return redirect('notifications')

@staff_required()
def staff_users(request):
    if not request.user.is_superuser: raise PermissionDenied
    return render(request,'staff/users.html',{'users':get_user_model().objects.filter(is_staff=True).prefetch_related('groups'),'roles':Group.objects.all()})

class StaffCreateForm(OwnerForm):
    role=forms.ModelChoiceField(queryset=Group.objects.all(),required=True)

@staff_required()
def staff_add(request):
    if not request.user.is_superuser: raise PermissionDenied
    form=StaffCreateForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        u=form.save(commit=False); u.is_staff=True; u.save(); u.groups.add(form.cleaned_data['role'])
        services.audit(request.user,'staff_created',u,{'role':form.cleaned_data['role'].name})
        messages.success(request,'Staff account created. Share the initial password through a secure channel.'); return redirect('staff_users')
    return render(request,'staff/form.html',{'form':form,'title':'Add staff member','submit':'Create staff account'})

@require_POST
@staff_required()
def staff_update(request,pk):
    if not request.user.is_superuser: raise PermissionDenied
    user=get_object_or_404(get_user_model(),pk=pk,is_staff=True)
    if user.is_superuser: messages.error(request,'Owner accounts are managed through the owner recovery command.')
    elif request.POST.get('action')=='toggle':
        user.is_active=not user.is_active; user.save()
        if not user.is_active:
            from django.contrib.sessions.models import Session
            for session in Session.objects.filter(expire_date__gt=timezone.now()):
                if session.get_decoded().get('_auth_user_id')==str(user.pk): session.delete()
        services.audit(request.user,'staff_access_changed',user,{'active':user.is_active})
    elif request.POST.get('role'):
        group=get_object_or_404(Group,pk=request.POST['role']); user.groups.set([group]); services.audit(request.user,'staff_role_changed',user,{'role':group.name})
    return redirect('staff_users')
