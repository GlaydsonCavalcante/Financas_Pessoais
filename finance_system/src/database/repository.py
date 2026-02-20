import pandas as pd
from src.database.connection import db_instance

class TransactionRepository:
    
    def get_base_income_for_year(self, year):
        """Retorna a Renda Base (Meta de Receita) para cálculo do Gap"""
        conn = db_instance.get_connection()
        cursor = conn.cursor()
        
        # Privilegia o planeamento anual para o orçamento
        cursor.execute("""
            SELECT SUM(valor_meta) FROM annual_budgets 
            WHERE ano = ? 
            AND (categoria LIKE '%Receita%' OR categoria LIKE '%Salário%' OR categoria LIKE '%Entrada%' OR categoria LIKE '%Rendimento%')
        """, (year,))
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row and row[0] else 0.0

    def get_budget_vs_real(self, year):
        """Traz todo o cenário do ano numa única chamada consolidada usando SQL puro onde possível"""
        conn = db_instance.get_connection()
        
        # Metas
        df_metas = pd.read_sql_query("SELECT categoria, valor_meta, is_locked FROM annual_budgets WHERE ano = ?", conn, params=(year,))
        
        # Realizado (YTD - Acumulado do Ano)
        df_real = pd.read_sql_query("""
            SELECT category as categoria, SUM(ABS(amount)) as realizado 
            FROM transactions 
            WHERE strftime('%Y', date) = ? AND amount < 0 AND category != '⛔ IGNORADO'
            GROUP BY category
        """, conn, params=(str(year),))
        
        # Guardado (Provisões)
        df_cofre = pd.read_sql_query("""
            SELECT categoria, SUM(valor) as guardado 
            FROM budget_provisions 
            WHERE strftime('%Y', data) = ? AND categoria != '⛔ IGNORADO'
            GROUP BY categoria
        """, conn, params=(str(year),))
        
        conn.close()
        
        # Unifica os dados
        df = pd.merge(df_metas, df_real, on='categoria', how='outer')
        df = pd.merge(df, df_cofre, on='categoria', how='outer')
        return df.fillna(0)

    def get_monthly_kpis(self, year, month):
        """Substitui o uso de Pandas nas rotas do dashboard por SQL otimizado"""
        conn = db_instance.get_connection()
        cursor = conn.cursor()
        month_str = f"{year}-{month:02d}"
        
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE strftime('%Y-%m', date) = ? AND amount > 0", (month_str,))
        inc = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT SUM(ABS(amount)) FROM transactions WHERE strftime('%Y-%m', date) = ? AND amount < 0 AND category != '⛔ IGNORADO'", (month_str,))
        exp = cursor.fetchone()[0] or 0.0
        
        conn.close()
        return {'income': inc, 'expenses': exp}
        
    def get_historical_category_trends(self, category):
        """Nova função para alimentar o gráfico do chat sem hardcoding de anos"""
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