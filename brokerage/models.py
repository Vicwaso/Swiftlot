import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

money = {'max_digits': 14, 'decimal_places': 2, 'validators': [MinValueValidator(0)]}
currency_validator = RegexValidator(r'^[A-Z]{3}$', 'Use a three-letter currency code, for example USD.')
def upload_path(instance, filename):
    return f'{"photos" if isinstance(instance, VehiclePhoto) else "private"}/{uuid.uuid4().hex}{__import__("pathlib").Path(filename).suffix.lower()}'

class Timestamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class SiteSettings(models.Model):
    business_name = models.CharField(max_length=120, default='Swiftlot')
    currency = models.CharField(max_length=3, blank=True, default='KES', validators=[currency_validator])
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True, default='0111506710')
    address = models.TextField(blank=True)
    opening_hours = models.TextField(blank=True)
    service_area = models.CharField(max_length=160, blank=True)
    about = models.TextField(blank=True)
    process = models.TextField(blank=True)
    privacy = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    notification_email = models.EmailField(blank=True)
    retention_days = models.PositiveIntegerField(default=730)
    facebook_url = models.URLField('Facebook', max_length=300, blank=True)
    instagram_url = models.URLField('Instagram', max_length=300, blank=True)
    tiktok_url = models.URLField('TikTok', max_length=300, blank=True)
    x_url = models.URLField('X', max_length=300, blank=True)
    youtube_url = models.URLField('YouTube', max_length=300, blank=True)
    linkedin_url = models.URLField('LinkedIn', max_length=300, blank=True)
    @property
    def social_links(self):
        return [(self._meta.get_field(field).verbose_name, getattr(self, field)) for field in
                ['facebook_url','instagram_url','tiktok_url','x_url','youtube_url','linkedin_url'] if getattr(self, field)]
    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]
    def __str__(self): return self.business_name

class Seller(Timestamped):
    name = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40)
    preferred_contact = models.CharField(max_length=20, choices=[('phone','Phone'),('email','Email')], default='phone')
    verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    notes = models.TextField(blank=True)
    def __str__(self): return self.name
    class Meta: ordering = ['name']

class VehicleQuerySet(models.QuerySet):
    def public(self): return self.filter(status='available')

class Vehicle(Timestamped):
    class Status(models.TextChoices):
        DRAFT='draft','Draft'
        REVIEW='review','Pending review'
        AVAILABLE='available','Available'
        RESERVED='reserved','Reserved'
        SOLD='sold','Sold'
        WITHDRAWN='withdrawn','Withdrawn'
        ARCHIVED='archived','Archived'
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="vehicles_added")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    stock_reference = models.CharField(max_length=30, unique=True)
    seller = models.ForeignKey(Seller, on_delete=models.PROTECT, related_name='vehicles')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, limit_choices_to={'is_staff':True,'is_active':True})
    make = models.CharField(max_length=60)
    model = models.CharField(max_length=80)
    variant = models.CharField(max_length=100, blank=True)
    year = models.PositiveSmallIntegerField(validators=[MinValueValidator(1900), MaxValueValidator(2100)])
    registration_year = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1900), MaxValueValidator(2100)])
    body_type = models.CharField(max_length=30, choices=[(x,x) for x in ['Saloon','SUV','Hatchback','Estate','Pickup','Van','Coupe','Convertible','Truck','Bus','Motorcycle','Other']])
    mileage = models.PositiveIntegerField()
    mileage_unit = models.CharField(max_length=5, choices=[('km','km'),('miles','miles')], default='km')
    fuel = models.CharField(max_length=20, choices=[(x,x) for x in ['Petrol','Diesel','Hybrid','Electric','Other']])
    transmission = models.CharField(max_length=20, choices=[(x,x) for x in ['Automatic','Manual','Other']])
    engine = models.CharField(max_length=100, blank=True, help_text='Engine capacity or battery and electric motor specification.')
    drive_type = models.CharField(max_length=40, blank=True)
    colour = models.CharField(max_length=40)
    seats = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    price = models.DecimalField(**money)
    currency = models.CharField(max_length=3, validators=[currency_validator])
    negotiable = models.BooleanField(default=False)
    location = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    features = models.TextField(blank=True, help_text='One feature per line.')
    condition = models.TextField(blank=True)
    known_defects = models.TextField(blank=True, help_text='Record known defects or state explicitly what has been disclosed.')
    service_history = models.TextField(blank=True)
    inspection_notes = models.TextField(blank=True)
    inspection_date = models.DateField(null=True, blank=True)
    accident_history = models.TextField(blank=True)
    ownership_info = models.TextField(blank=True)
    registration_number = models.CharField(max_length=40, blank=True)
    vin = models.CharField(max_length=60, null=True, blank=True, unique=True)
    seller_minimum = models.DecimalField(**money, null=True, blank=True)
    private_notes = models.TextField(blank=True)
    agreement_confirmed = models.BooleanField(default=False)
    agreement_start = models.DateField(null=True, blank=True)
    agreement_end = models.DateField(null=True, blank=True)
    fee_type = models.CharField(max_length=12, choices=[('fixed','Fixed amount'),('percent','Percentage of final sale price')], default='fixed')
    fee_value = models.DecimalField(**money, default=0)
    fee_payer = models.CharField(max_length=10, choices=[('seller','Seller'),('buyer','Buyer')], default='seller')
    fee_notes = models.TextField(blank=True, help_text='Include the agreed tax treatment. No tax is added automatically.')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    version = models.PositiveIntegerField(default=1)
    published_at = models.DateTimeField(null=True, blank=True)
    sold_at = models.DateTimeField(null=True, blank=True)
    objects = VehicleQuerySet.as_manager()
    class Meta:
        ordering = ['-created_at']
        permissions = [('publish_vehicle','Can publish vehicles'), ('close_sale','Can confirm sales'), ('reverse_sale','Can reverse sales'), ('view_finance','Can view financial reports')]
    def __str__(self): return f'{self.year} {self.make} {self.model}'
    @property
    def cover(self): return next(iter(self.photos.all()),None)

class VehiclePhoto(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to=upload_path)
    alt = models.CharField(max_length=180)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['position','id']

class PrivateDocument(Timestamped):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='documents')
    label = models.CharField(max_length=120)
    file = models.FileField(upload_to=upload_path)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    scanned_at = models.DateTimeField(null=True, blank=True)
    def __str__(self): return self.label

class Enquiry(Timestamped):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    submission_key = models.UUIDField(default=uuid.uuid4, unique=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, null=True, blank=True, related_name='enquiries')
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    preferred_contact = models.CharField(max_length=10, choices=[('email','Email'),('phone','Phone')], default='email')
    message = models.TextField(max_length=5000)
    privacy_consent = models.BooleanField(default=False)
    kind = models.CharField(max_length=12, choices=[('enquiry','Enquiry'),('viewing','Viewing request')], default='enquiry')
    requested_time = models.DateTimeField(null=True, blank=True)
    stage = models.CharField(max_length=20, choices=[(x,y) for x,y in [('new','New'),('contacted','Contacted'),('viewing_requested','Viewing requested'),('viewed','Viewing completed'),('negotiating','Negotiating'),('won','Won'),('closed','Closed without sale')]], default='new')
    source = models.CharField(max_length=40, default='Website')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', limit_choices_to={'is_staff':True,'is_active':True})
    next_action = models.CharField(max_length=240, blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True)
    first_contact_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    closure_reason = models.TextField(blank=True)
    needs_review = models.BooleanField(default=False)
    class Meta: ordering=['-created_at']
    def __str__(self): return f'{self.name} · {str(self.reference)[:8]}'

class Viewing(Timestamped):
    enquiry = models.ForeignKey(Enquiry, on_delete=models.PROTECT, related_name='viewings')
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, limit_choices_to={'is_staff':True,'is_active':True})
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    location = models.CharField(max_length=160)
    status = models.CharField(max_length=12, choices=[(x,x.title()) for x in ['requested','confirmed','completed','cancelled']], default='requested')
    outcome = models.TextField(blank=True)
    class Meta: ordering=['-starts_at']
    def __str__(self): return f'{self.enquiry.name} · {self.starts_at:%d %b %H:%M}'

class Task(Timestamped):
    title = models.CharField(max_length=180)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, limit_choices_to={'is_staff':True,'is_active':True})
    enquiry = models.ForeignKey(Enquiry, on_delete=models.PROTECT, null=True, blank=True)
    due_at = models.DateTimeField()
    done = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    class Meta: ordering=['done','due_at']
    def __str__(self): return self.title

class Offer(Timestamped):
    enquiry = models.ForeignKey(Enquiry, on_delete=models.PROTECT)
    amount = models.DecimalField(**money)
    currency = models.CharField(max_length=3, validators=[currency_validator])
    expires_at = models.DateTimeField(null=True, blank=True)
    decision = models.CharField(max_length=12, choices=[(x,x.title()) for x in ['pending','accepted','rejected','expired']], default='pending')
    notes = models.TextField(blank=True)
    def __str__(self): return f'{self.enquiry.name} · {self.currency} {self.amount}'

class Reservation(Timestamped):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='reservations')
    enquiry = models.ForeignKey(Enquiry, on_delete=models.PROTECT)
    expires_at = models.DateTimeField()
    deposit_reference = models.CharField(max_length=120, blank=True)
    conditions = models.TextField()
    active = models.BooleanField(default=True)
    reminded = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['vehicle'], condition=Q(active=True), name='one_active_reservation')]

class Sale(Timestamped):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='sales')
    buyer = models.ForeignKey(Enquiry, on_delete=models.PROTECT)
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    amount = models.DecimalField(**money)
    asking_price_at_sale = models.DecimalField(**money, default=0)
    currency = models.CharField(max_length=3, validators=[currency_validator])
    sale_date = models.DateField(default=timezone.localdate)
    evidence = models.TextField()
    fee_type = models.CharField(max_length=12)
    fee_value = models.DecimalField(**money)
    fee_payer = models.CharField(max_length=10)
    fee_notes = models.TextField(blank=True)
    commission = models.DecimalField(**money)
    handover = models.CharField(max_length=12, choices=[('pending','Pending'),('complete','Complete')], default='pending')
    handover_notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    reversal_reason = models.TextField(blank=True)
    class Meta:
        ordering=['-sale_date','-id']
        constraints=[models.UniqueConstraint(fields=['vehicle'],condition=Q(active=True),name='one_active_sale')]
    def __str__(self): return f'{self.vehicle.stock_reference} · {self.buyer.name}'
    @property
    def balances(self):
        entries = list(self.payments.filter(reversed=False))
        total=lambda kind: sum((e.amount for e in entries if e.kind==kind), Decimal('0'))
        received=total('proceeds')-total('refund')
        deductions=total('deduction')
        commission_held=total('commission_held')
        settled=total('settlement')
        collected=total('commission')+commission_held
        return {'received':received,'deductions':deductions,'settled':settled,
         'commission_collected':collected,'commission_due':self.commission-collected,
         'settlement_due':received-deductions-commission_held-settled}

class Payment(Timestamped):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='payments')
    kind = models.CharField(max_length=20, choices=[('proceeds','Vehicle proceeds received'),('refund','Vehicle proceeds refunded'),('commission','Commission received separately'),('commission_held','Commission retained from proceeds'),('deduction','Approved seller deduction'),('settlement','Seller settlement paid')])
    amount = models.DecimalField(max_digits=14,decimal_places=2,validators=[MinValueValidator(Decimal('0.01'))])
    date = models.DateField(default=timezone.localdate)
    method = models.CharField(max_length=60)
    reference = models.CharField(max_length=120)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    reversed = models.BooleanField(default=False)
    reversal_reason = models.TextField(blank=True)
    class Meta: ordering=['-date','-id']

class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=160)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']

class Notification(models.Model):
    subject = models.CharField(max_length=180)
    body = models.TextField()
    recipient = models.EmailField(blank=True)
    state = models.CharField(max_length=12, choices=[('pending','Pending'),('sent','Sent'),('failed','Failed'),('inapp','In app only')], default='pending')
    attempts = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=200, blank=True)
    next_attempt = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']

class StaffSecurity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    secret_encrypted = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)
    last_step = models.BigIntegerField(default=-1)

class RateLimit(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
