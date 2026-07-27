from django.test import SimpleTestCase

from quarm_reference.services.special_abilities import (
    crowd_control_summary,
    parse_special_abilities,
)


class SpecialAbilityTests(SimpleTestCase):
    def test_parser_handles_parameters(self):
        abilities = parse_special_abilities("3,1,13^12,1^37,1,10")

        self.assertEqual(abilities[0]["id"], 3)
        self.assertEqual(abilities[0]["parameters"], [13])
        self.assertEqual(abilities[1]["name"], "Immune to Slow")
        self.assertEqual(abilities[2]["parameters"], [10])

    def test_crowd_control_immunities(self):
        summary = crowd_control_summary("12,1^13,1^16,1", 50)

        self.assertTrue(summary["slow_immune"])
        self.assertTrue(summary["mez_immune"])
        self.assertTrue(summary["snare_immune"])

    def test_slow_mitigation_without_immunity(self):
        summary = crowd_control_summary("10,1", 35)

        self.assertFalse(summary["slow_immune"])
        self.assertEqual(summary["slow_mitigation_percent"], 35)
        self.assertIn("35%", summary["slow_status"])

    def test_disabled_immunity_is_not_active(self):
        summary = crowd_control_summary("12,0^13,0", 0)

        self.assertFalse(summary["slow_immune"])
        self.assertFalse(summary["mez_immune"])
