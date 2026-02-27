import pandas as pd
from src.database.connection import db_instance

class TransactionRepository:
    
    def __init__(self):
        # Auto-migração: Garante que a coluna is_revenue existe no banco de dados
        conn = db_instance.get_connection()
        try:
            conn.execute("ALTER TABLE annual_budgets ADD COLUMN is_revenue INTEGER DEFAULT 0")
            conn.commit()
        except Exception:
            pass # A coluna já existe, segue o jogo
        finally:
            conn.close()
            
    def get_base_income_for_year(self, year):
        conn = db_instance.get_connection()
        cursor = conn.cursor()
        # AGORA BUSCA APENAS O QUE VOCÊ MARCOU COMO RECEITA (is_revenue = 1)
        cursor.execute("SELECT SUM(valor_meta) FROM annual_budgets WHERE ano = ? AND is_revenue = 1", (str(year),))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else 0.0

    def get_budget_vs_real(self, year):
        conn = db_instance.get_connection()
        # AGORA PUXA A COLUNA is_revenue
        df_metas = pd.read_sql_query("SELECT categoria, valor_meta, is_locked, is_revenue FROM annual_budgets WHERE ano = ?", conn, params=(str(year),))
        
        df_real = pd.read_sql_query("""
            SELECT category as categoria, SUM(ABS(amount)) as realizado 
            FROM transactions 
            WHERE strftime('%Y', date) = ? AND category != '⛔ IGNORADO'
            GROUP BY category
        """, conn, params=(str(year),))
        
        df_cofre = pd.read_sql_query("""
            SELECT categoria, SUM(valor) as guardado 
            FROM budget_provisions 
            WHERE strftime('%Y', data) = ? AND categoria != '⛔ IGNORADO'
            GROUP BY categoria
        """, conn, params=(str(year),))
        conn.close()
        df = pd.merge(df_metas, df_real, on='categoria', how='outer')
        df = pd.merge(df, df_cofre, on='categoria', how='outer')
        # Preenche os vazios e garante que is_revenue seja 0 (Despesa) por padrão
        df['is_revenue'] = df['is_revenue'].fillna(0)
        return df.fillna(0)

    def get_monthly_breakdown(self, year, month):
        conn = db_instance.get_connection()
        month_str = f"{year}-{month:02d}"
        cursor = conn.cursor()
        
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE strftime('%Y-%m', date) = ? AND amount > 0 AND category != '⛔ IGNORADO'", (month_str,))
        income = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT SUM(ABS(amount)) FROM transactions WHERE strftime('%Y-%m', date) = ? AND amount < 0 AND category != '⛔ IGNORADO'", (month_str,))
        total_spent = cursor.fetchone()[0] or 0.0
        
        df_breakdown = pd.read_sql_query("""
            SELECT category as categoria, SUM(ABS(amount)) as realizado_mes 
            FROM transactions 
            WHERE strftime('%Y-%m', date) = ? AND amount < 0 AND category != '⛔ IGNORADO'
            GROUP BY category
        """, conn, params=(month_str,))
        conn.close()
        
        return {
            'income': income,
            'total_spent': total_spent,
            'breakdown': df_breakdown
        }

    def get_provisions_sum(self, year):
        conn = db_instance.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(valor) FROM budget_provisions WHERE strftime('%Y', data) = ? AND categoria != '⛔ IGNORADO'", (str(year),))
        val = cursor.fetchone()[0]
        conn.close()
        return val if val else 0.0
        
    def get_historical_category_trends(self, category):
        conn = db_instance.get_connection()
        df = pd.read_sql_query("""
            SELECT strftime('%Y', date) as ano, strftime('%m', date) as mes, SUM(ABS(amount)) as valor
            FROM transactions 
            WHERE category = ? AND amount < 0
            GROUP BY ano, mes
            ORDER BY ano, mes
        """, conn, params=(category,))
        conn.close()
        return df

    def get_expenses_by_category(self, year):
        conn = db_instance.get_connection()
        df = pd.read_sql_query("""
            SELECT category, SUM(ABS(amount)) as amount 
            FROM transactions 
            WHERE strftime('%Y', date) = ? AND amount < 0 AND category != '⛔ IGNORADO'
            GROUP BY category
        """, conn, params=(str(year),))
        conn.close()
        return df

    def get_income_by_category(self, year):
        conn = db_instance.get_connection()
        df = pd.read_sql_query("""
            SELECT category, SUM(amount) as amount 
            FROM transactions 
            WHERE strftime('%Y', date) = ? AND amount > 0 AND category != '⛔ IGNORADO'
            GROUP BY category
        """, conn, params=(str(year),))
        conn.close()
        return df
    
    def get_transactions_ledger(self, year, month, category=None):
        """Busca transações para o Extrato Analítico com filtros"""
        conn = db_instance.get_connection()
        query = """
            SELECT hash_id, date, description, amount, source, category 
            FROM transactions 
            WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
        """
        params = [str(year), f"{int(month):02d}"]
        
        if category:
            query += " AND category = ?"
            params.append(category)
            
        query += " ORDER BY date DESC"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df

    def update_transaction_category(self, hash_id, new_category):
        """Atualiza a categoria de uma transação específica"""
        conn = db_instance.get_connection()
        conn.execute("UPDATE transactions SET category = ? WHERE hash_id = ?", (new_category, hash_id))
        conn.commit()
        conn.close()

    def get_category_monthly_actuals(self, year, category):
        """Retorna os valores reais gastos/recebidos por mês para uma categoria."""
        conn = db_instance.get_connection()
        query = """
            SELECT strftime('%m', date) as mes, SUM(ABS(amount)) as total
            FROM transactions 
            WHERE strftime('%Y', date) = ? AND category = ?
            GROUP BY mes
            ORDER BY mes ASC
        """
        df = pd.read_sql_query(query, conn, params=(str(year), category))
        conn.close()
        
        # Garante uma lista de 12 meses (0 a 11)
        actuals = [0.0] * 12
        for _, row in df.iterrows():
            idx = int(row['mes']) - 1
            if 0 <= idx < 12:
                actuals[idx] = float(row['total'])
        return actuals
        
        # Converte para uma lista de 12 meses preenchida com zeros onde não houve gasto
        actuals = [0.0] * 12
        for _, row in df.iterrows():
            idx = int(row['mes']) - 1
            if 0 <= idx < 12:
                actuals[idx] = float(row['total'])
        return actuals