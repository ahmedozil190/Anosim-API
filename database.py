import sqlite3
import os
from config import DB_PATH

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table for stored sessions (inventory)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE,
            session_name TEXT,
            api_id INTEGER,
            api_hash TEXT,
            first_name TEXT,
            last_name TEXT,
            proxy TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        )
    ''')
    
    # Table for order history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            booking_id INTEGER UNIQUE,
            phone_number TEXT,
            service TEXT,
            country TEXT,
            price_usd REAL,
            status TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Table for proxies
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proxy_url TEXT UNIQUE,
            status TEXT DEFAULT 'active',
            last_used DATETIME
        )
    ''')

    # Table for users and their settings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            language TEXT DEFAULT 'ar'
        )
    ''')

    conn.commit()
    conn.close()

def add_account(phone_number, session_name, api_id, api_hash, first_name, last_name, proxy=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO accounts (phone_number, session_name, api_id, api_hash, first_name, last_name, proxy)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (phone_number, session_name, api_id, api_hash, first_name, last_name, proxy))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_all_accounts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM accounts ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_language(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT language FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 'ar'

def set_user_language(user_id, language):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (user_id, language) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
    ''', (user_id, language))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
