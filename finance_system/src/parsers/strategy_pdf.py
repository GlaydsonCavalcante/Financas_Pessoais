import pdfplumber
import re
from datetime import datetime
from typing import List
from src.models.transaction import Transaction
from src.parsers.interface import IParserStrategy

class CdcPdfParser(IParserStrategy):
    def parse(self, file_buffer, filename: str) -> List[Transaction]:
        transactions = []
        
        with pdfplumber.open(file_buffer) as pdf:
            for page in pdf.pages:
                # Extrai tabelas da página
                tables = page.extract_tables()
                
                for table in tables:
                    for row in table:
                        # O layout do CDC geralmente é: 
                        # Col 0: Parcela | Col 1: Vencimento | Col 2: Situação | ... | Col X: Valor
                        # Precisamos filtrar linhas válidas
                        
                        # Remove None e limpa strings
                        clean_row = [str(cell).strip() if cell else "" for cell in row]
                        
                        # Validação básica: precisa ter data e valor ou situação
                        if len(clean_row) < 3:
                            continue
                            
                        # Detecta cabeçalho e pula
                        if "VENCIMENTO" in clean_row[1].upper():
                            continue

                        # Lógica de "Pula Parcela" ou linha vazia
                        situacao = clean_row[2].upper()
                        if "PULA" in situacao or "LIQUIDADA" in situacao:
                            # Se já foi paga ou pulada, não entra no fluxo FUTURO
                            # Se quiser histórico, remova o "LIQUIDADA"
                            continue
                        
                        # Tenta extrair data (Coluna 1)
                        try:
                            dt_str = clean_row[1]
                            dt_obj = datetime.strptime(dt_str, "%d/%m/%Y").date()
                        except ValueError:
                            continue # Não é uma linha de dados válida

                        # Tenta extrair valor (A coluna do valor varia, geralmente é a última preenchida com R$)
                        # Procura na linha inteira por algo que pareça dinheiro
                        amount = 0.0
                        for cell in clean_row:
                            if "R$" in cell:
                                # Limpa R$, pontos e troca vírgula
                                val_clean = cell.replace('R$', '').replace('.', '').replace(',', '.').strip()
                                try:
                                    amount = float(val_clean)
                                    # É uma saída futura (Dívida)
                                    amount = -abs(amount)
                                    break
                                except:
                                    continue
                        
                        if amount != 0:
                            t = Transaction(
                                date=dt_obj,
                                description=f"CDC Parcela {clean_row[0]}", # Ex: CDC Parcela 60
                                amount=amount,
                                source_file=filename,
                                raw_category="Empréstimos" # Categoria automática
                            )
                            transactions.append(t)
                            
        return transactions