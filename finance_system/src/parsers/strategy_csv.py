import pandas as pd
from typing import List
from io import StringIO
from src.models.transaction import Transaction
from src.parsers.interface import IParserStrategy

class BBCsvParser(IParserStrategy):
    def parse(self, file_buffer, filename: str) -> List[Transaction]:
        # Pula as primeiras linhas se necessário, mas o BB geralmente manda cabeçalho limpo
        # Encoding comum no BB CSV é latin-1 ou utf-8 dependendo da exportação
        try:
            df = pd.read_csv(file_buffer, encoding='latin-1', sep=',', quotechar='"', thousands='.', decimal=',')
        except:
            file_buffer.seek(0)
            df = pd.read_csv(file_buffer, encoding='utf-8', sep=',', quotechar='"', thousands='.', decimal=',')

        transactions = []
        
        # Filtra apenas colunas necessárias e linhas válidas
        # O CSV do BB tem colunas: "Data", "Histórico", "Valor"
        required_cols = ["Data", "Histórico", "Valor"]
        if not all(col in df.columns for col in required_cols):
             # Fallback para tentar identificar cabeçalho em outra linha se falhar
             return []

        for _, row in df.iterrows():
            # Pula linhas de saldo
            if "Saldo" in str(row["Histórico"]):
                continue
                
            try:
                # Conversão de data
                dt_obj = pd.to_datetime(row["Data"], format="%d/%m/%Y").date()
                
                t = Transaction(
                    date=dt_obj,
                    description=row["Histórico"],
                    amount=float(row["Valor"]), # Pandas já tratou decimal devido ao parametro
                    source_file=filename,
                    raw_category="Conta Corrente"
                )
                transactions.append(t)
            except Exception as e:
                # Log de erro silencioso para linha inválida
                continue
                
        return transactions