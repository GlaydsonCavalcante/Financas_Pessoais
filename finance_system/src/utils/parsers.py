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
    Lê CSV do Banco do Brasil.
    Correção: Ajustado para ler decimais com PONTO (.) conforme amostra 'extrato (1).csv'.
    """
    transactions = []
    try:
        # Tenta ler com encoding comum do BB (latin-1)
        # CORREÇÃO AQUI: decimal='.' e thousands=None (padrão US)
        df = pd.read_csv(file_buffer, encoding='latin-1', sep=',', quotechar='"', decimal='.')
    except:
        file_buffer.seek(0)
        df = pd.read_csv(file_buffer, encoding='utf-8', sep=',', quotechar='"', decimal='.')

    # Normalização de Colunas (Remove espaços extras nos nomes)
    df.columns = [c.strip() for c in df.columns]

    # Verifica colunas essenciais
    required = ["Data", "Histórico", "Valor"]
    if not all(col in df.columns for col in required):
        return []

    for _, row in df.iterrows():
        # Ignora linhas de saldo/totais ou vazias
        hist = str(row["Histórico"])
        if "Saldo" in hist or "S A L D O" in hist:
            continue
            
        try:
            # Data
            dt_obj = pd.to_datetime(row["Data"], format="%d/%m/%Y").date()
            
            # Valor (Já vem float correto devido ao decimal='.')
            amount = float(row["Valor"])
            
            # Descrição
            desc = hist.strip()
            # Limpeza de Prefixos Comuns
            desc = re.sub(r'Compra com Cartão - \d{2}/\d{2} \d{2}:\d{2} ', '', desc)
            desc = re.sub(r'Pix - Enviado - \d{2}/\d{2} \d{2}:\d{2} ', 'Pix env: ', desc)
            desc = re.sub(r'Pix - Recebido - \d{2}/\d{2} \d{2}:\d{2} ', 'Pix rec: ', desc)

            t = Transaction(
                date=dt_obj,
                description=desc,
                amount=amount,
                source=f"CSV: {filename}",
                category=None,
                is_manual=False
            )
            t.hash_id = _generate_hash(t)
            transactions.append(t)
        except Exception as e:
            # Pula linhas com erro de conversão
            continue
            
    return transactions

def parse_sisbb_txt(file_buffer, filename: str) -> List[Transaction]:
    """
    Lê arquivo de fatura do Cartão (TXT/Spool).
    Mantém lógica brasileira (Vírgula para decimais).
    """
    try:
        content = file_buffer.getvalue().decode('latin-1')
    except:
        content = file_buffer.getvalue().decode('utf-8')
        
    transactions = []
    
    # Regex ajustado para capturar a linha da fatura
    # Ex: 27.11    BONNAPAN    52,00
    # O ano geralmente vem no cabeçalho, mas o BB repete data completa às vezes ou só DD.MM
    # Vamos assumir DD.MM.AAAA com base no seu arquivo sample
    pattern = re.compile(r"^(\d{2}\.\d{2}\.\d{4}?)(.*?)\s+(-?[\d\.]+,\d{2})")

    capture_mode = False
    
    for line in content.split('\n'):
        line = line.strip()
        
        # Gatilhos de início e fim de leitura
        if "Data" in line and "Transações" in line:
            capture_mode = True
            continue
        if "--------" in line and capture_mode:
            # Se for apenas tracejado, não faz nada, mas se tiver texto depois, pode ser rodapé
            pass

        if not capture_mode:
            continue

        match = pattern.search(line)
        if match:
            dt_str, desc, val_str = match.groups()
            
            # Filtra linhas de pagamento ou saldo anterior
            if "SALDO FATURA" in desc or "PGTO DEBITO" in desc:
                continue

            try:
                # Tratamento de Valor (Padrão BR: 1.000,00 -> 1000.00)
                clean_val = val_str.replace('.', '').replace(',', '.')
                amount = float(clean_val)
                
                # Regra: No TXT, gasto vem positivo. Inverter para negativo.
                amount = -abs(amount)

                # Tratamento de Data
                # Se vier apenas DD.MM, precisamos adivinhar o ano (arriscado), 
                # mas seu sample mostra DD.MM.AAAA (12.09.2024), então parsing direto.
                dt_obj = datetime.strptime(dt_str, "%d.%m.%Y").date()

                t = Transaction(
                    date=dt_obj,
                    description=desc.strip(),
                    amount=amount,
                    source=f"Card: {filename}",
                    category=None,
                    is_manual=False
                )
                t.hash_id = _generate_hash(t)
                transactions.append(t)
            except ValueError:
                continue

    return transactions