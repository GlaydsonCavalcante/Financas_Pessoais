import os
import time
import google.generativeai as genai
import pandas as pd
from dotenv import load_dotenv
from src.database.connection import db_instance

load_dotenv() 

class AIAdvisor:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.model = None
        else:
            genai.configure(api_key=api_key)
            # Tenta usar o modelo solicitado. Se falhar, o retry vai capturar.
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp') 

    def get_category_context(self, category):
        """Busca dados de 3 anos."""
        conn = db_instance.get_connection()
        query = f"""
            SELECT strftime('%Y-%m', date) as mes, SUM(ABS(amount)) as valor
            FROM transactions 
            WHERE category = ? 
            AND strftime('%Y', date) IN ('2024', '2025', '2026')
            AND amount < 0
            GROUP BY mes
            ORDER BY mes ASC
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
        except:
            return []
        finally:
            conn.close()

    def save_message(self, category, role, message):
        conn = db_instance.get_connection()
        try:
            conn.execute(
                "INSERT INTO ai_chat_logs (category, role, message) VALUES (?, ?, ?)",
                (category, role, message)
            )
            conn.commit()
        except Exception as e:
            print(f"Erro ao salvar chat: {e}")
        finally:
            conn.close()

    def ask_with_retry(self, prompt, history=[]):
        """Tenta chamar o Gemini até 4 vezes."""
        max_retries = 4
        
        for attempt in range(max_retries):
            try:
                print(f"🤖 Tentativa IA {attempt+1}/{max_retries}...")
                if history:
                    chat = self.model.start_chat(history=history)
                    response = chat.send_message(prompt)
                else:
                    response = self.model.generate_content(prompt)
                
                return response.text
            
            except Exception as e:
                print(f"⚠️ Erro na IA (Tentativa {attempt+1}): {e}")
                time.sleep(2) # Espera 2 segundos antes de tentar de novo
                
        return "❌ O Consultor está indisponível no momento (Erro de Conexão com Gemini). Tente novamente em instantes."

    def ask_specialist(self, category, user_message=None):
        if not self.model: return "Erro: API Key não configurada."

        df, meta_val = self.get_category_context(category)
        history = self.get_chat_history(category)
        
        # GERAÇÃO INICIAL (SEM PERGUNTA DO USUÁRIO)
        if not history and not user_message:
            data_str = df.to_string(index=False) if not df.empty else "Sem dados registrados."
            initial_prompt = f"""
            Você é um Consultor Especialista na categoria: '{category}'.
            
            HISTÓRICO FINANCEIRO (2024-2026):
            {data_str}
            
            META 2026: R$ {meta_val:.2f}
            
            Analise os dados acima. Identifique padrões de alta, sazonalidade ou controle.
            Seja breve (máximo 3 frases). Use Markdown.
            """
            reply = self.ask_with_retry(initial_prompt)
            self.save_message(category, 'model', reply)
            return reply

        # CHAT CONTÍNUO
        if user_message:
            self.save_message(category, 'user', user_message)
            reply = self.ask_with_retry(user_message, history=history)
            self.save_message(category, 'model', reply)
            return reply
            
        return ""