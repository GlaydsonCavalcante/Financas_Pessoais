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

    @staticmethod
    def unify_installments_batch(df):
        """
        1. Unifica parcela 01 (Valor Total).
        2. Marca parcelas 02+ como '⛔ IGNORADO' automaticamente.
        """
        # Regex captura padrões como "01/10", "1/10", "01 / 10"
        regex_pattern = r'(\d{1,2})\s*/\s*(\d{1,2})'
        
        def extract_parcel_info(desc):
            match = re.search(regex_pattern, str(desc))
            if match:
                curr, total = map(int, match.groups())
                # Limpa o nome
                clean_name = re.sub(regex_pattern, '', str(desc), 1)
                clean_name = re.sub(r'(?i)parc\.?|parcela', '', clean_name).strip()
                clean_name = clean_name.strip(' -.')
                return curr, total, clean_name
            return None, None, desc

        # Prepara DataFrame
        df_temp = df['description'].apply(extract_parcel_info).tolist()
        df[['p_curr', 'p_total', 'clean_desc']] = pd.DataFrame(df_temp, index=df.index)

        # ---------------------------------------------------------
        # FASE 1: AS CABEÇAS (Parcela 01) - Transforma em Valor Cheio
        # ---------------------------------------------------------
        heads_mask = (df['p_curr'] == 1) & (df['p_total'] > 1)
        
        for idx, row in df[heads_mask].iterrows():
            total_installments = int(row['p_total'])
            installment_value = row['amount']
            clean_name = row['clean_desc']
            
            # Valor Total
            full_value = installment_value * total_installments
            
            # Atualiza a linha da parcela 01
            df.at[idx, 'amount'] = full_value
            df.at[idx, 'description'] = f"{clean_name} (Compra Parcelada {total_installments}x)"
            df.at[idx, 'is_manual'] = True # Protege
            
            # Tenta encontrar e remover irmãos (parcelas 02, 03) que estejam NESTE MESMO ARQUIVO
            siblings_mask = (
                (df['clean_desc'] == clean_name) & 
                (df['p_curr'] > 1) & 
                (abs(df['amount'] - installment_value) < 0.05)
            )
            # Marca irmãos do mesmo arquivo para remoção imediata
            df.loc[siblings_mask, 'to_remove'] = True

        # Remove os que foram encontrados no mesmo lote
        if 'to_remove' in df.columns:
            df = df[df['to_remove'] != True].copy()

        # ---------------------------------------------------------
        # FASE 2: OS ORFÃOS (Parcelas 02, 03... isoladas) - IGNORAR
        # ---------------------------------------------------------
        # Se sobrou alguma parcela > 1 (que veio de outro mês ou não foi linkada)
        orphans_mask = (df['p_curr'] > 1)
        
        if orphans_mask.any():
            print(f"🧹 Faxina: Ignorando {orphans_mask.sum()} parcelas intermediárias isoladas.")
            # Marca como Ignorado
            df.loc[orphans_mask, 'category'] = "⛔ IGNORADO"
            df.loc[orphans_mask, 'is_manual'] = True # Trava para ninguém mexer

        # Limpeza final de colunas auxiliares
        df_final = df.drop(columns=['p_curr', 'p_total', 'clean_desc', 'to_remove'], errors='ignore')
        
        return df_final
    
    def get_grouped_pending(self):
        """Retorna pendências agrupadas por descrição (Para Aba Lote)."""
        conn = db_instance.get_connection()
        try:
            import pandas as pd
            query = """
                SELECT 
                    description, 
                    COUNT(*) as qtd, 
                    AVG(amount) as avg_amount 
                FROM transactions 
                WHERE (category IS NULL OR category = '') 
                GROUP BY description 
                ORDER BY description ASC
            """
            return pd.read_sql_query(query, conn)
        finally:
            conn.close()

    def apply_batch_by_description(self, descriptions: list, category: str, create_rule: bool):
        """Aplica categoria em massa baseada na descrição exata."""
        conn = db_instance.get_connection()
        try:
            cursor = conn.cursor()
            
            # 1. Cria regras (opcional)
            if create_rule:
                for desc in descriptions:
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO classification_rules (match_term, target_category) VALUES (?, ?)", 
                            (desc, category)
                        )
                    except: pass

            # 2. Atualiza transações
            placeholders = ', '.join(['?'] * len(descriptions))
            sql = f"""
                UPDATE transactions 
                SET category = ?, is_manual = 1 
                WHERE description IN ({placeholders}) 
                  AND (category IS NULL OR category = '')
            """
            params = [category] + descriptions
            cursor.execute(sql, params)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def apply_batch_by_description(self, descriptions: list, category: str, create_rule: bool):
        """
        Aplica categoria em transações baseando-se na descrição exata.
        Opcionalmente cria a regra de aprendizado.
        """
        conn = db_instance.get_connection()
        updated_count = 0
        try:
            cursor = conn.cursor()
            
            # 1. Cria regras se solicitado
            if create_rule:
                # Prepara dados para inserção em massa ou loop seguro
                for desc in descriptions:
                    # Tenta criar regra (ignora se já existe)
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO classification_rules (match_term, target_category) VALUES (?, ?)", 
                            (desc, category)
                        )
                    except:
                        pass # Termo já existe ou erro de constraint

            # 2. Atualiza transações em massa
            # Monta query dinâmica: UPDATE ... WHERE description IN (?, ?, ?)
            placeholders = ', '.join(['?'] * len(descriptions))
            sql = f"""
                UPDATE transactions 
                SET category = ?, is_manual = 1 
                WHERE description IN ({placeholders}) 
                  AND (category IS NULL OR category = '')
            """
            # O primeiro parametro é a categoria, os demais são as descrições
            params = [category] + descriptions
            
            cursor.execute(sql, params)
            updated_count = cursor.rowcount
            
            conn.commit()
            return updated_count
        finally:
            conn.close()

    # ... (seu código atual)

    def preview_vacation_mode(self, start_date, end_date):
        """
        (Compatibilidade Streamlit) Simula a lógica de Férias:
        Busca transações no período e separa o que é Recorrente (protegido) do que é Pontual (férias).
        """
        conn = db_instance.get_connection()
        try:
            import pandas as pd
            # 1. Busca candidatos dentro da janela
            query = f"""
                SELECT * FROM transactions 
                WHERE date BETWEEN '{start_date}' AND '{end_date}'
                AND (category != 'Férias' OR category IS NULL)
                AND (category != '⛔ IGNORADO' OR category IS NULL)
            """
            candidates = pd.read_sql_query(query, conn)
            
            to_update = []
            protected = []
            
            cursor = conn.cursor()
            
            for _, row in candidates.iterrows():
                desc = row['description']
                
                # 2. O Teste de Recorrência
                # Verifica se esta descrição aparece FORA da janela temporal selecionada
                cursor.execute(f"""
                    SELECT count(*) FROM transactions 
                    WHERE description = ? 
                    AND date NOT BETWEEN '{start_date}' AND '{end_date}'
                """, (desc,))
                
                count_outside = cursor.fetchone()[0]
                
                item = {
                    "hash_id": row['hash_id'],
                    "Data": row['date'],
                    "Descrição": desc,
                    "Valor": row['amount'],
                    "Categoria Atual": row['category']
                }
                
                if count_outside > 0:
                    protected.append(item)
                else:
                    to_update.append(item)
                    
            return pd.DataFrame(to_update), pd.DataFrame(protected)
            
        finally:
            conn.close()

    def apply_vacation_batch(self, hash_ids: list):
        """(Compatibilidade Streamlit) Aplica a categoria 'Férias' em lote."""
        conn = db_instance.get_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany(
                "UPDATE transactions SET category = 'Férias', is_manual = 1 WHERE hash_id = ?",
                [(h,) for h in hash_ids]
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()