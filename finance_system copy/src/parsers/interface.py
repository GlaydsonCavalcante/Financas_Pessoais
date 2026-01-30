from abc import ABC, abstractmethod
from typing import List
from src.models.transaction import Transaction

class IParserStrategy(ABC):
    @abstractmethod
    def parse(self, file_buffer, filename: str) -> List[Transaction]:
        """Recebe um buffer de arquivo e retorna lista de transações"""
        pass