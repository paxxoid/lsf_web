from django.test import SimpleTestCase

from quarm_reference.services.names import (
    display_npc_name,
    normalize_npc_name,
    stored_npc_name_variants,
)


class NPCNameTests(SimpleTestCase):
    def test_display_name_is_normalized_for_lookup(self):
        self.assertEqual(normalize_npc_name("Aten Ha Ra"), "Aten_Ha_Ra")

    def test_multiple_separators_are_collapsed(self):
        self.assertEqual(
            normalize_npc_name("Aten__Ha   Ra"),
            "Aten_Ha_Ra",
        )

    def test_database_marker_is_hidden_for_display(self):
        self.assertEqual(
            display_npc_name("#Lord_Nagafen"),
            "Lord Nagafen",
        )

    def test_lookup_supports_database_marker(self):
        self.assertEqual(
            stored_npc_name_variants("#Lord Nagafen"),
            ("Lord_Nagafen", "#Lord_Nagafen"),
        )
