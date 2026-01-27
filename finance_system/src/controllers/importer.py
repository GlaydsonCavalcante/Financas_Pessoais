from typing import List
from src.models.transaction import Transaction
from src.parsers.strategy_csv import BBCsvParser
from src.parsers.strategy_txt import SisbbTxtParser
from src.parsers.strategy_pdf import CdcPdfParser # <--- IMPORTANTE: Importando a nova classe
from src.database import DatabaseManager

class ImportController:
    def __init__(self):
        self.db = DatabaseManager()

    def process_file(self, uploaded_file):
        filename = uploaded_file.name.lower()
        strategy = None
        
        # Seleciona a estratégia baseada na extensão
        if filename.endswith('.csv'):
            strategy = BBCsvParser()
        elif filename.endswith('.txt'):
            strategy = SisbbTxtParser()
        elif filename.endswith('.pdf'):
            strategy = CdcPdfParser() # <--- IMPORTANTE: Usando a nova classe
        
        # Executa o processamento
        transactions = []
        if strategy:
            try:
                transactions = strategy.parse(uploaded_file, uploaded_file.name)
            except Exception as e:
                # Retorna erro para ser exibido no front
                print(f"Erro no parser {filename}: {e}")
                return 0, 0
        
        # Salva no banco
        saved_count = 0
        for t in transactions:
            if self.db.save_transaction(t):
                saved_count += 1
                
        # Retorna total lido vs total salvo (novos)
        return len(transactions), saved_count