import pdfplumber
import re
from datetime import datetime
from typing import List
from src.models.transaction import Transaction
from src.parsers.interface import IParserStrategy

class CdcPdfParser(IParserStrategy):
    def parse(self, file_buffer, filename: str) -> List[Transaction]:
        transactions = []
        
        # Abre o PDF a partir da memória
        with pdfplumber.open(file_buffer) as pdf:
            for page in pdf.pages:
                # Extrai tabelas da página
                tables = page.extract_tables()
                
                for table in tables:
                    for row in table:
                        # Limpa linhas vazias ou None
                        clean_row = [str(cell).strip() if cell else "" for cell in row]
                        
                        # Validação básica: precisa ter pelo menos 3 colunas (Parcela, Vencimento, Situação...)
                        if len(clean_row) < 3:
                            continue
                            
                        # Pula cabeçalho
                        if "VENCIMENTO" in clean_row[1].upper():
                            continue

                        # Ignora parcelas já pagas ou puladas (focamos no fluxo FUTURO ou DÍVIDA ATIVA)
                        # Se quiser histórico passado, remova o "LIQUIDADA"
                        situacao = clean_row[2].upper()
                        if "PULA" in situacao or "LIQUIDADA" in situacao:
                            continue
                        
                        # Tenta extrair data (Coluna 1 geralmente)
                        try:
                            dt_str = clean_row[1]
                            dt_obj = datetime.strptime(dt_str, "%d/%m/%Y").date()
                        except ValueError:
                            continue 

                        # Tenta extrair valor (procura R$ em qualquer coluna da linha)
                        amount = 0.0
                        for cell in clean_row:
                            if "R$" in cell:
                                # Limpa formatação (R$ 1.000,00 -> 1000.00)
                                val_clean = cell.replace('R$', '').replace('.', '').replace(',', '.').strip()
                                try:
                                    amount = float(val_clean)
                                    # É uma dívida/saída futura, então negativo
                                    amount = -abs(amount)
                                    break
                                except:
                                    continue
                        
                        if amount != 0:
                            t = Transaction(
                                date=dt_obj,
                                description=f"CDC Parcela {clean_row[0]}", 
                                amount=amount,
                                source_file=filename,
                                raw_category="Empréstimos"
                            )
                            transactions.append(t)
                            
        return transactions