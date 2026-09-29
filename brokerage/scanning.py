import socket
import struct
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

def scan_document(upload):
    """Send the file to an internal ClamAV daemon; never trust a browser MIME type."""
    if not settings.CLAMAV_HOST:
        if settings.DEBUG:
            return None
        raise ValidationError('Private PDF uploads are disabled until the malware scanner is configured.')
    try:
        with socket.create_connection((settings.CLAMAV_HOST, settings.CLAMAV_PORT),timeout=15) as client:
            client.sendall(b'zINSTREAM\x00')
            upload.seek(0)
            for chunk in upload.chunks(65536):
                client.sendall(struct.pack('!I',len(chunk))+chunk)
            client.sendall(struct.pack('!I',0))
            response=b''
            while len(response)<4096 and b'\x00' not in response:
                part=client.recv(1024)
                if not part: break
                response+=part
            if response.rstrip(b'\x00\n')!=b'stream: OK':
                raise ValidationError('This document failed the security scan and was not saved.')
    except (OSError,TimeoutError):
        raise ValidationError('The document scanner is unavailable. Try the upload again after it is restored.')
    finally:
        upload.seek(0)
    return timezone.now()
