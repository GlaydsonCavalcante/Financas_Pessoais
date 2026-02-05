# src/services/budget_service.py
import pandas as pd
from datetime import date
from src.database.connection import db_instance

class BudgetService:
    def get_budget_summary(self, year):
        """
        Gera o relatório principal: Meta vs Realizado vs Guardado
        Retorna uma lista de dicionários pronta para o HTML.
        """
        conn = db_instance.get_connection()
        
        # 1. Busca Metas Definidas
        df_metas = pd.read_sql_query(f"SELECT categoria, valor_meta FROM annual_budgets WHERE ano = {year}", conn)
        
        # 2. Busca Realizado (Despesas do ano)
        # Atenção: Soma despesas (negativas) e inverte o sinal para positivo
        df_real = pd.read_sql_query(f"""
            SELECT category as categoria, SUM(ABS(amount)) as realizado 
            FROM transactions 
            WHERE strftime('%Y', date) = '{year}' AND amount < 0 
            GROUP BY category
        """, conn)
        
        # 3. Busca Guardado (Saldo do Cofre)
        # Soma tudo o que foi guardado (positivo) e retirado (negativo)
        df_cofre = pd.read_sql_query(f"""
            SELECT categoria, SUM(valor) as guardado 
            FROM budget_provisions 
            WHERE strftime('%Y', data) = '{year}'
            GROUP BY categoria
        """, conn)
        
        conn.close()
        
        # 4. Cruzamento de Dados (Merge)
        # Se não tiver meta, usa 0. Se não tiver gasto, usa 0.
        res = pd.merge(df_metas, df_real, on='categoria', how='outer').fillna(0)
        res = pd.merge(res, df_cofre, on='categoria', how='outer').fillna(0)
        
        # 5. Cálculos de Negócio (A Fórmula Mestra)
        today = date.today()
        months_left = 12 - today.month + 1 if year == today.year else 12
        if year < today.year: months_left = 1 # Evita divisão por zero no passado
        
        summary = []
        for _, row in res.iterrows():
            meta = row['valor_meta'] if 'valor_meta' in row else 0
            real = row['realizado']
            saved = row['guardado']
            
            # Quanto já cobrimos da meta?
            coberto = real + saved
            
            # Saldo a cobrir (Nunca negativo)
            falta = max(0, meta - coberto)
            
            # Cota Mensal Sugerida
            cota = falta / months_left if months_left > 0 else 0
            
            # Percentual para barra de progresso
            pct = (coberto / meta * 100) if meta > 0 else 0
            pct = min(100, pct) # Trava visual em 100%
            
            summary.append({
                'categoria': row['categoria'],
                'meta': meta,
                'realizado': real,
                'guardado': saved,
                'total_coberto': coberto,
                'falta': falta,
                'cota_mensal': cota,
                'pct': pct,
                'status_class': 'success' if pct >= 100 else 'warning' if pct > 80 else 'primary'
            })
            
        # Ordena: Maior meta primeiro
        return sorted(summary, key=lambda x: x['meta'], reverse=True)

    def set_annual_goal(self, year, category, amount):
        """Define ou atualiza a meta anual"""
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
        """Adiciona (ou remove se negativo) dinheiro do cofre"""
        if not date_str:
            date_str = date.today().strftime('%Y-%m-%d')
            
        conn = db_instance.get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO budget_provisions (data, categoria, valor, memo) VALUES (?, ?, ?, ?)",
                    (date_str, category, amount, memo))
        conn.commit()
        conn.close()