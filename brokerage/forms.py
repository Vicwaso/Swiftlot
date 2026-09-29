from decimal import Decimal
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import *

class StyledModelForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for f in self.fields.values():
            if isinstance(f,forms.DateTimeField): f.widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M')
            elif isinstance(f,forms.DateField): f.widget=forms.DateInput(attrs={'type':'date'})
            elif isinstance(f.widget,forms.Textarea): f.widget.attrs['rows']=3

class StaffLoginForm(AuthenticationForm):
    def confirm_login_allowed(self,user):
        super().confirm_login_allowed(user)
        if not user.is_staff: raise ValidationError('This sign-in is for authorised staff only.')

class OwnerForm(UserCreationForm):
    email=forms.EmailField(required=True)
    class Meta: model=get_user_model(); fields=['username','email','password1','password2']

class SellerForm(StyledModelForm):
    class Meta: model=Seller; fields=['name','email','phone','preferred_contact','verified','verification_notes','notes']
    def clean(self):
        data=super().clean()
        if data.get('verified') and not data.get('verification_notes'): self.add_error('verification_notes','Record the evidence checked before verifying this seller.')
        return data

class VehicleForm(StyledModelForm):
    version=forms.IntegerField(widget=forms.HiddenInput(),required=False)
    class Meta:
        model=Vehicle
        exclude=['public_id','status','published_at','sold_at','created_at','updated_at']
    def clean_vin(self): return self.cleaned_data.get('vin') or None
    def clean_currency(self): return self.cleaned_data['currency'].upper()
    def clean(self):
        d=super().clean()
        if d.get('agreement_start') and d.get('agreement_end') and d['agreement_end']<d['agreement_start']:
            self.add_error('agreement_end','End date must be on or after the start date.')
        if d.get('fee_type')=='percent' and d.get('fee_value',0)>100: self.add_error('fee_value','Percentage cannot exceed 100.')
        return d

class MultipleFileInput(forms.ClearableFileInput): allow_multiple_selected=True
class MultipleFileField(forms.FileField):
    def __init__(self,*args,**kwargs):
        kwargs.setdefault('widget',MultipleFileInput(attrs={'accept':'image/jpeg,image/png,image/webp'}))
        super().__init__(*args,**kwargs)
    def clean(self,data,initial=None):
        clean=super().clean
        if isinstance(data,(list,tuple)): return [clean(d,initial) for d in data]
        return [clean(data,initial)] if data else []

class PhotoUploadForm(forms.Form):
    photos=MultipleFileField()
    rights_confirmed=forms.BooleanField(label='These are genuine photos of this vehicle and I have permission to publish them.')
    def clean_photos(self):
        photos=self.cleaned_data['photos']
        if len(photos)>20: raise ValidationError('Upload up to 20 photos at a time.')
        return photos

class DocumentForm(StyledModelForm):
    class Meta: model=PrivateDocument; fields=['label','file']
    def clean_file(self):
        f=self.cleaned_data['file']
        if f.size>10*1024*1024: raise ValidationError('Documents must be 10 MB or smaller.')
        # PDF-only downloads are attachments and never rendered as HTML.
        if not f.name.lower().endswith('.pdf') or f.read(5)!=b'%PDF-': raise ValidationError('Upload a PDF document.')
        f.seek(0)
        from .scanning import scan_document
        f.scanned_at=scan_document(f)
        return f

class PublicEnquiryForm(StyledModelForm):
    website=forms.CharField(required=False,widget=forms.HiddenInput())
    submission_key=forms.UUIDField(widget=forms.HiddenInput())
    privacy_consent=forms.BooleanField(label='I agree that my details may be used to respond to this request.')
    class Meta:
        model=Enquiry
        fields=['name','email','phone','preferred_contact','kind','requested_time','message','privacy_consent','submission_key']
        labels={'kind':'Request type','requested_time':'Proposed viewing time'}
    def clean(self):
        d=super().clean()
        if d.get('website'): raise ValidationError('Unable to submit this request.')
        method=d.get('preferred_contact')
        if method and not d.get(method): self.add_error(method,'Enter details for your preferred contact method.')
        if d.get('kind')=='viewing' and not d.get('requested_time'): self.add_error('requested_time','Choose a proposed viewing time.')
        if d.get('requested_time') and d['requested_time']<=timezone.now(): self.add_error('requested_time','Choose a future time.')
        return d

class EnquiryForm(StyledModelForm):
    class Meta:
        model=Enquiry
        exclude=['reference','submission_key','created_at','updated_at','first_contact_at']
    def clean(self):
        d=super().clean()
        if not d.get('email') and not d.get('phone'): raise ValidationError('Provide a phone number or email address.')
        if self.instance.pk and Sale.objects.filter(buyer_id=self.instance.pk).exists():
            old=Enquiry.objects.get(pk=self.instance.pk)
            if d.get('vehicle')!=old.vehicle: self.add_error('vehicle','An enquiry linked to a sale cannot be moved to another vehicle.')
        return d

class ViewingForm(StyledModelForm):
    class Meta: model=Viewing; fields='__all__'
    def clean(self):
        d=super().clean(); start=d.get('starts_at'); end=d.get('ends_at'); agent=d.get('agent'); enquiry=d.get('enquiry')
        if start and end and end<=start: self.add_error('ends_at','End time must be after start time.')
        if d.get('status') in {'requested','confirmed'}:
            if enquiry and (not enquiry.vehicle or enquiry.vehicle.status not in {'available','reserved'}): raise ValidationError('The vehicle is no longer available for a viewing.')
            if agent and start and end and Viewing.objects.filter(agent=agent,status='confirmed',starts_at__lt=end,ends_at__gt=start).exclude(pk=self.instance.pk).exists(): raise ValidationError('This agent already has a confirmed viewing during that time.')
        return d

class TaskForm(StyledModelForm):
    class Meta: model=Task; fields='__all__'
class OfferForm(StyledModelForm):
    class Meta: model=Offer; fields='__all__'
    def clean(self):
        d=super().clean(); e=d.get('enquiry')
        if e and e.vehicle and d.get('currency')!=e.vehicle.currency: self.add_error('currency','Use the vehicle currency.')
        return d
class SettingsForm(StyledModelForm):
    class Meta: model=SiteSettings; exclude=[]
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for field in ['facebook_url','instagram_url','tiktok_url','x_url','youtube_url','linkedin_url']:
            self.fields[field]=forms.CharField(label=self.fields[field].label,required=False,max_length=300,
                help_text='Enter a profile URL or @handle. Leave blank to hide this link.' if field!='linkedin_url'
                else 'Enter your full LinkedIn profile or company URL. Leave blank to hide this link.')
    def clean(self):
        from .social import normalize_social_link
        data=super().clean()
        for field in ['facebook_url','instagram_url','tiktok_url','x_url','youtube_url','linkedin_url']:
            if field in data:
                try: data[field]=normalize_social_link(field,data[field])
                except ValidationError as error: self.add_error(field,error)
        return data
class ReserveForm(forms.Form):
    version=forms.IntegerField(widget=forms.HiddenInput())
    enquiry=forms.ModelChoiceField(queryset=Enquiry.objects.none())
    expires_at=forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type':'datetime-local'}))
    conditions=forms.CharField(widget=forms.Textarea(attrs={'rows':3}))
    deposit_reference=forms.CharField(max_length=120,required=False)
    def __init__(self,*args,vehicle,**kwargs):
        super().__init__(*args,**kwargs); self.fields['enquiry'].queryset=vehicle.enquiries.all()
class SaleForm(forms.Form):
    version=forms.IntegerField(widget=forms.HiddenInput())
    buyer=forms.ModelChoiceField(queryset=Enquiry.objects.none())
    amount=forms.DecimalField(min_value=Decimal('.01'),max_digits=14,decimal_places=2,label='Final sale price')
    sale_date=forms.DateField(widget=forms.DateInput(attrs={'type':'date'}),initial=timezone.localdate)
    evidence=forms.CharField(widget=forms.Textarea(attrs={'rows':3}),label='Sale confirmation evidence or documented exception')
    confirm=forms.BooleanField(label='Confirm sale and remove this vehicle from the consumer website.')
    def __init__(self,*args,vehicle,**kwargs):
        super().__init__(*args,**kwargs); self.fields['buyer'].queryset=vehicle.enquiries.all()
class PaymentForm(StyledModelForm):
    class Meta: model=Payment; fields=['kind','amount','date','method','reference','notes']
class HandoverForm(StyledModelForm):
    class Meta: model=Sale; fields=['handover','handover_notes']
