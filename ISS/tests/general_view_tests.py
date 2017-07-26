import datetime
import json

from django.conf import settings
from django.core import mail
from django.contrib.auth import authenticate
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from ISS.models import *
from ISS import utils
import test_utils

class GeneralViewTestCase(TestCase):
    def setUp(self):
        # Disable initial captcha period
        utils.get_config()['captcha_period'] = 0

        test_utils.create_std_forums()

        self.scrub = test_utils.create_user(thread_count=5, post_count=10)

        self.scrub_client = Client()
        self.scrub_client.force_login(self.scrub)


    def test_authed_users_can_access_index(self):
        path = reverse('forum-index')
        response = self.scrub_client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_unauthed_users_can_access_index(self):
        path = reverse('forum-index')
        anon_client = Client()
        response = anon_client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_index_has_categories(self):
        path = reverse('forum-index')
        response = self.scrub_client.get(path)
        self.assertEqual(len(response.context['categories']), 2)
        self.assertTrue(isinstance(response.context['forums_by_category'], dict))

    def test_threads_by_user(self):
        path = reverse('threads-by-user', kwargs={'user_id': self.scrub.pk})
        response = self.scrub_client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['threads']), 5)

    def test_user_profile_doesnt_error(self):
        path = reverse('user-profile', kwargs={'user_id': self.scrub.pk})
        response = self.scrub_client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_new_post(self):
        thread = Thread.objects.all()[0]
        path = reverse('new-reply', kwargs={'thread_id': thread.pk})
        post_count = self.scrub.get_post_count()
        response = self.scrub_client.post(path, {
            'content': 'P = NP?',
            'thread': thread.pk
        })
        self.assertEqual(self.scrub.get_post_count(), post_count + 1)

    def test_new_post_too_long(self):
        thread = Thread.objects.all()[0]
        path = reverse('new-reply', kwargs={'thread_id': thread.pk})
        post_count = self.scrub.get_post_count()
        response = self.scrub_client.post(path, {
            'content': 'P = NP?' * 3000,
            'thread': thread.pk
        })
        self.assertEqual(self.scrub.get_post_count(), post_count)

    def test_edit_post_too_long(self):
        post = self.scrub.post_set.all()[0]
        path = reverse('edit-post', kwargs={'post_id': post.pk})
        long_content = 'P = NP?' * 3000
        response = self.scrub_client.post(path, {
            'content': long_content,
            'post': post.pk
        })
        post = Post.objects.get(pk=post.pk)
        self.assertLess(len(post.content), len(long_content))

class ThanksViewTest(TestCase):
    def setUp(self):
        self.limit = utils.get_config()['initial_account_period_total'] = 3

        test_utils.create_std_forums()

        self.thankee = test_utils.create_user(thread_count=1, post_count=4)
        self.thanker = test_utils.create_user(post_count=4)
        self.noob_thanker = test_utils.create_user(post_count=1)

        self.thanker_client = Client()
        self.thanker_client.force_login(self.thanker)

        self.noob_thanker_client = Client()
        self.noob_thanker_client.force_login(self.noob_thanker)


        self.thankee_client = Client()
        self.thankee_client.force_login(self.thankee)

        self.url = reverse('thank-post',
                           args=(self.thankee.post_set.all()[0].pk,))

    def test_happy_path(self):
        resp = self.thanker_client.post(self.url)
        self.assertEqual(self.thankee.thanks_received.count(), 1)

    def test_can_not_thank_set(self):
        resp = self.thankee_client.post(self.url)
        self.assertEqual(self.thankee.thanks_received.count(), 0)

    def test_noobs_cant_thanksforce(self):
        resp = self.noob_thanker_client.post(self.url)
        self.assertEqual(self.thankee.thanks_received.count(), 0)

class PostFloodControlTestCase(TestCase):
    def setUp(self):
        test_utils.create_std_forums()
        self.scrub = test_utils.create_user(thread_count=1, post_count=0)
        self.thread = Thread.objects.get(author=self.scrub)
        self.scrub_client = Client()
        self.scrub_client.force_login(self.scrub)
        self.path = reverse('new-reply', args=(self.thread.pk,))
        self.limit = utils.get_config('initial_account_period_limit')

    def _attempt_new_post(self):
        prior_count = self.scrub.post_set.count()

        response = self.scrub_client.post(self.path, {
            'content': 'foobar!',
            'thread': self.thread.pk
        })

        return self.scrub.post_set.count() - prior_count

    def test_initial_account_period_compliance(self):
        # Post should be created
        self.assertEqual(self._attempt_new_post(), 1)

    def test_initial_account_period_violation(self):
        test_utils.create_posts(self.scrub, self.limit, bulk=True)
        # Post should be rejected
        self.assertEqual(self._attempt_new_post(), 0)

    def test_initial_account_period_violation_cooldown(self):
        test_utils.create_posts(self.scrub, self.limit, bulk=True)
        new_created = timezone.now() - utils.get_config(
                'initial_account_period_width')
        self.scrub.post_set.update(created=new_created)

        # Post should be created
        self.assertEqual(self._attempt_new_post(), 1)

    def test_initial_account_period_done(self):
        # Create enough posts to get us out of the initial period
        count = utils.get_config('initial_account_period_total')
        test_utils.create_posts(self.scrub, count + 1, bulk=True)

        self.assertEqual(self._attempt_new_post(), 1)

class ThreadActionTestCase(TestCase):
    def setUp(self):
        test_utils.create_std_forums()

        self.admin = test_utils.create_user()
        self.scrub = test_utils.create_user(thread_count=1, post_count=10)

        self.admin.is_admin = True
        self.admin.is_staff = True
        self.admin.save()

        self.thread = Thread.objects.all()[0]

        self.scrub_client = Client()
        self.scrub_client.force_login(self.scrub)
        self.admin_client = Client()
        self.admin_client.force_login(self.admin)

    def test_non_staff_may_not_delete_posts(self):
        path = reverse('thread-action', kwargs={'thread_id': self.thread.pk})
        response = self.scrub_client.post(path, {'action': 'delete-posts'})
        self.assertEqual(response.status_code, 403)

    def test_staff_may_delete_posts(self):
        path = reverse('thread-action', kwargs={'thread_id': self.thread.pk})
        posts_to_delete = self.thread.post_set.order_by('-created')[8:]

        response = self.admin_client.post(path, {
            'action': 'delete-posts',
            'post': [p.pk for p in posts_to_delete]
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.thread.post_set.count(), 8)

class AdminThreadCreationForum(TestCase):
    def setUp(self):
        test_utils.create_std_forums()

        self.admin = test_utils.create_user()
        self.scrub = test_utils.create_user()

        self.admin.is_admin = True
        self.admin.is_staff = True
        self.admin.save()

        self.admin_client = Client()
        self.admin_client.force_login(self.admin)
        self.scrub_client = Client()
        self.scrub_client.force_login(self.scrub)

        auth_package = AuthPackage.objects.create(
            logic_package='ADMIN_REQUIRED')

        self.admin_only_forum = Forum.objects.all()[0]
        self.admin_only_forum.create_thread_pack = auth_package
        self.admin_only_forum.save()

        self.limit = utils.get_config()['captcha_period'] = 0

    def test_admin_may_make_thread(self):
        path = reverse('new-thread',
                       kwargs={'forum_id': self.admin_only_forum.pk})
        response = self.admin_client.post(path, {
            'title': 'Presenting: Admin made thread',
            'content': 'by admins, for everyone.',
            'forum': str(self.admin_only_forum.pk)
        })
        self.assertEqual(response.status_code, 302)

    def test_scrub_may_not_make_thread(self):
        path = reverse('new-thread',
                       kwargs={'forum_id': self.admin_only_forum.pk})
        response = self.scrub_client.post(path, {
            'title': 'this shouldn\'t go through',
            'content': 'if you\'re reading this something has gone wrong.',
            'forum': str(self.admin_only_forum.pk)
        })
        self.assertEqual(response.status_code, 403)


class PasswordResetTestCase(TestCase):
    def setUp(self):
        self.franz = test_utils.create_user()
        self.franz.email = 'J.K@bank.gov'
        self.franz.save()
        
        self.franz_client = Client()
        self.franz_client.force_login(self.franz)

        self.issue_path = reverse('recovery-initiate')
        self.reset_path = reverse('recovery-reset')

    def tearDown(self):
        mail.outbox = []

    def _update_franz(self):
        self.franz = Poster.objects.get(pk=self.franz.pk)

    def _set_recovery_code(self):
        response = self.franz_client.post(self.issue_path, {
            'username': self.franz.username
        })

    def test_recovery_code_is_initially_null(self):
        self.assertEqual(self.franz.recovery_code, None)

    def test_get_recovery_page(self):
        response = self.franz_client.get(self.issue_path)
        self.assertEqual(response.status_code, 200)

    def test_invalid_email_addr(self):
        response = self.franz_client.post(self.issue_path, {
            'username': 'notarealusername'
        })
        self._update_franz()
        self.assertEqual(self.franz.recovery_code, None)

    def test_initiate(self):
        self._set_recovery_code()
        self._update_franz()
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotEqual(self.franz.recovery_code, None)

    def test_invalid_recovery_get(self):
        self._set_recovery_code()
        response = self.franz_client.get(self.reset_path + '?code=notauuid')
        self.assertEqual(response.status_code, 404)

    def test_valid_recovery_get(self):
        self._set_recovery_code()
        self._update_franz()
        response = self.franz_client.get(
            self.reset_path + '?code=' + self.franz.recovery_code)
        self.assertEqual(response.status_code, 200)

    def test_valid_recovery_post(self):
        self._set_recovery_code()
        self._update_franz()
        old_pass = self.franz.password

        response = self.franz_client.post(
            self.reset_path,
            {
                'password': 'justice',
                'password_repeat': 'justice',
                'code': self.franz.recovery_code
            })

        self._update_franz()
        new_pass = self.franz.password

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(new_pass, old_pass)
        self.assertEqual(self.franz.recovery_code, None)


    def test_invalid_recovery_post(self):
        self._set_recovery_code()
        self._update_franz()
        response = self.franz_client.post(
            self.reset_path,
            {
                'password': 'justice',
                'password_repeat': 'justice',
                'code': 'notauuid'
            })
        self._update_franz()
        self.assertNotEqual(self.franz.recovery_code, None)

    def test_expired_recovery_post(self):
        self._set_recovery_code()
        self._update_franz()
        self.franz.recovery_expiration = (
            timezone.now() - datetime.timedelta(seconds=30))
        self.franz.save()
        response = self.franz_client.post(
            self.reset_path,
            {
                'new_password': 'justice',
                'new_password_repeat': 'justice',
                'code': self.franz.recovery_code
            })
        self.assertEqual(response.status_code, 404)
