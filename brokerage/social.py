import re
from urllib.parse import urlsplit, urlunsplit
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

PLATFORMS={
    'facebook_url':('www.facebook.com','',{'facebook.com','www.facebook.com','m.facebook.com'}),
    'instagram_url':('www.instagram.com','',{'instagram.com','www.instagram.com'}),
    'tiktok_url':('www.tiktok.com','@',{'tiktok.com','www.tiktok.com'}),
    'x_url':('x.com','',{'x.com','www.x.com','twitter.com','www.twitter.com'}),
    'youtube_url':('www.youtube.com','@',{'youtube.com','www.youtube.com'}),
    'linkedin_url':('www.linkedin.com','in/',{'linkedin.com','www.linkedin.com'}),
}

def normalize_social_link(field,value):
    value=value.strip()
    if not value: return ''
    domain,prefix,allowed=PLATFORMS[field]
    if '://' not in value:
        if any(value.lower().startswith(host+'/') for host in allowed): value='https://'+value
        else:
            if field=='linkedin_url': raise ValidationError('Paste the full LinkedIn profile or company URL.')
            handle=value.removeprefix('@')
            if not re.fullmatch(r'[A-Za-z0-9_.-]+',handle): raise ValidationError('Enter a valid @handle or full profile URL.')
            value=f'https://{domain}/{prefix}{handle}'
    URLValidator(schemes=['http','https'])(value)
    parts=urlsplit(value)
    if parts.hostname not in allowed or parts.username or parts.password or parts.port:
        raise ValidationError('Use the official profile URL for this social platform.')
    if not parts.path.strip('/') or parts.path=='/@': raise ValidationError('Include your profile or handle in the URL.')
    return urlunsplit(('https',parts.netloc.lower(),parts.path,parts.query,''))
