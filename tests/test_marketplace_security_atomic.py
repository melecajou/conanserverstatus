import pytest
import sqlite3
import os
from utils.database import execute_marketplace_purchase, initialize_global_db

@pytest.fixture
def db_path(tmp_path):
    db = tmp_path / "test_global.db"
    initialize_global_db(str(db))
    return str(db)

def test_execute_marketplace_purchase_success(db_path):
    # Setup
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        # Create buyer with 1000 coins
        cur.execute("INSERT INTO player_wallets (discord_id, balance) VALUES (111, 1000)")
        # Create seller
        cur.execute("INSERT INTO player_wallets (discord_id, balance) VALUES (222, 0)")
        # Create listing for 500 coins
        cur.execute("INSERT INTO market_listings (seller_discord_id, item_template_id, item_dna, price, status) VALUES (222, 500, '{}', 500, 'active')")
        listing_id = cur.lastrowid
        con.commit()

    # Execute
    listing, error = execute_marketplace_purchase(111, listing_id, global_db_path=db_path)

    # Verify
    assert error is None
    assert listing is not None
    assert listing['price'] == 500

    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        # Buyer should have 500 left
        cur.execute("SELECT balance FROM player_wallets WHERE discord_id = 111")
        assert cur.fetchone()[0] == 500
        # Seller should have 500
        cur.execute("SELECT balance FROM player_wallets WHERE discord_id = 222")
        assert cur.fetchone()[0] == 500
        # Listing should be sold
        cur.execute("SELECT status FROM market_listings WHERE id = ?", (listing_id,))
        assert cur.fetchone()[0] == 'sold'

def test_execute_marketplace_purchase_insufficient_funds(db_path):
    # Setup
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        # Create buyer with 100 coins
        cur.execute("INSERT INTO player_wallets (discord_id, balance) VALUES (111, 100)")
        # Create listing for 500 coins
        cur.execute("INSERT INTO market_listings (seller_discord_id, item_template_id, item_dna, price, status) VALUES (222, 500, '{}', 500, 'active')")
        listing_id = cur.lastrowid
        con.commit()

    # Execute
    listing, error = execute_marketplace_purchase(111, listing_id, global_db_path=db_path)

    # Verify
    assert listing is None
    assert error == "Insufficient funds."

    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        # Buyer balance should not have changed
        cur.execute("SELECT balance FROM player_wallets WHERE discord_id = 111")
        assert cur.fetchone()[0] == 100
        # Listing should still be active
        cur.execute("SELECT status FROM market_listings WHERE id = ?", (listing_id,))
        assert cur.fetchone()[0] == 'active'

def test_execute_marketplace_purchase_already_sold(db_path):
    # Setup
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute("INSERT INTO player_wallets (discord_id, balance) VALUES (111, 1000)")
        cur.execute("INSERT INTO market_listings (seller_discord_id, item_template_id, item_dna, price, status) VALUES (222, 500, '{}', 500, 'sold')")
        listing_id = cur.lastrowid
        con.commit()

    # Execute
    listing, error = execute_marketplace_purchase(111, listing_id, global_db_path=db_path)

    # Verify
    assert listing is None
    assert error == "Listing not found or already sold."
