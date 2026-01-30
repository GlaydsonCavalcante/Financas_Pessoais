import re
from datetime import datetime
from typing import List
from src.models.transaction import Transaction
from src.parsers.interface import IParserStrategy

class SisbbTxtParser(IParserStrategy):
    def parse(self, file_buffer, filename: str) -> List[Transaction]:
        content = file_buffer.getvalue().decode('latin-1') # SISBB usa Latin-1
        transactions = []
        
        # Regex para capturar linhas de transação no formato TXT do BB
        # Grupo 1: Data (DD.MM.YYYY)
        # Grupo 2: Descrição (Texto livre, as vezes colado na data)
        # Grupo 3: Valor (pode ter sinal negativo no final ou inicio, formato PT-BR)
        # Observação: O regex ignora colunas de dólar à direita se existirem
        pattern = re.compile(r"^(\d{2}\.\d{2}\.\d{4})(.*?)\s+(-?[\d\.]+,\d{2})")

        capture_mode = False
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Máquina de Estados: Só processa entre o cabeçalho e o rodapé
            if "Data" in line and "Transações" in line and "Valor" in line:
                capture_mode = True
                continue
            if "--------" in line and capture_mode:
                # Se encontrarmos linha tracejada após iniciar captura, paramos (fim do bloco)
                # Mas cuidado: as vezes tem tracejado no meio. 
                # Melhor critério: Linhas vazias ou totais
                pass
            
            if not capture_mode:
                continue

            match = pattern.search(line)
            if match:
                dt_str, desc, val_str = match.groups()
                
                # Ignora linhas de saldo anterior ou pagamentos (para evitar duplicidade na competência)
                if "SALDO FATURA" in desc or "PGTO DEBITO" in desc:
                    continue

                # Tratamento de Valor
                # Remove pontos de milhar e troca vírgula por ponto
                clean_val = val_str.replace('.', '').replace(',', '.')
                amount = float(clean_val)
                
                # Inverte sinal: No cartão, gasto positivo é dívida. 
                # Mas para fluxo de caixa, saída é negativo.
                # Mantemos negativo para indicar "saída de recurso/aumento de passivo"
                amount = -abs(amount) 

                # Tratamento de Data
                dt_obj = datetime.strptime(dt_str, "%d.%m.%Y").date()

                t = Transaction(
                    date=dt_obj,
                    description=desc.strip(),
                    amount=amount,
                    source_file=filename,
                    raw_category="Cartão Crédito"
                )
                transactions.append(t)
                
        return transactions