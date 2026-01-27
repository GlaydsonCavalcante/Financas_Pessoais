import sqlite3
import pandas as pd
from datetime import date
import hashlib
import os  # <--- NOVA IMPORTAÇÃO NECESSÁRIA

class DatabaseManager:
    def __init__(self, db_path="data/finance.db"):
        self.db_path = db_path
        
        # --- BLOCO DE CORREÇÃO (BLINDAGEM) ---
        # Garante que a pasta onde o banco vai ficar existe.
        # Se não existir, o sistema cria.
        db_folder = os.path.dirname(self.db_path)
        if db_folder and not os.path.exists(db_folder):
            os.makedirs(db_folder, exist_ok=True)
        # -------------------------------------

        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Tabela de Transações
        c.execute('''CREATE TABLE IF NOT EXISTS transactions (
            hash_id TEXT PRIMARY KEY,
            date DATE,
            description TEXT,
            amount REAL,
            source_file TEXT,
            category TEXT,
            is_manual BOOLEAN DEFAULT 0
        )''')
        
        # Tabela de Regras
        c.execute('''CREATE TABLE IF NOT EXISTS classification_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_term TEXT UNIQUE,
            target_category TEXT,
            created_at DATE
        )''')
        
        conn.commit()
        conn.close()

    def save_transaction(self, t):
        conn = sqlite3.connect(self.db_path)
        
        # Gera Hash único
        raw_str = f"{t.date}{t.amount:.2f}{t.description.strip()}"
        hash_id = hashlib.md5(raw_str.encode()).hexdigest()
        
        try:
            conn.execute('''
                INSERT INTO transactions (hash_id, date, description, amount, source_file, category, is_manual)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (hash_id, t.date, t.description, t.amount, t.source_file, None, False))
            conn.commit()
            return True 
        except sqlite3.IntegrityError:
            return False 
        finally:
            conn.close()

    def get_pending_transactions(self):
        conn = sqlite3.connect(self.db_path)
        query = "SELECT * FROM transactions WHERE category IS NULL OR category = '' ORDER BY date DESC"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    
    def get_all_transactions(self):
        conn = sqlite3.connect(self.db_path)
        query = "SELECT * FROM transactions ORDER BY date DESC"
        df = pd.read_sql(query, conn)
        conn.close()
        return df

    def get_rules(self):
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql("SELECT * FROM classification_rules ORDER BY match_term", conn)
        conn.close()
        return df

    def add_rule(self, match_term, category):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute('''
                INSERT OR REPLACE INTO classification_rules (match_term, target_category, created_at)
                VALUES (?, ?, ?)
            ''', (match_term, category, date.today()))
            conn.commit()
        finally:
            conn.close()
            
    def delete_rule(self, match_term):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM classification_rules WHERE match_term = ?", (match_term,))
        conn.commit()
        conn.close()

    def update_transaction_category(self, hash_id, category, is_manual=False):
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            UPDATE transactions 
            SET category = ?, is_manual = ? 
            WHERE hash_id = ?
        ''', (category, is_manual, hash_id))
        conn.commit()
        conn.close()