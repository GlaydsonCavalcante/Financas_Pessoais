from dataclasses import dataclass
from datetime import date

@dataclass
class Transaction:
    date: date
    description: str
    amount: float
    source_file: str
    raw_category: str = "Uncategorized"
    
    # Propriedade para facilitar exibição em dataframe
    def to_dict(self):
        return {
            "Data": self.date,
            "Descrição": self.description,
            "Valor": self.amount,
            "Fonte": self.source_file,
            "Categoria": self.raw_category
        }