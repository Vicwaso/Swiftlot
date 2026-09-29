import base64
import hashlib
from functools import wraps
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))
def staff_required(permission=None):
    def deco(view):
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
            if not request.user.is_active or not request.user.is_staff: raise PermissionDenied
            if settings.MFA_REQUIRED and not request.session.get('mfa_verified'): return redirect('mfa')
            if permission and not request.user.has_perm('brokerage.'+permission): raise PermissionDenied
            return view(request,*args,**kwargs)
        return wrapped
    return deco
