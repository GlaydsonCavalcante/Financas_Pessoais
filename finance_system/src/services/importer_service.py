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

    def preview_vacation_mode(self, start_date, end_date):
        """
        Simula a lógica de Férias:
        Busca transações no período e separa o que é Recorrente (protegido) do que é Pontual (férias).
        """
        conn = db_instance.get_connection()
        try:
            # 1. Busca candidatos dentro da janela
            # Ignora o que já for 'Férias' ou 'Ignorado'
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
                
                # 2. O Teste de Recorrência
                # Verifica se esta descrição aparece FORA da janela temporal selecionada
                # (Isso indica que é uma conta mensal comum, como Escola ou Aluguel)
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
                    # É recorrente (Existe fora das férias) -> Protege
                    protected.append(item)
                else:
                    # É exclusivo deste período -> Vira Férias
                    to_update.append(item)
                    
            return pd.DataFrame(to_update), pd.DataFrame(protected)
            
        finally:
            conn.close()

    def apply_vacation_batch(self, hash_ids: list):
        """Aplica a categoria 'Férias' em lote para os IDs validados."""
        conn = db_instance.get_connection()
        try:
            cursor = conn.cursor()
            # Otimização: Executa updates em lote
            cursor.executemany(
                "UPDATE transactions SET category = 'Férias', is_manual = 1 WHERE hash_id = ?",
                [(h,) for h in hash_ids]
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()