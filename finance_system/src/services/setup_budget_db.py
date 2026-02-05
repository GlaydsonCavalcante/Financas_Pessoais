# Salve como: setup_budget_db.py
from src.database.connection import db_instance

def create_budget_tables():
    conn = db_instance.get_connection()
    cursor = conn.cursor()
    
    # 1. Tabela de Metas Anuais (Planejamento)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS annual_budgets (
            ano INTEGER,
            categoria TEXT,
            valor_meta REAL,
            PRIMARY KEY (ano, categoria)
        )
    """)
    
    # 2. Tabela de Cofre/Provisões (Execução)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budget_provisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            categoria TEXT,
            valor REAL,
            memo TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Tabelas de Orçamento criadas com sucesso!")

if __name__ == "__main__":
    create_budget_tables()