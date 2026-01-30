from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass
class Transaction:
    """
    Entidade núcleo do sistema. Representa qualquer movimentação financeira.
    
    Campos:
        date (date): A data de competência ou vencimento.
        description (str): O nome legível da transação (ex: 'Netflix', 'Parcela Carro 1/60').
        amount (float): O valor monetário. 
                        Convenção: Negativo (-) para Saídas, Positivo (+) para Entradas.
        source (str): A origem da informação (ex: 'Extrato BB', 'Manual', 'CSV').
        category (Optional[str]): A classificação analítica (ex: 'Moradia', 'Lazer').
        is_manual (bool): Trava de segurança. Se True, a classificação nunca será sobrescrita.
        hash_id (Optional[str]): Assinatura única para evitar duplicatas no banco.
    """
    date: date
    description: str
    amount: float
    source: str
    category: Optional[str] = None
    is_manual: bool = False
    hash_id: Optional[str] = None

    @property
    def is_future(self) -> bool:
        """Retorna True se a transação é uma projeção futura."""
        return self.date > date.today()

    @property
    def is_past_due(self) -> bool:
        """Retorna True se é uma saída não paga no passado (conceito simplificado)."""
        return self.date < date.today() and self.amount < 0

    def to_dict(self) -> dict:
        """Serializa para uso em Dataframes e Interfaces."""
        return {
            "Data": self.date,
            "Descrição": self.description,
            "Valor": self.amount,
            "Fonte": self.source,
            "Categoria": self.category,
            "Status Tempo": "Futuro" if self.is_future else "Realizado"
        }