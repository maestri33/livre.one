from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from djstripe.enums import SubscriptionStatus
from djstripe.models import Subscription, Customer

from apps.teams.models import Team, Membership
from apps.teams.roles import ROLE_ADMIN
from apps.users.models import CustomUser


class TeamBillingUpdateTest(TestCase):
    def test_default_value(self):
        before = timezone.now()
        team = Team.objects.create(name="My Team", slug="my_team")
        after = timezone.now()
        self.assertTrue(before < team.billing_details_last_changed < after)

    def test_add_membership_via_model_updates_value(self):
        team = Team.objects.create(name="My Team", slug="my_team")
        before = timezone.now()
        user = CustomUser.objects.create(username="alice@example.com")
        Membership.objects.create(team=team, user=user, role=ROLE_ADMIN)
        team.refresh_from_db()
        self.assertTrue(before < team.billing_details_last_changed)

    def test_add_membership_via_m2m_updates_value(self):
        team = Team.objects.create(name="My Team", slug="my_team")
        before = timezone.now()
        user = CustomUser.objects.create(username="alice@example.com")
        team.members.add(user, through_defaults={"role": ROLE_ADMIN})
        team.refresh_from_db()
        self.assertTrue(before < team.billing_details_last_changed)

    def test_removing_membership_via_model_updates_value(self):
        team = Team.objects.create(name="My Team", slug="my_team")
        user = CustomUser.objects.create(username="alice@example.com")
        team.members.add(user, through_defaults={"role": ROLE_ADMIN})
        previous_value = team.billing_details_last_changed
        membership = Membership.objects.get(team=team, user=user)
        membership.delete()
        team.refresh_from_db()
        self.assertTrue(previous_value < team.billing_details_last_changed)

    def test_removing_membership_via_m2m_updates_value(self):
        team = Team.objects.create(name="My Team", slug="my_team")
        user = CustomUser.objects.create(username="alice@example.com")
        team.members.add(user, through_defaults={"role": ROLE_ADMIN})
        previous_value = team.billing_details_last_changed
        team.members.remove(user)
        team.refresh_from_db()
        self.assertTrue(previous_value < team.billing_details_last_changed)

    def test_removing_membership_via_user_m2m_fails(self):
        team = Team.objects.create(name="My Team", slug="my_team")
        user = CustomUser.objects.create(username="alice@example.com")
        team.members.add(user, through_defaults={"role": ROLE_ADMIN})
        with self.assertRaises(Exception):
            user.teams.remove(team)

    def test_need_to_sync(self):
        team = Team.objects.create(name="My Team", slug="my_team")

        # initially no need to sync
        self.assertEqual(0, Team.get_items_needing_sync().count())

        # add active subscription and dates, and ensure needs to sync
        customer = Customer.objects.create()
        team.subscription = Subscription.objects.create(
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
            customer_id=customer.id,
            status=SubscriptionStatus.active,
        )
        team.billing_details_last_changed = timezone.now()
        team.save()
        self.assertEqual(1, Team.get_items_needing_sync().count())

        # set sync date and no need anymore
        team.last_synced_with_stripe = timezone.now()
        team.save()
        self.assertEqual(0, Team.get_items_needing_sync().count())

        # update billing date and need to sync again
        team.billing_details_last_changed = timezone.now()
        team.save()
        self.assertEqual(1, Team.get_items_needing_sync().count())

        # change subscription status and no need
        team.subscription.status = SubscriptionStatus.canceled
        team.subscription.save()
        self.assertEqual(0, Team.get_items_needing_sync().count())

        # remove subscription and no need
        team.subscription = None
        team.save()
        self.assertEqual(0, Team.get_items_needing_sync().count())
