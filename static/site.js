'use strict';
const filterDisclosure = document.querySelector('.filter-disclosure');
if (filterDisclosure && window.matchMedia('(max-width: 800px)').matches) filterDisclosure.open = false;
document.querySelectorAll('nav a').forEach(link => {
  if (new URL(link.href).pathname === location.pathname) link.setAttribute('aria-current', 'page');
});
const params = new URLSearchParams(location.search);
document.querySelectorAll('[data-filter-value]').forEach(option => {
  option.selected = params.get(option.dataset.filterValue) === option.value;
});
document.querySelectorAll('[data-gallery-src]').forEach(button => {
  button.addEventListener('click', () => {
    const main = document.getElementById('gallery-main');
    main.src = button.dataset.gallerySrc;
    main.alt = button.dataset.galleryAlt;
    document.querySelectorAll('[data-gallery-src]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
  });
});
if (location.pathname === '/') sessionStorage.setItem('stockReturn', location.pathname + location.search);
document.querySelectorAll('[data-back-to-stock]').forEach(link => {
  const saved = sessionStorage.getItem('stockReturn');
  if (saved && saved.startsWith('/?')) link.href = saved;
});
let refreshInFlight = false;
async function refreshAvailability() {
  if (document.hidden || refreshInFlight) return;
  const detail = document.querySelector('[data-detail-vehicle]');
  const items = [...document.querySelectorAll('[data-vehicle-id]')];
  const ids = detail ? [detail.dataset.detailVehicle] : items.map(item => item.dataset.vehicleId);
  if (!ids.length) return;
  refreshInFlight = true;
  try {
    const response = await fetch('/availability/?ids=' + encodeURIComponent(ids.join(',')), {cache:'no-store'});
    if (!response.ok) return;
    const data = await response.json();
    if (detail && !data.available.includes(detail.dataset.detailVehicle)) { location.reload(); return; }
    if (items.some(item => !data.available.includes(item.dataset.vehicleId))) location.reload();
  } catch (_) { /* The server rechecks stock before accepting any enquiry. */ }
  finally { refreshInFlight = false; }
}
setInterval(refreshAvailability, 25000);
window.addEventListener('focus', refreshAvailability);
window.addEventListener('pageshow', refreshAvailability);
document.querySelectorAll('[data-submit-form]').forEach(form => {
  form.addEventListener('submit', () => { form.querySelector('button[type="submit"], button:not([type])').disabled = true; });
});
document.querySelectorAll('[data-unsaved]').forEach(form => {
  let dirty = false;
  form.addEventListener('input', () => dirty = true);
  form.addEventListener('submit', () => dirty = false);
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
});
document.querySelectorAll('[data-upload-form]').forEach(form => {
  const input = form.querySelector('input[type=file]');
  const previews = form.querySelector('.upload-previews');
  let urls = [];
  input.addEventListener('change', () => {
    urls.forEach(URL.revokeObjectURL); urls = []; previews.replaceChildren();
    [...input.files].slice(0,20).forEach(file => {
      const image = document.createElement('img');
      const url = URL.createObjectURL(file); urls.push(url);
      image.src = url; image.alt = file.name; previews.append(image);
    });
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    const progress = form.querySelector('progress');
    const button = form.querySelector('button');
    progress.hidden = false; button.disabled = true;
    const xhr = new XMLHttpRequest();
    xhr.open('POST', form.action);
    xhr.upload.addEventListener('progress', event => { if(event.lengthComputable) progress.value = event.loaded / event.total * 100; });
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 400) {
        // Render the server response so validation messages are not lost to an extra GET.
        const parsed = new DOMParser().parseFromString(xhr.responseText,'text/html');
        const errors = parsed.querySelectorAll('.message.error');
        if (errors.length) {
          errors.forEach(error => previews.append(document.importNode(error,true)));
          button.disabled = false;
        } else location.href = xhr.responseURL || location.href;
      } else { previews.textContent = 'Upload could not be completed. Reload the page and try again.'; button.disabled = false; }
    });
    xhr.addEventListener('error', () => { previews.textContent = 'Connection interrupted. Reload to check whether the photos were saved.'; button.disabled = false; });
    xhr.send(new FormData(form));
  });
});
