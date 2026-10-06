import json
from urllib.parse import urlencode

from django import template
from django.conf import settings
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

register = template.Library()


@register.inclusion_tag('components/seo.html', takes_context=True)
def search_metadata(context):
    request = context['request']
    site = context['site']
    origin = settings.PUBLIC_ORIGIN.rstrip('/')
    path = request.path
    vehicle = context.get('vehicle')
    canonical = origin + path
    description = f'Browse available vehicles at {site.business_name}. View real photos, prices and specifications, and contact the brokerage.'
    title = f'Available vehicles · {site.business_name}'
    indexable = path == '/' or path == '/contact/' or path.startswith('/information/')
    if path == '/' and request.GET:
        indexable = not any(k != 'page' for k in request.GET)
        if request.GET.get('page', '').isdigit() and int(request.GET['page']) > 1:
            canonical += '?' + urlencode({'page': request.GET['page']})
    image = ''
    graph = []
    if vehicle and not context.get('preview') and vehicle.status == 'available':
        indexable = True
        title = f'{vehicle} for sale · {site.business_name}'
        description = f'{vehicle} in {vehicle.location}. {vehicle.currency} {vehicle.price:,.0f}. {vehicle.mileage:,} {vehicle.mileage_unit}, {vehicle.transmission}, {vehicle.fuel}. Enquire with {site.business_name}.'
        photos = context.get('photos', vehicle.photos.all())
        images = [origin + reverse('photo', args=[p.public_id]) for p in photos]
        image = images[0] if images else ''
        product = {'@type': ['Product', 'Vehicle'], 'name': str(vehicle), 'url': canonical,
                   'sku': vehicle.stock_reference, 'description': description,
                   'brand': {'@type': 'Brand', 'name': vehicle.make},
                   'model': vehicle.model, 'vehicleModelDate': str(vehicle.year),
                   'fuelType': vehicle.fuel, 'vehicleTransmission': vehicle.transmission,
                   'offers': {'@type': 'Offer', 'url': canonical,
                              'price': str(vehicle.price), 'priceCurrency': vehicle.currency,
                              'availability': 'https://schema.org/InStock'}}
        if images:
            product['image'] = images
        graph.append(product)
    elif path == '/contact/':
        title = f'Contact · {site.business_name}'
        description = f'Contact {site.business_name} about available vehicles, specifications and viewing arrangements.'
    elif path.startswith('/information/'):
        title = f'{context.get("title", "Information")} · {site.business_name}'
        description = strip_tags(str(context.get('content') or description))
    if indexable:
        organization = {'@type': 'Organization', '@id': origin + '/#organization',
                        'name': site.business_name, 'url': origin + '/'}
        if site.phone:
            organization['telephone'] = site.phone
        if site.email:
            organization['email'] = site.email
        if site.social_links:
            organization['sameAs'] = [url for _, url in site.social_links]
        graph.append(organization)
    encoded = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False)
    encoded = encoded.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return {'seo_title': title, 'seo_description': ' '.join(description.split())[:300],
            'seo_canonical': canonical, 'seo_image': image,
            'seo_robots': 'index, follow, max-image-preview:large' if indexable else 'noindex, nofollow',
            'seo_schema': mark_safe(encoded) if graph else '', 'seo_site_name': site.business_name}
