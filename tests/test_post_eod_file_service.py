import datetime as dt
import unittest

from app.services.post_eod_file_service import (
    evaluate_post_eod_files,
    get_post_eod_email_due_at,
    should_run_post_eod_check,
)


class PostEodFileServiceTests(unittest.TestCase):
    def test_valid_files_pass_for_business_date(self):
        result = evaluate_post_eod_files(
            {
                "fdn_mdp": {"exists": True, "date_prefix": "130826"},
                "vteplu": {"exists": True},
                "vtesf": {"exists": True},
            },
            "2026-08-13",
        )

        self.assertTrue(result["passed"])
        self.assertEqual([], result["problems"])

    def test_missing_and_wrong_date_are_consolidated(self):
        result = evaluate_post_eod_files(
            {
                "fdn_mdp": {"exists": True, "date_prefix": "120826"},
                "vteplu": {"exists": False},
                "vtesf": {"exists": True},
            },
            "2026-08-13",
        )

        self.assertFalse(result["passed"])
        self.assertEqual(2, len(result["problems"]))
        self.assertIn("fdn_mdp", result["details"])
        self.assertIn("vteplu", result["details"])

    def test_check_runs_only_five_minutes_after_successful_eod(self):
        files = {"fdn_mdp": {}, "vteplu": {}, "vtesf": {}}
        completed_at = "2026-08-13 23:18:00"

        self.assertFalse(
            should_run_post_eod_check(
                "OK",
                "2026-08-13",
                completed_at,
                files,
                dt.datetime(2026, 8, 13, 23, 22, 59),
            )
        )
        self.assertTrue(
            should_run_post_eod_check(
                "OK",
                "2026-08-13",
                completed_at,
                files,
                dt.datetime(2026, 8, 13, 23, 23, 0),
            )
        )
        self.assertFalse(
            should_run_post_eod_check(
                "MISSING",
                "2026-08-13",
                completed_at,
                files,
                dt.datetime(2026, 8, 13, 23, 30, 0),
            )
        )

    def test_email_is_due_at_six_next_day(self):
        self.assertEqual(
            dt.datetime(2026, 8, 14, 6, 0, 0),
            get_post_eod_email_due_at("2026-08-13"),
        )


if __name__ == "__main__":
    unittest.main()
