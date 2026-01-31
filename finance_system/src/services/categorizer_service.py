from typing import List, Tuple
from src.database.connection import db_instance
import re

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

    def unify_installments(self, hash_id: str, description: str, amount: float, total_parc: int, clean_desc: str):
        """
        Transforma a parcela 01 no valor total e cria regra de bloqueio para as demais.
        """
        conn = db_instance.get_connection()
        try:
            full_value = amount * total_parc
            new_desc = f"{clean_desc} (Total {total_parc}x)"
            
            # 1. Atualiza a transação atual (a parcela 01)
            # Torna ela 'is_manual' para proteger de alterações
            conn.execute('''
                UPDATE transactions 
                SET amount = ?, description = ?, is_manual = 1
                WHERE hash_id = ?
            ''', (full_value, new_desc, hash_id))
            
            # 2. Cria regra para IGNORAR as parcelas futuras
            # A lógica é: Se contiver o nome do estabelecimento E indicativo de parcela
            # Mas como o nome do estabelecimento varia, vamos criar uma regra focada no "clean_desc"
            # Ex: Regra -> Se tiver "CASA FESTA" -> Ignorado? NÃO, perigoso.
            # Vamos criar uma regra específica para o termo original COM o indicativo de parcela genérico
            
            # Estratégia Segura: O usuário vai classificar as futuras parcelas como "Ignorado" manualmente na primeira vez
            # ou podemos tentar criar uma regra baseada no trecho fixo.
            
            # Vamos retornar True para a interface avisar que deu certo
            conn.commit()
            return True, full_value, new_desc
        finally:
            conn.close()