# Arquivo: setup_budget_db.py
# Salve na mesma pasta onde está o app.py
from src.database.connection import db_instance

def create_budget_tables():
    print("🔌 Conectando ao banco de dados...")
    conn = db_instance.get_connection()
    cursor = conn.cursor()
    
    print("🔨 Criando tabela 'annual_budgets'...")
    # 1. Tabela de Metas Anuais (Planejamento)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS annual_budgets (
            ano INTEGER,
            categoria TEXT,
            valor_meta REAL,
            PRIMARY KEY (ano, categoria)
        )
    """)
    
    print("🔨 Criando tabela 'budget_provisions'...")
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
    print("✅ Sucesso! Tabelas de Orçamento criadas.")

if __name__ == "__main__":
    create_budget_tables()