import pandas as pd
from datetime import date
from src.database.connection import db_instance
from src.database.repository import TransactionRepository

pd.set_option('future.no_silent_downcasting', True)

class BudgetService:
    def __init__(self):
        self.repository = TransactionRepository()
          
    # === 1. LÓGICA DO DASHBOARD (MENSAL / GPS) ===
    # ESTE MÉTODO ESTAVA FALTANDO E CAUSOU O ERRO
    def get_dashboard_overview(self, year=None, month=None):
        today = date.today()
        if not year: year = today.year
        if not month: month = today.month
        
        months_left = 13 - month
        if months_left < 1: months_left = 1 

        # --- BUSCA DADOS LIMPOS DO REPOSITÓRIO ---
        df_metas = self.repository.get_budget_vs_real(year) # Já traz Meta e Travas
        
        # Realizado YTD
        df_real_ytd = self.repository.get_expenses_by_category(year)
        df_real_ytd.rename(columns={'category': 'categoria', 'amount': 'realizado_acumulado'}, inplace=True)
        
        # Cofre YTD
        conn = db_instance.get_connection()
        df_cofre_ytd = pd.read_sql_query(f"""
            SELECT categoria, SUM(valor) as guardado_acumulado
            FROM budget_provisions 
            WHERE strftime('%Y', data) = '{year}' AND categoria != '⛔ IGNORADO'
            GROUP BY categoria
        """, conn)
        conn.close()

        # Mês Atual
        monthly_data = self.repository.get_monthly_breakdown(year, month)
        df_real_month = monthly_data['breakdown']
        df_real_month.rename(columns={'category': 'categoria', 'amount': 'realizado_mes'}, inplace=True)
        
        income_month = monthly_data['income']
        total_provisions_balance = self.repository.get_provisions_sum(year) # Total geral

        # --- PROCESSAMENTO ---
        # Unifica DataFrames (Garante que todas as categorias apareçam)
        df = pd.merge(df_metas, df_real_ytd, on='categoria', how='outer')
        df = pd.merge(df, df_cofre_ytd, on='categoria', how='outer')
        df = pd.merge(df, df_real_month, on='categoria', how='outer').fillna(0)

        overview_data = []
        total_quotas = 0
        safe_income = income_month if income_month > 0 else 1.0

        for _, row in df.iterrows():
            cat = row['categoria']
            if not cat: continue

            meta = row['valor_meta']
            real_ytd = row['realizado_acumulado']
            saved_ytd = row['guardado_acumulado']
            real_mes = row['realizado_mes']
            
            # AJUSTE MATEMÁTICO: 
            # O saldo para o cálculo da cota deve considerar o gasto ANTES deste mês
            # para projetar quanto você pode gastar AGORA.
            gasto_anterior = real_ytd - real_mes
            saldo_disponivel_para_o_ano = meta - (gasto_anterior + saved_ytd)
            
            if meta > 0:
                # Cota Mensal baseada no saldo que restava no início do mês
                cota_mensal = max(0, saldo_disponivel_para_o_ano / months_left)
            else:
                cota_mensal = real_mes
                
            total_quotas += cota_mensal
            
            visual_target = max(cota_mensal, real_mes) if cota_mensal > 0 else (real_mes if real_mes > 0 else 1)
            
            overview_data.append({
                'category': cat,
                'meta_anual': meta,
                'cota_mensal': int(cota_mensal),
                'realizado_mes': int(real_mes),
                'pct_paid': (real_mes / visual_target * 100),
                'impact': (real_mes / safe_income * 100),
                'is_alert': (real_mes > cota_mensal) and (meta > 0)
            })

        economic_result = income_month - total_quotas
        cash_burn = income_month - monthly_data['total_spent']

        return {
            'rows': sorted(overview_data, key=lambda x: x['realizado_mes'], reverse=True),
            'kpis': {
                'income': int(income_month),
                'total_quotas': int(total_quotas),
                'total_spent': int(monthly_data['total_spent']),
                'economic_result': int(economic_result),
                'cash_burn': int(cash_burn),
                'provisions_balance': int(total_provisions_balance)
            }
        }

    # === 2. LÓGICA DE METAS (ANUAL) ===
    def init_budget_from_history(self, target_year, base_year):
        df_base = self.repository.get_expenses_by_category(base_year)
        if df_base.empty: return 0
            
        conn = db_instance.get_connection()
        cursor = conn.cursor()
        count = 0
        for _, row in df_base.iterrows():
            cursor.execute("""
                INSERT INTO annual_budgets (ano, categoria, valor_meta, is_locked) 
                VALUES (?, ?, ?, 0)
                ON CONFLICT(ano, categoria) DO UPDATE SET valor_meta = excluded.valor_meta
            """, (target_year, row['category'], row['amount']))
            count += 1
        conn.commit()
        conn.close()
        return count

    def apply_curve(self, year, curve_type):
        financials = self.repository.get_year_financials(year) # Usa ano atual para renda
        net_income = financials['net_income']
        
        if net_income <= 0: return {"error": "Sem renda líquida registrada."}

        global_cap = net_income if curve_type == 1 else net_income * 0.90
        
        df_budget = self.repository.get_budget_vs_real(year)
        locked_total = df_budget[df_budget['is_locked'] == 1]['valor_meta'].sum()
        unlocked_df = df_budget[df_budget['is_locked'] == 0]
        unlocked_total = unlocked_df['valor_meta'].sum()
        
        available = global_cap - locked_total
        
        if available < 0:
            return {"error": f"Travas (R$ {locked_total:.0f}) já excedem o teto (R$ {global_cap:.0f})."}
            
        if unlocked_total > available and unlocked_total > 0:
            factor = available / unlocked_total
            conn = db_instance.get_connection()
            for _, row in unlocked_df.iterrows():
                new_val = row['valor_meta'] * factor
                conn.execute("UPDATE annual_budgets SET valor_meta = ? WHERE ano = ? AND categoria = ?", 
                            (new_val, year, row['categoria']))
            conn.commit()
            conn.close()
            return {"success": True}
        
        return {"success": True, "message": "Já está dentro da curva."}

    def get_budget_summary(self, year):
        # 1. Busca dados base e financeiros
        df = self.repository.get_budget_vs_real(year) #
        financials = self.repository.get_year_financials(year) #
        net_income = financials['net_income'] #
        
        # 2. Peso da categoria para distribuição proporcional da renda
        total_meta_atual = df['valor_meta'].sum() #
        
        summary = []
        today = date.today() #
        months_left = 13 - today.month if year == today.year else 1 #
        months_left = max(1, months_left) #

        for _, row in df.iterrows():
            if not row['categoria']: continue #
            
            meta_atual = row['valor_meta'] #
            total_coberto = row['realizado'] + row['guardado'] #
            
            # Cálculo das Curvas de Referência (Baseado na sua lógica de 100% e 90% da renda)
            peso = meta_atual / total_meta_atual if total_meta_atual > 0 else 0
            valor_curva_1 = net_income * peso  # Equilíbrio
            valor_curva_2 = (net_income * 0.90) * peso # Prosperidade
            
            summary.append({
                'categoria': row['categoria'],
                'meta': meta_atual,
                'realizado': row['realizado'],
                'guardado': row['guardado'],
                'is_locked': bool(row['is_locked']),
                'total_coberto': total_coberto,
                'saldo_restante': meta_atual - total_coberto,
                'curva_1': valor_curva_1,
                'curva_2': valor_curva_2,
                'cota_mensal': max(0, (meta_atual - total_coberto) / months_left)
            })
            
        return sorted(summary, key=lambda x: x['meta'], reverse=True) 

    def toggle_lock(self, year, category):
        conn = db_instance.get_connection()
        conn.execute("UPDATE annual_budgets SET is_locked = NOT is_locked WHERE ano = ? AND categoria = ?", (year, category))
        conn.commit()
        conn.close()
        
    def set_annual_goal(self, year, category, amount):
        conn = db_instance.get_connection()
        conn.execute("""
            INSERT INTO annual_budgets (ano, categoria, valor_meta) VALUES (?, ?, ?)
            ON CONFLICT(ano, categoria) DO UPDATE SET valor_meta = excluded.valor_meta
        """, (year, category, amount))
        conn.commit()
        conn.close()

    def add_provision(self, category, amount, memo, date_str=None):
        if not date_str: date_str = date.today().strftime('%Y-%m-%d')
        conn = db_instance.get_connection()
        conn.execute("INSERT INTO budget_provisions (data, categoria, valor, memo) VALUES (?, ?, ?, ?)",
                    (date_str, category, amount, memo))
        conn.commit()
        conn.close()