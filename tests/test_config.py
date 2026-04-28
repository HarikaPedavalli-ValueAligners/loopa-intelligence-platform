import unittest
from unittest.mock import patch

from config import get_database_url


class ConfigTests(unittest.TestCase):
    def test_production_azure_sql_url_uses_driver_18_security_defaults(self):
        env = {
            "ENVIRONMENT": "production",
            "AZURE_SQL_SERVER": "valuealigners.database.windows.net",
            "AZURE_SQL_DATABASE": "loopa-platform",
            "AZURE_SQL_USERNAME": "loopa_app",
            "AZURE_SQL_PASSWORD": "secret value",
        }

        with patch.dict("os.environ", env, clear=True):
            url = get_database_url()

        self.assertIn("valuealigners.database.windows.net:1433/loopa-platform", url)
        self.assertIn("driver=ODBC+Driver+18+for+SQL+Server", url)
        self.assertIn("Encrypt=yes", url)
        self.assertIn("TrustServerCertificate=no", url)


if __name__ == "__main__":
    unittest.main()
