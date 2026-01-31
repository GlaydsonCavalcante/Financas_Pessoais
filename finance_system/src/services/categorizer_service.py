from typing import List, Tuple
from src.database.connection import db_instance
import re
import pandas as pd

class CategorizerService:
    """
    Motor de Inteligência do Sistema.
    Responsável por aplicar regras de negócios para classificar transações.
    """

    def get_pending_count(self) -> int:
        """Retorna quantas transações ainda não têm categoria."""
        conn = db_instance.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM transactions WHERE category IS NULL OR category = ''")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def get_pending_transactions(self):
        """Busca todas as transações pendentes para a interface."""
        conn = db_instance.get_connection()
        try:
            # Retorna DataFrame para facilitar na UI
            import pandas as pd
            return pd.read_sql_query(
                "SELECT * FROM transactions WHERE category IS NULL OR category = '' ORDER BY date DESC", 
                conn
            )
        finally:
            conn.close()

    def run_auto_classification(self) -> int:
        """
        Aplica todas as regras conhecidas nas transações pendentes.
        Retorna o número de transações classificadas nesta execução.
        """
        conn = db_instance.get_connection()
        updated_count = 0
        
        try:
            # Garante que a tabela de regras existe
            conn.execute('''
                CREATE TABLE IF NOT EXISTS classification_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_term TEXT UNIQUE NOT NULL,
                    target_category TEXT NOT NULL
                )
            ''')

            # 1. Busca Regras
            rules = conn.execute("SELECT match_term, target_category FROM classification_rules").fetchall()
            if not rules:
                return 0

            # 2. Aplica Regras (SQL LIKE)
            # Apenas em transações que NÃO são manuais E estão sem categoria
            for term, category in rules:
                # O termo '%term%' busca a palavra em qualquer lugar da descrição
                cursor = conn.execute('''
                    UPDATE transactions 
                    SET category = ? 
                    WHERE description LIKE ? 
                      AND (category IS NULL OR category = '') 
                      AND is_manual = 0
                ''', (category, f'%{term}%'))
                updated_count += cursor.rowcount
            
            conn.commit()
            return updated_count
        finally:
            conn.close()

    def create_rule(self, term: str, category: str) -> bool:
        """
        Ensina uma nova regra ao sistema.
        Ex: term='UBER', category='Transporte'
        """
        conn = db_instance.get_connection()
        try:
            # Garante tabela antes de inserir
            conn.execute('''
                CREATE TABLE IF NOT EXISTS classification_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_term TEXT UNIQUE NOT NULL,
                    target_category TEXT NOT NULL
                )
            ''')

            # Insere ou Atualiza a regra
            conn.execute('''
                INSERT OR REPLACE INTO classification_rules (match_term, target_category)
                VALUES (?, ?)
            ''', (term, category))
            conn.commit()
            
            # Roda classificação imediatamente para aplicar o novo conhecimento
            self.run_auto_classification()
            return True
        except Exception as e:
            print(f"Erro ao criar regra: {e}")
            return False
        finally:
            conn.close()

    def manual_update(self, hash_id: str, category: str):
        """
        Classificação manual pontual (Trava de Segurança).
        """
        conn = db_instance.get_connection()
        try:
            conn.execute('''
                UPDATE transactions 
                SET category = ?, is_manual = 1 
                WHERE hash_id = ?
            ''', (category, hash_id))
            conn.commit()
        finally:
            conn.close()
            
    def get_rules(self):
        """Retorna todas as regras cadastradas."""
        conn = db_instance.get_connection()
        try:
            import pandas as pd
            # Garante tabela
            conn.execute('''
                CREATE TABLE IF NOT EXISTS classification_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_term TEXT UNIQUE NOT NULL,
                    target_category TEXT NOT NULL
                )
            ''')
            return pd.read_sql_query("SELECT * FROM classification_rules ORDER BY match_term", conn)
        finally:
            conn.close()

    def delete_rule(self, match_term: str):
        conn = db_instance.get_connection()
        conn.execute("DELETE FROM classification_rules WHERE match_term = ?", (match_term,))
        conn.commit()
        conn.close()

    def get_unique_categories(self):
        """
        Retorna uma lista única de todas as categorias já utilizadas no sistema.
        Útil para manter consistência de nomes (Memória).
        """
        conn = db_instance.get_connection()
        try:
            import pandas as pd
            # Busca categorias distintas da tabela de transações e de regras
            # Unimos as duas para ter a memória completa
            query = """
            SELECT DISTINCT category as Categoria FROM transactions WHERE category IS NOT NULL AND category != ''
            UNION
            SELECT DISTINCT target_category as Categoria FROM classification_rules
            ORDER BY Categoria ASC
            """
            return pd.read_sql_query(query, conn)
        finally:
            conn.close()
    
    def detect_installment(self, description: str) -> tuple:
        """
        Tenta identificar padrão de parcelamento.
        Retorna: (is_installment, current_parc, total_parc, clean_desc)
        """
        # Padrões comuns: "PARC 01/10", "01/10", "PARCELA 1 DE 10"
        # Regex captura: (parcela_atual) / (total)
        patterns = [
            r"PARC\s*(\d{2})/(\d{2})", # PARC 01/05
            r"(\d{2})/(\d{2})",        # 01/05 solto
            r"PARC\s*(\d+)\s*DE\s*(\d+)" # PARC 1 DE 5
        ]
        
        for p in patterns:
            match = re.search(p, description, re.IGNORECASE)
            if match:
                current, total = map(int, match.groups())
                # Remove o trecho "PARC 01/05" da descrição para limpar o nome
                clean_desc = re.sub(p, "", description, flags=re.IGNORECASE).strip()
                # Remove espaços duplos e traços soltos
                clean_desc = re.sub(r"\s+-\s+", " ", clean_desc).strip()
                return True, current, total, clean_desc
                
        return False, 0, 0, description

    def unify_installments(self, hash_id: str, description: str, amount: float, total_parc: int, clean_desc: str, category: str = None):
        """
        Unifica valor, altera descrição E JÁ APLICA A CATEGORIA (Atomic Update).
        """
        conn = db_instance.get_connection()
        try:
            full_value = amount * total_parc
            new_desc = f"{clean_desc} (Total {total_parc}x)"
            
            # Se a categoria foi informada, já atualiza ela junto
            # Se não, mantém NULL (caso antigo)
            sql = '''
                UPDATE transactions 
                SET amount = ?, description = ?, is_manual = 1
            '''
            params = [full_value, new_desc]
            
            if category:
                sql += ", category = ?"
                params.append(category)
                
            sql += " WHERE hash_id = ?"
            params.append(hash_id)
            
            conn.execute(sql, params)
            conn.commit()
            return True, full_value, new_desc
        finally:
            conn.close()

    def unify_installments_batch(df):
        """
        Processa um DataFrame de transações para converter parcelamentos (Caixa) 
        em compras únicas (Competência).
        
        Lógica:
        1. Identifica a parcela 01/XX.
        2. Calcula o valor total (Valor da Parcela * Total de Parcelas).
        3. Atualiza a linha da parcela 01 com o valor cheio e remove a numeração.
        4. Identifica e remove todas as parcelas subsequentes (02, 03...) presentes no arquivo
        para evitar duplicidade.
        """
        
        # 1. Preparação: Extração segura de dados de parcelamento
        # Regex captura padrões como "01/10", "1/10", "01 / 10"
        regex_pattern = r'(\d{1,2})\s*/\s*(\d{1,2})'
        
        def extract_parcel_info(desc):
            match = re.search(regex_pattern, str(desc))
            if match:
                curr, total = map(int, match.groups())
                # Limpa o nome removendo "01/10", "Parc 01/10", etc.
                # Remove a parte da string que deu match e limpa espaços extras
                clean_name = re.sub(regex_pattern, '', str(desc), 1)
                clean_name = re.sub(r'(?i)parc\.?|parcela', '', clean_name).strip()
                # Remove traços ou pontos soltos no final
                clean_name = clean_name.strip(' -.')
                return curr, total, clean_name
            return None, None, desc

        # Aplica a extração criando colunas temporárias
        # (Usamos zip para fazer isso de forma vetorizada e rápida)
        df_temp = df['description'].apply(extract_parcel_info).tolist()
        df[['p_curr', 'p_total', 'clean_desc']] = pd.DataFrame(df_temp, index=df.index)

        # 2. Identificar as "Cabeças" (Parcela 01 de XX)
        # Filtramos onde p_curr é 1 e p_total > 1
        heads_mask = (df['p_curr'] == 1) & (df['p_total'] > 1)
        
        # Se não tiver parcelas, retorna o DF original limpo
        if not heads_mask.any():
            return df.drop(columns=['p_curr', 'p_total', 'clean_desc'], errors='ignore')

        # Lista para armazenar índices das parcelas futuras que serão removidas
        indexes_to_remove = []
        
        # 3. Processamento das Cabeças
        # Iteramos apenas sobre as linhas que são "01/XX"
        for idx, row in df[heads_mask].iterrows():
            total_installments = int(row['p_total'])
            installment_value = row['amount']
            clean_name = row['clean_desc']
            
            # --- PASSO A: TRANSFORMAR EM COMPETÊNCIA ---
            # Calcula o valor total da compra
            full_value = installment_value * total_installments
            
            # Atualiza a linha original (A "01/XX" vira a compra cheia)
            df.at[idx, 'amount'] = full_value
            df.at[idx, 'description'] = f"{clean_name} (Compra Parcelada {total_installments}x)"
            # Opcional: Marcar uma flag para saber que foi unificado auto
            df.at[idx, 'auto_unified'] = True 

            # --- PASSO B: LIMPAR AS PARCELAS FUTURAS ---
            # Procuramos no MESMO dataframe as parcelas 02, 03... desse mesmo item.
            # Critério rigoroso: Mesmo Nome Limpo + Mesmo Valor de Parcela (aprox) + Parcela > 1
            
            # Margem de erro de 1 centavo para o valor da parcela (arredondamentos bancários)
            siblings_mask = (
                (df['clean_desc'] == clean_name) & 
                (df['p_curr'] > 1) & 
                (abs(df['amount'] - installment_value) < 0.05) # Tolerância de 5 centavos
            )
            
            # Adiciona os índices encontrados para remoção
            siblings_indexes = df[siblings_mask].index.tolist()
            indexes_to_remove.extend(siblings_indexes)

        # 4. Finalização
        # Remove as linhas das parcelas 02, 03... (pois o valor já está somado na 01)
        df_final = df.drop(index=indexes_to_remove).copy()
        
        # Remove colunas auxiliares
        df_final = df_final.drop(columns=['p_curr', 'p_total', 'clean_desc'], errors='ignore')
        
        print(f"✅ Unificação Concluída: {heads_mask.sum()} compras unificadas.")
        print(f"🗑️ Parcelas futuras removidas: {len(indexes_to_remove)}")
        
        return df_final

