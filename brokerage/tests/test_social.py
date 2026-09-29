from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from brokerage.forms import SettingsForm
from brokerage.models import SiteSettings
from brokerage.social import normalize_social_link

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class SocialSettingsTests(TestCase):
    def test_settings_accept_handles_and_show_only_saved_links(self):
        site=SiteSettings.current()
        form=SettingsForm({'business_name':'Swiftlot','currency':'KES','retention_days':730,
            'instagram_url':'@swiftlot_test','linkedin_url':'https://www.linkedin.com/company/swiftlot-test/'},instance=site)
        self.assertTrue(form.is_valid(),form.errors)
        form.save()
        response=self.client.get('/')
        self.assertContains(response,'https://www.instagram.com/swiftlot_test')
        self.assertContains(response,'https://www.linkedin.com/company/swiftlot-test/')
        self.assertNotContains(response,'facebook.com')
        self.assertContains(self.client.get('/contact/'),'Find us on social media')
    def test_invalid_platform_and_unsafe_urls_rejected(self):
        for value in ['javascript:alert(1)','https://instagram.com.evil.example/profile','https://example.com/profile','https://user:pass@instagram.com/profile','https://instagram.com/']:
            with self.subTest(value=value),self.assertRaises(ValidationError): normalize_social_link('instagram_url',value)
        self.assertEqual(normalize_social_link('tiktok_url','@swiftlot'),'https://www.tiktok.com/@swiftlot')
        self.assertEqual(normalize_social_link('x_url','x.com/swiftlot'),'https://x.com/swiftlot')
    def test_theme_controls_render_without_invented_profiles(self):
        for path in ['/','/contact/','/staff/login/']:
            response=self.client.get(path)
            self.assertContains(response,'data-theme-toggle')
            self.assertContains(response,'theme.js')
        self.assertNotContains(self.client.get('/'),'aria-label="Swiftlot social media"')
