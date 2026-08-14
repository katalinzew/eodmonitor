import os
import sys
import tempfile
import types
import unittest

sys.modules.setdefault("requests", types.SimpleNamespace())

import agent_eod


class AgentPostEodFilesTests(unittest.TestCase):
    def test_only_exact_file_names_are_reported(self):
        original_directory = agent_eod.POST_EOD_UPLOAD_DIR

        try:
            with tempfile.TemporaryDirectory() as directory:
                agent_eod.POST_EOD_UPLOAD_DIR = directory

                with open(os.path.join(directory, "fdn_mdp.old"), "wb") as handle:
                    handle.write(b"130826ignored")
                with open(os.path.join(directory, "vteplu"), "wb") as handle:
                    handle.write(b"")
                with open(os.path.join(directory, "vtesf"), "wb") as handle:
                    handle.write(b"")

                files = agent_eod.get_post_eod_files()

                self.assertFalse(files["fdn_mdp"]["exists"])
                self.assertTrue(files["vteplu"]["exists"])
                self.assertTrue(files["vtesf"]["exists"])
        finally:
            agent_eod.POST_EOD_UPLOAD_DIR = original_directory

    def test_fdn_prefix_reads_only_first_six_bytes(self):
        original_directory = agent_eod.POST_EOD_UPLOAD_DIR

        try:
            with tempfile.TemporaryDirectory() as directory:
                agent_eod.POST_EOD_UPLOAD_DIR = directory
                with open(os.path.join(directory, "fdn_mdp"), "wb") as handle:
                    handle.write(b"1308260000002173416502")

                files = agent_eod.get_post_eod_files()

                self.assertEqual("130826", files["fdn_mdp"]["date_prefix"])
        finally:
            agent_eod.POST_EOD_UPLOAD_DIR = original_directory


if __name__ == "__main__":
    unittest.main()
