from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from tournaments.models import Tournament
from tournaments.payment_content import (
    render_transfer_content,
    snapshot_transfer_template,
)


class TransferTemplateTests(SimpleTestCase):
    def test_admin_rejects_unsupported_placeholders_and_invalid_limits(self):
        for template in (
            "{reference}",
            "{participant.__class__}",
            "{participant!r}",
            "{participant:10}",
            "{",
            "   ",
        ):
            with self.subTest(template=template), self.assertRaises(ValidationError):
                Tournament(
                    name="Event", slug="event", transfer_content_template=template
                ).full_clean(validate_unique=False, validate_constraints=False)
        for limit in (0, 151):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                Tournament(
                    name="Event", slug="event", transfer_content_limit=limit
                ).full_clean(validate_unique=False, validate_constraints=False)

    def test_static_template_and_literal_braces_are_preserved(self):
        template = snapshot_transfer_template(
            "{{Fees}} {tournament_name} {participant}", "Đấu {Cup}"
        )
        self.assertEqual(
            render_transfer_content(template, "Đặng", 100), "{Fees} Dau {Cup} Dang"
        )
        self.assertEqual(
            render_transfer_content("Chuyển  tiền\ncho giải", "", 100),
            "Chuyen tien cho giai",
        )
