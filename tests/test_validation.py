import copy
import unittest

from fpl_ai.errors import FPLValidationError
from fpl_ai.validation import validate_payloads
from tests.sample_data import bootstrap_payload, fixtures_payload


class ValidatePayloadsTests(unittest.TestCase):
    def test_accepts_usable_payloads(self) -> None:
        validate_payloads(bootstrap_payload(), fixtures_payload())

    def test_rejects_missing_required_player_field(self) -> None:
        bootstrap = bootstrap_payload()
        del bootstrap["elements"][0]["team"]

        with self.assertRaisesRegex(FPLValidationError, "missing fields: team"):
            validate_payloads(bootstrap, fixtures_payload())

    def test_rejects_duplicate_ids(self) -> None:
        bootstrap = bootstrap_payload()
        bootstrap["elements"].append(copy.deepcopy(bootstrap["elements"][0]))

        with self.assertRaisesRegex(FPLValidationError, "duplicate player id"):
            validate_payloads(bootstrap, fixtures_payload())

    def test_rejects_unknown_team_reference(self) -> None:
        bootstrap = bootstrap_payload()
        bootstrap["elements"][0]["team"] = 999

        with self.assertRaisesRegex(FPLValidationError, "unknown team 999"):
            validate_payloads(bootstrap, fixtures_payload())

    def test_empty_fixture_list_is_valid_between_seasons(self) -> None:
        validate_payloads(bootstrap_payload(), [])


if __name__ == "__main__":
    unittest.main()
