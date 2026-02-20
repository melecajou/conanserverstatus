import unittest
import threading
import sqlite3
import os
import time
from utils.database import execute_marketplace_purchase, initialize_global_db

class TestMarketplacePurchaseRace(unittest.TestCase):
    DB_PATH = "test_race_condition.db"

    def setUp(self):
        if os.path.exists(self.DB_PATH):
            os.remove(self.DB_PATH)
        initialize_global_db(self.DB_PATH)

        with sqlite3.connect(self.DB_PATH) as con:
            cur = con.cursor()
            # Create Seller (ID 1)
            cur.execute("INSERT INTO player_wallets (discord_id, balance) VALUES (1, 0)")
            # Create Buyer (ID 2) with enough money for two purchases
            cur.execute("INSERT INTO player_wallets (discord_id, balance) VALUES (2, 200)")
            # Create Listing (ID 1) - Item price 100
            cur.execute("""
                INSERT INTO market_listings (id, seller_discord_id, item_template_id, item_dna, price, status)
                VALUES (1, 1, 1001, '{}', 100, 'active')
            """)
            con.commit()

    def tearDown(self):
        if os.path.exists(self.DB_PATH):
            os.remove(self.DB_PATH)

    def test_concurrent_purchase(self):
        """Test that concurrent purchase attempts on the same listing do not result in double spending."""
        results = []

        def attempt_purchase():
            try:
                # We cannot easily force a sleep inside the function without mocking or patching,
                # but checking the result is valid.
                listing, error = execute_marketplace_purchase(2, 1, global_db_path=self.DB_PATH)
                if listing:
                    results.append("Success")
                else:
                    results.append(f"Failed: {error}")
            except Exception as e:
                results.append(f"Exception: {e}")

        threads = []
        # Launch 2 concurrent purchase attempts
        for _ in range(2):
            t = threading.Thread(target=attempt_purchase)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verify state
        with sqlite3.connect(self.DB_PATH) as con:
            cur = con.cursor()

            cur.execute("SELECT balance FROM player_wallets WHERE discord_id = 1") # Seller
            seller_bal = cur.fetchone()[0]

            cur.execute("SELECT balance FROM player_wallets WHERE discord_id = 2") # Buyer
            buyer_bal = cur.fetchone()[0]

            cur.execute("SELECT status FROM market_listings WHERE id = 1")
            status = cur.fetchone()[0]

        # Assertions
        # Seller should have 100 (one sale)
        self.assertEqual(seller_bal, 100, "Seller balance incorrect - possible double spend")

        # Buyer should have 100 (200 - 100)
        self.assertEqual(buyer_bal, 100, "Buyer balance incorrect - possible double spend")

        # Listing should be sold
        self.assertEqual(status, 'sold')

        # Results should have 1 Success and 1 Failure
        success_count = results.count("Success")
        failure_count = len([r for r in results if r.startswith("Failed")])

        self.assertEqual(success_count, 1, "Should have exactly one successful purchase")
        self.assertEqual(failure_count, 1, "Should have exactly one failed purchase")

if __name__ == "__main__":
    unittest.main()
