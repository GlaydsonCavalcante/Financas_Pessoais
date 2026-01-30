from typing import List
from src.models.transaction import Transaction
from src.database.connection import db_instance
from src.utils.parsers import parse_bb_csv, parse_sisbb_txt

class ImporterService:
    """
    Fachada para processamento de arquivos bancários.
    Recebe arquivos brutos e devolve estatísticas de importação.
    """

    def process_files(self, uploaded_files) -> dict:
        """
        Processa lista de arquivos e salva no banco.
        Retorna dicionário com resumo da operação.
        """
        stats = {"read": 0, "saved": 0, "errors": []}
        all_transactions = []

        # 1. Parsing
        for file in uploaded_files:
            try:
                filename = file.name.lower()
                file_transactions = []

                if filename.endswith('.csv'):
                    file_transactions = parse_bb_csv(file, file.name)
                elif filename.endswith('.txt'):
                    file_transactions = parse_sisbb_txt(file, file.name)
                
                if file_transactions:
                    all_transactions.extend(file_transactions)
                    stats["read"] += len(file_transactions)
                else:
                    stats["errors"].append(f"{file.name}: Nenhum dado identificado.")
                    
            except Exception as e:
                stats["errors"].append(f"{file.name}: Erro crítico - {str(e)}")

        # 2. Persistência
        if all_transactions:
            saved_count = self._save_batch(all_transactions)
            stats["saved"] = saved_count

        return stats

    def _save_batch(self, transactions: List[Transaction]) -> int:
        """Insere transações no banco ignorando duplicatas (INSERT OR IGNORE)."""
        conn = db_instance.get_connection()
        count = 0
        try:
            for t in transactions:
                try:
                    conn.execute('''
                        INSERT INTO transactions (hash_id, date, description, amount, source, category, is_manual)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (t.hash_id, t.date, t.description, t.amount, t.source, t.category, t.is_manual))
                    count += 1
                except Exception:
                    # Hash collision = Transação já existe. Ignora silenciosamente.
                    continue
            conn.commit()
        finally:
            conn.close()
        return count