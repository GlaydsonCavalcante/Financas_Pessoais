from typing import List
from src.models.transaction import Transaction
from src.parsers.strategy_csv import BBCsvParser
from src.parsers.strategy_txt import SisbbTxtParser
# from src.parsers.strategy_pdf import PdfParser (Implementar na Fase 2)

class ImportController:
    def process_file(self, uploaded_file) -> List[Transaction]:
        filename = uploaded_file.name.lower()
        
        strategy = None
        
        if filename.endswith('.csv'):
            strategy = BBCsvParser()
        elif filename.endswith('.txt'):
            # Verifica se é SISBB lendo o buffer sem consumir
            strategy = SisbbTxtParser()
        elif filename.endswith('.pdf'):
            # strategy = PdfParser()
            return [] # Fase 2
            
        if strategy:
            return strategy.parse(uploaded_file, uploaded_file.name)
        return []