import pandas as pd
from datetime import date
from src.database.connection import db_instance
from src.database.repository import TransactionRepository

class BudgetService:
    def __init__(self):
        self.repository = TransactionRepository()

    def get_budget_summary(self, year):
        """
        Retorna o Plano Orçamental Completo:
        - Status Geral (Gap para as Curvas)
        - Categorias detalhadas com Cota Mensal Hidráulica
        """
        df = self.repository.get_budget_vs_real(year)
        renda_base_anual = self.repository.get_base_income_for_year(year)
        
        today = date.today()
        # Se for o ano atual, calcula meses restantes. Se for ano futuro, 12. Se passado, 1.
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
            if not cat or 'Receita' in cat or 'Salário' in cat: 
                continue # Ignoramos receitas no cálculo de cortes

            meta_anual = row['valor_meta']
            realizado_ytd = row['realizado']
            guardado_ytd = row['guardado']
            
            total_coberto = realizado_ytd + guardado_ytd
            saldo_restante_ano = meta_anual - total_coberto
            
            # CÁLCULO HIDRÁULICO: Ajusta o cinto pros meses seguintes
            cota_mensal_sugerida = max(0, saldo_restante_ano / months_left) if meta_anual > 0 else 0

            total_metas_despesas += meta_anual

            summary_categories.append({
                'categoria': cat,
                'meta': meta_anual,
                'realizado': realizado_ytd,
                'guardado': guardado_ytd,
                'is_locked': bool(row['is_locked']),
                'total_coberto': total_coberto,
                'saldo_restante': saldo_restante_ano,
                'cota_mensal': cota_mensal_sugerida
            })

        # CÁLCULO DO GAP (Feedback Loop)
        # Curva 1: 100% da Renda (Break-even)
        # Curva 2: 90% da Renda (Prosperidade)
        teto_c1 = renda_base_anual * 1.0
        teto_c2 = renda_base_anual * 0.9

        gap_c1 = teto_c1 - total_metas_despesas
        gap_c2 = teto_c2 - total_metas_despesas

        return {
            "status_geral": {
                "renda_base_anual": renda_base_anual,
                "total_metas_despesas": total_metas_despesas,
                "gap_curva_1": gap_c1, # Se negativo, precisa cortar X. Se positivo, tem folga.
                "gap_curva_2": gap_c2
            },
            "categorias": sorted(summary_categories, key=lambda x: x['meta'], reverse=True)
        }

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
        """Importa receitas e despesas como metas iniciais."""
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
        """Aplica redução proporcional apenas em DESPESAS, baseando-se na meta de receita."""
        financials = self.repository.get_year_financials(year)
        net_income = financials['net_income']
        
        if net_income <= 0:
            return {"error": "Sem renda definida (Meta ou Realizada)."}

        global_cap = net_income if curve_type == 1 else net_income * 0.90
        df_all = self.repository.get_budget_vs_real(year)
        
        # Filtra apenas DESPESAS (não reduzimos metas de receita)
        is_rev = df_all['categoria'].str.contains('Receita|Salário|Entrada|Rendimento', case=False, na=False)
        df_expenses = df_all[~is_rev]
        
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

pd.set_option('future.no_silent_downcasting', True)