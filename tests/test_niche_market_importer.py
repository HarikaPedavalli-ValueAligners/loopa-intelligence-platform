import os
import tempfile
import unittest

from agents.niche_market_importer import read_niche_file


class NicheMarketImporterTests(unittest.TestCase):
    def test_reads_csv_with_common_column_names(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as temp:
            temp.write("Industry,Sub Industry,Niche Market,NAICS Code,Geography,Notes\n")
            temp.write("Healthcare,Hospitals,Emergency Services,622110,US,HIPAA-heavy segment\n")
            path = temp.name

        try:
            records = read_niche_file(path)
        finally:
            os.unlink(path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["industry"], "Healthcare")
        self.assertEqual(records[0]["sub_industry"], "Hospitals")
        self.assertEqual(records[0]["sub_sub_industry"], "Emergency Services")
        self.assertEqual(records[0]["naics_code"], "622110")


if __name__ == "__main__":
    unittest.main()
