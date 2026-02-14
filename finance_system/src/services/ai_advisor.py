import os
import time
import google.generativeai as genai
import pandas as pd
from dotenv import load_dotenv
from src.database.connection import db_instance

load_dotenv() 

class AIAdvisor:
    def __init__(self):
        load_dotenv() 
        api_key = os.getenv("GEMINI_API_KEY")
        # Carrega o modelo definido no seu .env
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        
        if not api_key:
            self.model = None
        else:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name)

    def get_category_context(self, category):
        """Busca lançamentos detalhados (Data, Descrição, Valor) para análise profunda."""
        conn = db_instance.get_connection()
        query = """
            SELECT date as data, description as descricao, ABS(amount) as valor
            FROM transactions 
            WHERE category = ? 
            AND strftime('%Y', date) IN ('2024', '2025', '2026')
            AND amount < 0
            ORDER BY date DESC
        """
        df = pd.read_sql_query(query, conn, params=(category,))
        
        meta = pd.read_sql_query(
            "SELECT valor_meta FROM annual_budgets WHERE categoria = ? AND ano = 2026", 
            conn, params=(category,)
        )
        meta_val = meta.iloc[0,0] if not meta.empty else 0
        conn.close()
        return df, meta_val

    def get_chat_history(self, category):
        """Recupera a memória da conversa."""
        conn = db_instance.get_connection()
        try:
            logs = pd.read_sql_query(
                "SELECT role, message FROM ai_chat_logs WHERE category = ? ORDER BY id ASC",
                conn, params=(category,)
            ).to_dict('records')
            
            history = []
            for log in logs:
                history.append({"role": log['role'], "parts": [log['message']]})
            return history
        except Exception as e:
            print(f"Erro ao buscar histórico: {e}")
            return []
        finally:
            conn.close()

    def save_message(self, category, role, message):
        """Salva uma mensagem na memória."""
        conn = db_instance.get_connection()
        try:
            conn.execute(
                "INSERT INTO ai_chat_logs (category, role, message) VALUES (?, ?, ?)",
                (category, role, message)
            )
            conn.commit()
        finally:
            conn.close()

    def ask_specialist(self, category, user_message=None, force_new=False):
        if not self.model: 
            return "Erro: API Key não configurada."

        df, meta_val = self.get_category_context(category)
        # Se force_new for True, ignoramos o histórico para gerar uma análise do zero
        history = [] if force_new else self.get_chat_history(category)
        
        if not history and not user_message:
            data_str = df.to_string(index=False) if not df.empty else "Sem dados registrados."
            # PROMPT DE ALTO DESEMPENHO (CFO MODE)
            prompt = (
                f"### SISTEMA DE CONSULTORIA ESTRATÉGICA INDIVIDUALIZADA\n"
                f"Você é o CFO (Diretor Financeiro) de uma conta pessoal de alta precisão. "
                f"Sua missão é analisar EXCLUSIVAMENTE a categoria: '{category}'.\n\n"
                
                f"### INPUT DE DADOS REAIS (2024-2026):\n"
                f"{data_str}\n\n"
                f"LISTA DE LANÇAMENTOS RECENTES (Data, Descrição, Valor):\n"
                f"{data_str}\n\n"
                
                f"### PARÂMETROS ESTRATÉGICOS:\n"
                f"- Meta Anual Definida para 2026: R$ {meta_val:.2f}\n"
                f"- Status de Mercado: Considerar inflação e sazonalidade histórica nos dados fornecidos.\n\n"
                
                f"### TAREFAS DE ANÁLISE:\n"
                f"1. **Detecção de Anomalias**: Identifique meses onde o gasto fugiu do padrão e tente inferir a causa.\n"
                f"2. **Teste de Stress da Meta**: Com base no gasto médio mensal real, a meta de R$ {meta_val:.2f} é realista? "
                f"Calcule o desvio percentual esperado.\n"
                f"3. **Plano de Contenção**: Se o usuário estiver acima da cota mensal (GPS), dê 2 táticas específicas de redução para esta categoria.\n"
                f"4. **Insight de Sazonalidade**: Avise qual o próximo mês de 'pico' esperado para que ele se prepare.\n\n"
                
                f"### FORMATO DE RESPOSTA:\n"
                f"Use Markdown. Seja direto, técnico mas empático. Use tabelas se necessário para comparar anos."
            )
        else:
            prompt = user_message

        for tentativa in range(4):
            try:
                # Se for uma pergunta do usuário, usamos o chat com memória
                if history or user_message:
                    chat = self.model.start_chat(history=history)
                    response = chat.send_message(prompt)
                else:
                    response = self.model.generate_content(prompt)
                
                reply = response.text
                self.save_message(category, 'model', reply)
                return reply
            except Exception as e:
                time.sleep(2)
        return "❌ O Consultor está indisponível após 4 tentativas. Verifique sua conexão ou API Key."