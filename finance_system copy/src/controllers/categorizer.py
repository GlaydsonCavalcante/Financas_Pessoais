import sqlite3
from src.database import DatabaseManager

class CategorizerEngine:
    def __init__(self):
        self.db = DatabaseManager()

    def run_auto_classification(self):
        """
        Aplica regras existentes apenas em transações NÃO manuais.
        Retorna o número de linhas afetadas.
        """
        rules_df = self.db.get_rules()
        if rules_df.empty:
            return 0

        conn = sqlite3.connect(self.db.db_path)
        count_updated = 0
        
        for _, rule in rules_df.iterrows():
            term = rule['match_term']
            cat = rule['target_category']
            
            # Atualiza onde a descrição contem o termo E (não tem categoria OU não é manual)
            # A cláusula is_manual = 0 garante que suas edições pontuais nunca sejam sobrescritas
            cursor = conn.execute('''
                UPDATE transactions 
                SET category = ? 
                WHERE description LIKE ? AND (category IS NULL OR category = '') AND is_manual = 0
            ''', (cat, f'%{term}%'))
            
            count_updated += cursor.rowcount
            
        conn.commit()
        conn.close()
        return count_updated

    def create_new_rule(self, match_term, category):
        """Cria regra e já aplica imediatamente"""
        self.db.add_rule(match_term, category)
        self.run_auto_classification()