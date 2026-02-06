import unittest
import sqlite3
import os
from utils.database import (
    initialize_global_db,
    prepare_withdrawal_transaction,
    complete_withdrawal_transaction,
    update_player_balance
)

class TestDatabaseWithdrawal(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_global_registry.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        initialize_global_db(self.db_path)
        
        # Setup a test user with balance
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("INSERT INTO player_wallets (discord_id, balance) VALUES (?, ?)", (12345, 1000))
            con.commit()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_prepare_withdrawal_success(self):
        tx_id = prepare_withdrawal_transaction(12345, 100, "CharName", "ServerName", global_db_path=self.db_path)
        self.assertIsNotNone(tx_id)
        
        # Check balance deducted
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT balance FROM player_wallets WHERE discord_id = ?", (12345,))
            balance = cur.fetchone()[0]
            self.assertEqual(balance, 900)
            
            # Check transaction record
            cur.execute("SELECT * FROM withdraw_transactions WHERE id = ?", (tx_id,))
            row = cur.fetchone()
            self.assertEqual(row[1], 12345) # discord_id
            self.assertEqual(row[2], 100)   # amount
            self.assertEqual(row[3], "CharName")
            self.assertEqual(row[4], "ServerName")
            self.assertEqual(row[5], "PENDING")

    def test_prepare_withdrawal_insufficient_funds(self):
        tx_id = prepare_withdrawal_transaction(12345, 1100, "CharName", "ServerName", global_db_path=self.db_path)
        self.assertIsNone(tx_id)
        
        # Check balance NOT deducted
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT balance FROM player_wallets WHERE discord_id = ?", (12345,))
            balance = cur.fetchone()[0]
            self.assertEqual(balance, 1000)

    def test_complete_withdrawal_transaction(self):
        tx_id = prepare_withdrawal_transaction(12345, 100, "CharName", "ServerName", global_db_path=self.db_path)
        success = complete_withdrawal_transaction(tx_id, "COMPLETED", global_db_path=self.db_path)
        self.assertTrue(success)
        
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT status FROM withdraw_transactions WHERE id = ?", (tx_id,))
            status = cur.fetchone()[0]
            self.assertEqual(status, "COMPLETED")

if __name__ == "__main__":
    unittest.main()
