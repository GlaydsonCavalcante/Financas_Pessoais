import pandas as pd
from src.database.connection import db_instance

class TransactionRepository:
    """
    Guardião dos Dados (Single Source of Truth).
    """
    
    def get_year_financials(self, year):
        conn = db_instance.get_connection()
        query = f"""
            SELECT date, amount, category 
            FROM transactions 
            WHERE strftime('%Y', date) = '{year}' 
            AND (category != '⛔ IGNORADO' OR category IS NULL)
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return {'net_income': 0.0, 'real_expenses': 0.0, 'raw_df': pd.DataFrame()}

        # Saneamento
        is_revenue_cat = df['category'].str.contains('Receita|Salário|Entrada|Rendimento', case=False, na=False)
        
        # Receita Líquida (Soma tudo de receita, positivo ou negativo)
        net_income = df[is_revenue_cat]['amount'].sum()
        
        # Despesa Real (Soma negativos que não são receita)
        expenses_df = df[~is_revenue_cat & (df['amount'] < 0)].copy()
        expenses_df['amount'] = expenses_df['amount'].abs()
        real_expenses = expenses_df['amount'].sum()

        return {
            'net_income': net_income,
            'real_expenses': real_expenses,
            'raw_df': df,
            'expenses_df': expenses_df,
            'income_df': df[is_revenue_cat]
        }

    def get_monthly_breakdown(self, year, month):
        """Retorna os dados focados em um mês específico para o GPS."""
        financials = self.get_year_financials(year)
        
        # Se não tem dados no ano, retorna zerado
        if financials['raw_df'].empty:
            return {'income': 0.0, 'total_spent': 0.0, 'breakdown': pd.DataFrame()}

        month_str = f"{year}-{month:02d}"
        
        # 1. Renda do Mês
        inc_df = financials['income_df'].copy()
        if not inc_df.empty:
            inc_df['mes'] = pd.to_datetime(inc_df['date']).dt.strftime('%Y-%m')
            monthly_income = inc_df[inc_df['mes'] == month_str]['amount'].sum()
        else:
            monthly_income = 0.0
            
        # 2. Despesas do Mês
        exp_df = financials['expenses_df'].copy()
        total_spent = 0.0
        breakdown = pd.DataFrame()

        if not exp_df.empty:
            exp_df['mes'] = pd.to_datetime(exp_df['date']).dt.strftime('%Y-%m')
            monthly_expenses = exp_df[exp_df['mes'] == month_str]
            total_spent = monthly_expenses['amount'].sum()
            
            # Agrupa por categoria para o detalhe
            breakdown = monthly_expenses.groupby('category')['amount'].sum().reset_index()
            
        return {
            'income': monthly_income,
            'total_spent': total_spent,
            'breakdown': breakdown
        }

    def get_expenses_by_category(self, year):
        """Retorna acumulado do ano por categoria (YTD)."""
        financials = self.get_year_financials(year)
        exp_df = financials['expenses_df']
        
        if exp_df.empty:
            return pd.DataFrame(columns=['category', 'amount'])
            
        return exp_df.groupby('category')['amount'].sum().reset_index()

    def get_budget_vs_real(self, year):
        conn = db_instance.get_connection()
        # Metas
        df_metas = pd.read_sql_query(f"SELECT categoria, valor_meta, is_locked FROM annual_budgets WHERE ano = {year}", conn)
        # Realizado
        df_real = self.get_expenses_by_category(year)
        df_real.rename(columns={'category': 'categoria', 'amount': 'realizado'}, inplace=True)
        # Guardado
        df_cofre = pd.read_sql_query(f"""
            SELECT categoria, SUM(valor) as guardado 
            FROM budget_provisions 
            WHERE strftime('%Y', data) = '{year}' AND categoria != '⛔ IGNORADO'
            GROUP BY categoria
        """, conn)
        conn.close()
        
        df = pd.merge(df_metas, df_real, on='categoria', how='outer')
        df = pd.merge(df, df_cofre, on='categoria', how='outer')
        return df.fillna(0)

    def get_provisions_sum(self, year):
        """Total geral guardado no cofre."""
        conn = db_instance.get_connection()
        val = pd.read_sql_query(f"""
            SELECT SUM(valor) FROM budget_provisions 
            WHERE strftime('%Y', data) = '{year}' AND categoria != '⛔ IGNORADO'
        """, conn).iloc[0,0]
        conn.close()
        return val if val else 0.0