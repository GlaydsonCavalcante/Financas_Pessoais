import pandas as pd
from typing import List
from src.models.transaction import Transaction
from src.database.connection import db_instance
from src.utils.parsers import parse_bb_csv, parse_sisbb_txt, _generate_hash
from src.services.categorizer_service import CategorizerService

class ImporterService:
    """
    Fachada para processamento de arquivos bancários.
    Recebe arquivos brutos, salva e JÁ APLICA as regras de classificação.
    """

    def process_files(self, uploaded_files) -> dict:
        """
        Processa lista de arquivos, UNIFICA PARCELAS, salva no banco e CLASSIFICA.
        """
        stats = {"read": 0, "saved": 0, "classified": 0, "errors": []}
        all_transactions = []

        # 1. Parsing (Leitura Bruta)
        for file in uploaded_files:
            try:
                # Ajuste para garantir leitura do nome do arquivo (Flask vs Pure Python)
                filename = getattr(file, 'name', 'unknown').lower()
                file_transactions = []

                if filename.endswith('.csv'):
                    file_transactions = parse_bb_csv(file, filename)
                elif filename.endswith('.txt'):
                    file_transactions = parse_sisbb_txt(file, filename)
                
                if file_transactions:
                    all_transactions.extend(file_transactions)
                    stats["read"] += len(file_transactions)
                else:
                    stats["errors"].append(f"{filename}: Nenhum dado identificado.")
                    
            except Exception as e:
                stats["errors"].append(f"Erro em {getattr(file, 'name', '?')}: {str(e)}")

        # 2. Processamento Inteligente (ETL)
        if all_transactions:
            # A) Converte para DataFrame
            df_raw = pd.DataFrame([vars(t) for t in all_transactions])
            
            # B) Unificação de Parcelas
            df_unified = CategorizerService.unify_installments_batch(df_raw)
            
            # C) Reconverte para Objetos Transaction
            final_transactions = []
            for _, row in df_unified.iterrows():
                t = Transaction(
                    date=row['date'],
                    description=row['description'],
                    amount=row['amount'],
                    source=row['source'],
                    category=row['category'],
                    is_manual=row['is_manual']
                )
                t.hash_id = _generate_hash(t)
                final_transactions.append(t)

            # D) Persistência
            saved_count = self._save_batch(final_transactions)
            stats["saved"] = saved_count

        # 3. AUTO-CLASSIFICAÇÃO (A CORREÇÃO)
        # Instancia o serviço de categorização e manda rodar as regras
        # Fazemos isso mesmo se saved=0, para garantir que itens antigos sejam processados
        cat_service = CategorizerService()
        classified_count = cat_service.run_auto_classification()
        stats["classified"] = classified_count
        
        if classified_count > 0:
            print(f"🤖 Robô trabalhou: {classified_count} itens classificados automaticamente.")

        return stats

    def _save_batch(self, transactions: List[Transaction]) -> int:
        """Insere transações no banco ignorando duplicatas."""
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
                    continue # Ignora duplicatas
            conn.commit()
        finally:
            conn.close()
        return count

    # --- Métodos de Suporte (Férias) ---
    def preview_vacation_mode(self, start_date, end_date):
        conn = db_instance.get_connection()
        try:
            candidates = pd.read_sql_query(f"""
                SELECT * FROM transactions 
                WHERE date BETWEEN '{start_date}' AND '{end_date}'
                AND (category != 'Férias' OR category IS NULL)
                AND (category != '⛔ IGNORADO' OR category IS NULL)
            """, conn)
            
            to_update = []
            protected = []
            cursor = conn.cursor()
            
            for _, row in candidates.iterrows():
                desc = row['description']
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
                if count_outside > 0: protected.append(item)
                else: to_update.append(item)
                    
            return pd.DataFrame(to_update), pd.DataFrame(protected)
        finally:
            conn.close()

    def apply_vacation_batch(self, hash_ids: list):
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