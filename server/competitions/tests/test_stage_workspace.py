from django.test import TestCase, override_settings
from django.urls import reverse

from competitions.admin_workspace import workspace_url
from competitions.tests import test_handoffs as fixtures


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class StageWorkspaceTests(TestCase):
    setUp = fixtures.HandoffTests.setUp
    _registration = fixtures.HandoffTests._registration
    _chain = fixtures.HandoffTests._chain
    _finish = fixtures.HandoffTests._finish

    def test_stage_context_survives_tabs_and_return_links(self):
        source, destination = self._chain()
        self.client.force_login(self.actor)
        base = reverse(
            "admin:competitions_competition_change", args=[self.competition.pk]
        )
        self.assertEqual(
            workspace_url(self.competition.pk, "standings", stage_id=destination.pk),
            f"{base}?tab=standings&stage={destination.pk}",
        )
        response = self.client.get(f"{base}?stage={destination.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data["stage"].pk, destination.pk)
        self.assertContains(response, "Waiting for previous stage")
        self.assertContains(response, f"?tab=setup&amp;stage={destination.pk}")
        self.assertEqual(self.client.get(f"{base}?stage=999999").status_code, 404)

    def test_publication_explains_lock_and_forged_early_handoff_is_rejected(self):
        source, destination = self._chain()
        self.client.force_login(self.actor)
        url = reverse(
            "admin:competitions_competition_publish_detail", args=[self.competition.pk]
        )
        response = self.client.get(f"{url}?stage={destination.pk}")
        self.assertContains(response, "whole stage plan")
        generate = reverse(
            "admin:competitions_stage_generate",
            args=[self.competition.pk, destination.pk],
        )
        response = self.client.post(
            generate, {"expected_revision": self.competition.revision, "regenerate": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(destination.draws.exists())
        self._finish(source)
        response = self.client.post(
            generate, {"expected_revision": self.competition.revision}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            workspace_url(self.competition.pk, "bracket", stage_id=destination.pk),
        )
