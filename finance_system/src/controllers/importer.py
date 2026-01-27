from typing import List
from src.models.transaction import Transaction
from src.parsers.strategy_csv import BBCsvParser
from src.parsers.strategy_txt import SisbbTxtParser
from src.parsers.strategy_pdf import CdcPdfParser
from src.database import DatabaseManager

class ImportController:
    def __init__(self):
        self.db = DatabaseManager()

    def process_file(self, uploaded_file):
        filename = uploaded_file.name.lower()
        strategy = None
        
        if filename.endswith('.csv'):
            strategy = BBCsvParser()
        elif filename.endswith('.txt'):
            strategy = SisbbTxtParser()
        elif filename.endswith('.pdf'):
            strategy = CdcPdfParser()
        
        # Parse
        transactions = []
        if strategy:
            transactions = strategy.parse(uploaded_file, uploaded_file.name)
        
        # Persistência
        saved_count = 0
        for t in transactions:
            if self.db.save_transaction(t):
                saved_count += 1
                
        return len(transactions), saved_count