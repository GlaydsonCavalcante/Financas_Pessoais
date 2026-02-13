import pandas as pd
from datetime import date
from src.database.connection import db_instance

class BudgetService:
    
    def get_dashboard_overview(self, year=None, month=None):
        """
        Gera os dados para o Dashboard (GPS Financeiro).
        Agora inclui análise de impacto na renda (Análise Vertical).
        """
        today = date.today()
        if not year: year = today.year
        if not month: month = today.month
        
        months_left = 13 - month
        if months_left < 1: months_left = 1 

        conn = db_instance.get_connection()
        
        # 1. Metas
        df_metas = pd.read_sql_query(f"SELECT categoria, valor_meta FROM annual_budgets WHERE ano = {year}", conn)
        
        # 2. Realizado YTD
        df_real_ytd = pd.read_sql_query(f"""
            SELECT category as categoria, SUM(ABS(amount)) as realizado_acumulado
            FROM transactions 
            WHERE strftime('%Y', date) = '{year}' AND amount < 0 
            GROUP BY category
        """, conn)

        # 3. Provisões YTD
        df_cofre_ytd = pd.read_sql_query(f"""
            SELECT categoria, SUM(valor) as guardado_acumulado
            FROM budget_provisions 
            WHERE strftime('%Y', data) = '{year}'
            GROUP BY categoria
        """, conn)

        # 4. Realizado Mês Atual
        df_real_month = pd.read_sql_query(f"""
            SELECT category as categoria, SUM(ABS(amount)) as realizado_mes
            FROM transactions 
            WHERE strftime('%Y', date) = '{year}' AND strftime('%m', date) = '{month:02d}' AND amount < 0
            GROUP BY category
        """, conn)
        
        # 5. Renda do Mês (CRUCIAL PARA A ANÁLISE VERTICAL)
        income_month = pd.read_sql_query(f"""
            SELECT SUM(amount) FROM transactions 
            WHERE strftime('%Y', date) = '{year}' AND strftime('%m', date) = '{month:02d}' AND amount > 0
        """, conn).iloc[0,0] or 0.0

        # 6. Saldo Provisões Total
        total_provisions_balance = pd.read_sql_query("SELECT SUM(valor) FROM budget_provisions", conn).iloc[0,0] or 0.0

        conn.close()

        # --- PROCESSAMENTO ---
        df = pd.merge(df_metas, df_real_ytd, on='categoria', how='outer').fillna(0)
        df = pd.merge(df, df_cofre_ytd, on='categoria', how='outer').fillna(0)
        df = pd.merge(df, df_real_month, on='categoria', how='outer').fillna(0)

        overview_data = []
        total_quotas = 0
        total_spent_month = 0
        
        # Evita divisão por zero
        safe_income = income_month if income_month > 0 else 1.0

        for _, row in df.iterrows():
            cat = row['categoria']
            if not cat: continue

            meta = row['valor_meta']
            real_ytd = row['realizado_acumulado']
            saved_ytd = row['guardado_acumulado']
            real_mes = row['realizado_mes']
            
            total_spent_month += real_mes

            remaining_goal = meta - (real_ytd + saved_ytd)
            
            if meta > 0:
                cota_mensal = max(0, remaining_goal / months_left)
                status = "Planejado"
            else:
                cota_mensal = real_mes
                status = "Não Planejado"

            total_quotas += cota_mensal
            
            visual_target = max(cota_mensal, real_mes) if cota_mensal > 0 else (real_mes if real_mes > 0 else 1)
            pct_paid = (real_mes / visual_target * 100)
            
            # NOVO: Impacto na Renda (Regra 50/30/20)
            impact_on_income = (real_mes / safe_income * 100)
            
            overview_data.append({
                'category': cat,
                'meta_anual': meta,
                'cota_mensal': int(cota_mensal),
                'realizado_mes': int(real_mes),
                'pct_paid': pct_paid,
                'impact': impact_on_income, # % da renda que foi para isso
                'is_alert': (real_mes > cota_mensal) and (meta > 0)
            })

        # Ordena por quem gasta mais (Princípio de Pareto) - Mostra os ofensores primeiro
        sorted_rows = sorted(overview_data, key=lambda x: x['realizado_mes'], reverse=True)

        economic_result = income_month - total_quotas
        cash_burn = income_month - total_spent_month # Queima de Caixa Real (Entrada - Saída Real)

        return {
            'rows': sorted_rows,
            'kpis': {
                'income': int(income_month),
                'total_quotas': int(total_quotas),
                'total_spent': int(total_spent_month), # Total gasto no mês
                'economic_result': int(economic_result),
                'cash_burn': int(cash_burn), # Novo KPI de Sobrevivência
                'provisions_balance': int(total_provisions_balance)
            }
        }

    # --- MÉTODOS DE SUPORTE ---
    def set_annual_goal(self, year, category, amount):
        conn = db_instance.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO annual_budgets (ano, categoria, valor_meta) 
            VALUES (?, ?, ?)
            ON CONFLICT(ano, categoria) DO UPDATE SET valor_meta = excluded.valor_meta
        """, (year, category, amount))
        conn.commit()
        conn.close()

    def add_provision(self, category, amount, memo, date_str=None):
        if not date_str: date_str = date.today().strftime('%Y-%m-%d')
        conn = db_instance.get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO budget_provisions (data, categoria, valor, memo) VALUES (?, ?, ?, ?)",
                    (date_str, category, amount, memo))
        conn.commit()
        conn.close()
        
    def get_budget_summary(self, year):
        # Mantido para compatibilidade
        return self.get_dashboard_overview(year)['rows'] # Simplificação segura