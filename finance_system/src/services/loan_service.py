import hashlib
from typing import List
from datetime import date
from dateutil.relativedelta import relativedelta
from src.models.transaction import Transaction
from src.database.connection import db_instance

class LoanService:
    """
    Controlador responsável pela lógica de negócios de Passivos e Empréstimos.
    Transforma parâmetros manuais em projeções de fluxo de caixa.
    """

    def generate_plan(
        self, 
        contract_name: str, 
        amount: float, 
        first_due_date: date, 
        installments: int
    ) -> List[Transaction]:
        """
        Simula o plano de pagamentos futuro (Preview).
        Não salva no banco, apenas gera os objetos em memória.
        """
        plan = []
        monthly_cost = -abs(amount) # Garante sinal negativo (Saída)
        current_date = first_due_date

        for i in range(installments):
            # Ex: "Financ. Carro (01/48)"
            desc = f"{contract_name} ({i+1:02d}/{installments})"
            
            # Hash Determinístico: Garante que se você gerar de novo, 
            # o ID será o mesmo, evitando duplicidade se clicar 2x em salvar.
            unique_string = f"{current_date}{monthly_cost}{desc}"
            hash_id = hashlib.md5(unique_string.encode()).hexdigest()

            t = Transaction(
                date=current_date,
                description=desc,
                amount=monthly_cost,
                source="Contrato Manual",
                category="Empréstimos", # Auto-categorização
                is_manual=True,         # Protege contra reclassificação
                hash_id=hash_id
            )
            plan.append(t)
            
            # Avança mês a mês (inteligente com anos bissextos etc)
            current_date = current_date + relativedelta(months=1)
            
        return plan

    def save_plan(self, transactions: List[Transaction]) -> int:
        """
        Persiste a lista de transações no banco de dados.
        Retorna a quantidade de novos registros inseridos.
        """
        conn = db_instance.get_connection()
        saved_count = 0
        
        try:
            for t in transactions:
                try:
                    conn.execute('''
                        INSERT INTO transactions (hash_id, date, description, amount, source, category, is_manual)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (t.hash_id, t.date, t.description, t.amount, t.source, t.category, t.is_manual))
                    saved_count += 1
                except Exception:
                    # Se der erro (provavelmente hash duplicado), apenas ignora este item
                    continue
            conn.commit()
        finally:
            conn.close()
            
        return saved_count