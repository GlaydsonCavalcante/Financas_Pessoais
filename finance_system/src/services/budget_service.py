import pandas as pd
from datetime import date
from src.database.connection import db_instance
from src.database.repository import TransactionRepository

pd.set_option('future.no_silent_downcasting', True)

class BudgetService:
    def __init__(self):
        self.repository = TransactionRepository()

    def get_dashboard_overview(self, year=None, month=None):
        today = date.today()
        if not year: year = today.year
        if not month: month = today.month
        
        months_left = 13 - month
        if months_left < 1: months_left = 1 

        df_ytd = self.repository.get_budget_vs_real(year)
        monthly_data = self.repository.get_monthly_breakdown(year, month)
        df_real_month = monthly_data['breakdown']
        
        income_month = monthly_data['income']
        total_provisions_balance = self.repository.get_provisions_sum(year)

        if not df_real_month.empty:
            df = pd.merge(df_ytd, df_real_month, on='categoria', how='outer').fillna(0)
        else:
            df = df_ytd.copy()
            df['realizado_mes'] = 0.0

        overview_data = []
        total_quotas = 0
        safe_income = income_month if income_month > 0 else 1.0

        for _, row in df.iterrows():
            cat = row.get('categoria')
            # FIM DO HARDCODE NO GPS MENSAL: Só ignora se is_revenue for 1
            is_revenue = bool(row.get('is_revenue', 0))
            if not cat or pd.isna(cat) or is_revenue: 
                continue

            meta = row.get('valor_meta', 0)
            real_ytd = row.get('realizado', 0)
            saved_ytd = row.get('guardado', 0)
            real_mes = row.get('realizado_mes', 0)
            
            gasto_anterior = real_ytd - real_mes
            saldo_disponivel_para_o_ano = meta - (gasto_anterior + saved_ytd)
            
            if meta > 0:
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

    def get_budget_summary(self, year):
        df = self.repository.get_budget_vs_real(year)
        renda_base_anual = self.repository.get_base_income_for_year(year)
        
        today = date.today()
        if year == today.year:
            months_left = max(1, 13 - today.month)
        elif year > today.year:
            months_left = 12
        else:
            months_left = 1

        summary_categories = []
        total_metas_despesas = 0

        for _, row in df.iterrows():
            cat = row['categoria']
            if not cat or pd.isna(cat): 
                continue

            # FIM DO HARDCODE NO PAINEL ANUAL: Lê do banco de dados!
            is_revenue = bool(row.get('is_revenue', 0))

            meta_anual = row['valor_meta']
            realizado_ytd = row['realizado']
            guardado_ytd = row['guardado']
            
            total_coberto = realizado_ytd + guardado_ytd
            saldo_restante_ano = meta_anual - total_coberto
            
            cota_mensal_sugerida = max(0, saldo_restante_ano / months_left) if meta_anual > 0 else 0

            if not is_revenue:
                total_metas_despesas += meta_anual

            summary_categories.append({
                'categoria': cat,
                'meta': meta_anual,
                'realizado': realizado_ytd,
                'guardado': guardado_ytd,
                'is_locked': bool(row['is_locked']),
                'total_coberto': total_coberto,
                'saldo_restante': saldo_restante_ano,
                'cota_mensal': cota_mensal_sugerida,
                'is_revenue': is_revenue 
            })

        teto_c1 = renda_base_anual * 1.0
        teto_c2 = renda_base_anual * 0.9
        gap_c1 = teto_c1 - total_metas_despesas
        gap_c2 = teto_c2 - total_metas_despesas

        return {
            "status_geral": {
                "renda_base_anual": renda_base_anual,
                "total_metas_despesas": total_metas_despesas,
                "gap_curva_1": gap_c1,
                "gap_curva_2": gap_c2
            },
            "categorias": sorted(summary_categories, key=lambda x: x['meta'], reverse=True)
        }

    # === NOVAS FUNÇÕES DE CLASSIFICAÇÃO ===
    def toggle_revenue(self, year, category):
        """Inverte o status: Despesa vira Receita e vice-versa"""
        conn = db_instance.get_connection()
        conn.execute("UPDATE annual_budgets SET is_revenue = NOT is_revenue WHERE ano = ? AND categoria = ?", (year, category))
        conn.commit()
        conn.close()

    # (Mantenha o resto das funções: apply_curve, init_budget_from_history, toggle_lock, set_annual_goal, add_provision intactas do anterior...)
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

    def init_budget_from_history(self, target_year, base_year):
        df_expenses = self.repository.get_expenses_by_category(base_year)
        df_income = self.repository.get_income_by_category(base_year)
        df_base = pd.concat([df_expenses, df_income])
        
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
        net_income = self.repository.get_base_income_for_year(year)
        
        if net_income <= 0:
            return {"error": "Sem renda definida (Meta) para calcular o corte."}

        global_cap = net_income if curve_type == 1 else net_income * 0.90
        df_all = self.repository.get_budget_vs_real(year)
        
        # O corte aplica-se a tudo o que não for receita (is_revenue == 0)
        df_expenses = df_all[df_all['is_revenue'] == 0]
        
        locked_total = df_expenses[df_expenses['is_locked'] == 1]['valor_meta'].sum()
        unlocked_df = df_expenses[df_expenses['is_locked'] == 0]
        unlocked_total = unlocked_df['valor_meta'].sum()
        
        available = global_cap - locked_total
        
        if available < 0:
            return {"error": f"Gastos fixos (R$ {locked_total:.0f}) excedem o teto (R$ {global_cap:.0f})."}
            
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
        
        return {"success": True, "message": "Orçamento já está dentro da curva."}