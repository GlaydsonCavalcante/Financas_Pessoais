import pandas as pd
import re
from typing import List
from datetime import datetime
from src.models.transaction import Transaction
import hashlib

def _generate_hash(t: Transaction) -> str:
    """Gera ID único baseado em Data + Valor + Descrição."""
    raw = f"{t.date}{t.amount:.2f}{t.description.strip()}"
    return hashlib.md5(raw.encode()).hexdigest()

def parse_bb_csv(file_buffer, filename: str) -> List[Transaction]:
    """
    Lê CSV padrão do Banco do Brasil (Conta Corrente).
    Espera colunas: "Data", "Histórico", "Valor".
    """
    transactions = []
    try:
        # Tenta ler com encoding comum do BB (latin-1)
        df = pd.read_csv(file_buffer, encoding='latin-1', sep=',', thousands='.', decimal=',')
    except:
        file_buffer.seek(0)
        df = pd.read_csv(file_buffer, encoding='utf-8', sep=',', thousands='.', decimal=',')

    # Normalização de Colunas
    required = ["Data", "Histórico", "Valor"]
    if not all(col in df.columns for col in required):
        return []

    for _, row in df.iterrows():
        # Ignora linhas de saldo/totais
        if "Saldo" in str(row["Histórico"]):
            continue
            
        try:
            dt_obj = pd.to_datetime(row["Data"], format="%d/%m/%Y").date()
            amount = float(row["Valor"])
            desc = str(row["Histórico"]).strip()
            
            # Limpeza de Descrição (Remove prefixos comuns do BB)
            # Ex: "Compra com Cartão - 27/11 09:02 UBER" -> "UBER"
            # Regex procura por padrão de data/hora no meio da string para cortar
            clean_desc = re.sub(r'Compra com Cartão - \d{2}/\d{2} \d{2}:\d{2} ', '', desc)
            clean_desc = re.sub(r'Pix - Enviado - \d{2}/\d{2} \d{2}:\d{2} ', 'Pix env: ', clean_desc)

            t = Transaction(
                date=dt_obj,
                description=clean_desc,
                amount=amount,
                source=f"CSV: {filename}",
                category=None, # Será preenchido pelo Categorizer Service futuramente
                is_manual=False
            )
            t.hash_id = _generate_hash(t)
            transactions.append(t)
        except Exception:
            continue
            
    return transactions

def parse_sisbb_txt(file_buffer, filename: str) -> List[Transaction]:
    """
    Lê arquivo de impressão (Spool) do SISBB - Cartão de Crédito.
    Usa Regex para extrair dados de layout visual.
    """
    content = file_buffer.getvalue().decode('latin-1')
    transactions = []
    
    # Regex Poderoso: Captura Data (dd.mm.aaaa) + Descrição + Valor (com ou sem sinal)
    # Ex: 27.11.2025    BONNAPAN    52,00
    pattern = re.compile(r"^(\d{2}\.\d{2}\.\d{4})(.*?)\s+(-?[\d\.]+,\d{2})")

    capture_mode = False
    
    for line in content.split('\n'):
        line = line.strip()
        
        # Ativa captura apenas dentro do bloco de transações
        if "Data" in line and "Transações" in line:
            capture_mode = True
            continue
        if "--------" in line and capture_mode:
            # Tracejado geralmente indica fim ou totalizadores
            # Se a linha for apenas tracejada, pode ser fim
            pass

        if not capture_mode:
            continue

        match = pattern.search(line)
        if match:
            dt_str, desc, val_str = match.groups()
            
            # Filtros de exclusão (Pagamentos de fatura não são despesas aqui)
            if "SALDO FATURA" in desc or "PGTO DEBITO" in desc:
                continue

            try:
                # Tratamento de Valor PT-BR
                clean_val = val_str.replace('.', '').replace(',', '.')
                amount = float(clean_val)
                
                # Regra de Negócio: No TXT do cartão, valor positivo é gasto.
                # No nosso sistema, gasto deve ser negativo.
                amount = -abs(amount)

                dt_obj = datetime.strptime(dt_str, "%d.%m.%Y").date()

                t = Transaction(
                    date=dt_obj,
                    description=desc.strip(),
                    amount=amount,
                    source=f"Card: {filename}",
                    category="Cartão de Crédito", # Categoria provisória
                    is_manual=False
                )
                t.hash_id = _generate_hash(t)
                transactions.append(t)
            except ValueError:
                continue

    return transactions