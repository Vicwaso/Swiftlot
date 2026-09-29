from django.urls import path
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from . import views as v
from .security import staff_required
urlpatterns=[
 path('',v.inventory,name='inventory'),path('vehicles/<uuid:public_id>/',v.vehicle_detail,name='vehicle'),
 path('photos/<uuid:public_id>/',v.photo,name='photo'),path('availability/',v.availability,name='availability'),
 path('contact/',v.contact,name='contact'),path('request-received/',v.receipt,name='receipt'),
 path('information/<slug:slug>/',v.content_page,name='content'),path('sitemap.xml',v.sitemap,name='sitemap'),path('robots.txt',v.robots),
 path('staff/login/',v.staff_login,name='staff_login'),path('staff/logout/',v.staff_logout,name='staff_logout'),
 path('staff/setup/<str:token>/',v.setup_owner,name='setup_owner'),path('staff/security/',v.mfa,name='mfa'),path('staff/security/qr/',v.mfa_qr,name='mfa_qr'),
 path('staff/password/',staff_required()(PasswordChangeView.as_view(template_name='staff/password.html',success_url='/staff/password/done/')),name='password_change'),
 path('staff/password/done/',staff_required()(PasswordChangeDoneView.as_view(template_name='staff/password_done.html')),name='password_change_done'),
 path('staff/',v.dashboard,name='dashboard'),path('staff/vehicles/',v.staff_inventory,name='staff_inventory'),
 path('staff/vehicles/add/',v.vehicle_edit,name='vehicle_add'),path('staff/vehicles/<int:pk>/',v.staff_vehicle,name='staff_vehicle'),
 path('staff/vehicles/<int:pk>/edit/',v.vehicle_edit,name='vehicle_edit'),path('staff/vehicles/<int:pk>/action/',v.vehicle_action,name='vehicle_action'),
 path('staff/vehicles/<int:pk>/preview/',v.vehicle_preview,name='vehicle_preview'),path('staff/vehicles/<int:pk>/photos/',v.photos_upload,name='photos_upload'),
 path('staff/vehicles/<int:pk>/photo-order/',v.photos_update,name='photos_update'),path('staff/vehicles/<int:pk>/documents/',v.document_upload,name='document_upload'),
 path('files/<int:pk>/',v.document_download,name='document_download'),path('staff/vehicles/<int:pk>/reserve/',v.vehicle_reserve,name='vehicle_reserve'),
 path('staff/reservations/<int:pk>/release/',v.reservation_release,name='reservation_release'),path('staff/vehicles/<int:pk>/sell/',v.vehicle_sell,name='vehicle_sell'),
 path('staff/records/<slug:kind>/',v.record_list,name='record_list'),path('staff/records/<slug:kind>/add/',v.record_edit,name='record_add'),path('staff/records/<slug:kind>/<int:pk>/',v.record_edit,name='record_edit'),
 path('staff/sales/',v.sales_list,name='sales_list'),path('staff/sales/<int:pk>/',v.sale_detail,name='sale_detail'),
 path('staff/sales/<int:pk>/payment/',v.payment_add,name='payment_add'),path('staff/payments/<int:pk>/reverse/',v.payment_reverse,name='payment_reverse'),
 path('staff/sales/<int:pk>/reverse/',v.sale_reverse,name='sale_reverse'),path('staff/sales/<int:pk>/handover/',v.handover,name='handover'),
 path('staff/reports/',v.reports,name='reports'),path('staff/settings/',v.site_settings,name='site_settings'),path('staff/audit/',v.audit_history,name='audit_history'),
 path('staff/notifications/',v.notifications,name='notifications'),path('staff/notifications/<int:pk>/retry/',v.notification_retry,name='notification_retry'),
 path('staff/users/',v.staff_users,name='staff_users'),path('staff/users/add/',v.staff_add,name='staff_add'),path('staff/users/<int:pk>/update/',v.staff_update,name='staff_update'),
]
