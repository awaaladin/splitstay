from django.test import TestCase, override_settings


@override_settings(CRON_SECRET="s3cret")
class CronEndpointTests(TestCase):
    def test_rejects_missing_or_wrong_secret(self):
        self.assertEqual(self.client.get("/api/cron/enforce-deadlines/").status_code, 403)
        res = self.client.get("/api/cron/enforce-deadlines/", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(res.status_code, 403)

    def test_refuses_everything_when_no_secret_configured(self):
        with override_settings(CRON_SECRET=""):
            res = self.client.get("/api/cron/enforce-deadlines/", HTTP_AUTHORIZATION="Bearer ")
        self.assertEqual(res.status_code, 403)

    def test_runs_each_scheduled_task(self):
        for name in ("enforce-deadlines", "spawn-recurring-cycles", "send-due-reminders", "reconcile-pending-payouts"):
            res = self.client.get(f"/api/cron/{name}/", HTTP_AUTHORIZATION="Bearer s3cret")
            self.assertEqual(res.status_code, 200, name)
            self.assertEqual(res.json()["result"], 0)

    def test_unknown_task_404(self):
        res = self.client.get("/api/cron/nope/", HTTP_AUTHORIZATION="Bearer s3cret")
        self.assertEqual(res.status_code, 404)

    def test_post_not_allowed(self):
        self.assertEqual(self.client.post("/api/cron/enforce-deadlines/", HTTP_AUTHORIZATION="Bearer s3cret").status_code, 405)
