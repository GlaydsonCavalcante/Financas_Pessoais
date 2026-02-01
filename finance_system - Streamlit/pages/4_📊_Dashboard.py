import streamlit as st
import pandas as pd
import sys
import os
from datetime import date, timedelta

# --- CORREÇÃO DE PATH ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
sys.path.append(root_dir)
# ------------------------

from src.database.connection import db_instance

st.set_page_config(page_title="Dashboard Absoluto", layout="wide")

# Constante de Exclusão (Deve ser igual à da Classificação)
CATEGORY_IGNORE = "⛔ IGNORADO"

def get_data(start_date, end_date):
    """Busca transações e calcula métricas."""
    conn = db_instance.get_connection()
    try:
        # Filtra por data E remove os ignorados
        query = f"""
            SELECT * FROM transactions 
            WHERE date BETWEEN '{start_date}' AND '{end_date}'
            AND (category IS NULL OR category != '{CATEGORY_IGNORE}')
        """
        df = pd.read_sql_query(query, conn)
        df['date'] = pd.to_datetime(df['date']).dt.date
        return df
    finally:
        conn.close()

# --- SIDEBAR: FILTROS ---
with st.sidebar:
    st.header("📅 Período de Análise")
    
    # Padrão: Últimos 12 meses para pegar a sazonalidade anual
    today = date.today()
    last_year = today - timedelta(days=365)
    
    date_range = st.date_input(
        "Selecione o Intervalo",
        value=(last_year, today),
        format="DD/MM/YYYY"
    )
    
    if len(date_range) != 2:
        st.warning("Selecione data inicial e final.")
        st.stop()
        
    start, end = date_range
    
    # Cálculo de meses no período (para a média mensal)
    # Ex: Se pegou 12 meses, dividiremos o total por 12
    days_diff = (end - start).days
    months_diff = max(1, days_diff / 30) # Evita divisão por zero
    
    st.info(f"Fator de Mensalização: **{months_diff:.1f} meses**")

# --- CARGA DE DADOS ---
df = get_data(start, end)

st.title("📊 Visão Estratégica")

if df.empty:
    st.warning("Nenhum dado encontrado para este período.")
    st.stop()

# --- BLOC 1: SOLVÊNCIA (KPIs) ---
st.subheader("1. Fluxo de Caixa Real")

# Separa Entradas e Saídas
incomes = df[df['amount'] > 0]['amount'].sum()
expenses = df[df['amount'] < 0]['amount'].sum()
balance = incomes + expenses

# Taxa de Economia
savings_rate = (balance / incomes * 100) if incomes > 0 else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Receitas Totais", f"R$ {incomes:,.2f}")
c2.metric("Despesas Totais", f"R$ {expenses:,.2f}", delta_color="inverse")
c3.metric("Saldo do Período", f"R$ {balance:,.2f}", delta=f"{savings_rate:.1f}% Econ.")

# Meta de 10% (Sua Regra de Ouro)
target_savings = incomes * 0.10
delta_target = balance - target_savings
c4.metric(
    "Meta de Economia (10%)", 
    f"R$ {target_savings:,.2f}", 
    delta=f"R$ {delta_target:,.2f} vs Meta"
)

st.divider()

# --- BLOCO 2: A MENSALIZAÇÃO (O Coração do Projeto) ---
st.subheader("2. Custo de Vida Mensalizado")
st.caption(f"Valores totais do período divididos por {months_diff:.1f} meses. Revela o 'peso real' de gastos anuais.")

# Agrupa por Categoria
cat_group = df[df['amount'] < 0].groupby('category')['amount'].sum().reset_index()
cat_group['amount'] = cat_group['amount'].abs() # Torna positivo para o gráfico

# Cria a coluna de Média Mensal
cat_group['Média Mensal'] = cat_group['amount'] / months_diff
cat_group = cat_group.sort_values(by='Média Mensal', ascending=False)

# Gráfico de Barras
st.bar_chart(
    cat_group,
    x="category",
    y="Média Mensal",
    color="#FF4B4B", # Vermelho despesa
    use_container_width=True
)

# Tabela Detalhada
with st.expander("Ver Detalhes Numéricos"):
    # Formatação para exibição
    display_df = cat_group.copy()
    display_df.columns = ['Categoria', 'Total no Período', 'Custo Mensal Real']
    st.dataframe(
        display_df,
        column_config={
            "Total no Período": st.column_config.NumberColumn(format="R$ %.2f"),
            "Custo Mensal Real": st.column_config.NumberColumn(format="R$ %.2f"),
        },
        use_container_width=True,
        hide_index=True
    )

st.divider()

# --- BLOCO 3: PROJEÇÃO FUTURA (Empréstimos) ---
st.subheader("3. Radar de Passivos")
st.caption("Compromissos já assumidos para além de hoje.")

# Busca tudo que é Futuro (> hoje)
conn = db_instance.get_connection()
future_df = pd.read_sql_query(
    f"SELECT * FROM transactions WHERE date > '{date.today()}' AND amount < 0 ORDER BY date", 
    conn
)
conn.close()

if not future_df.empty:
    future_df['date'] = pd.to_datetime(future_df['date'])
    # Agrupa por Mês/Ano
    future_df['Mes_Ano'] = future_df['date'].dt.strftime('%Y-%m')
    monthly_debt = future_df.groupby('Mes_Ano')['amount'].sum().abs()
    
    col_chart, col_metric = st.columns([2, 1])
    
    with col_chart:
        st.bar_chart(monthly_debt, color="#FFA500") # Laranja alerta
        
    with col_metric:
        total_debt = future_df['amount'].sum()
        st.metric("Dívida Contratada Total", f"R$ {total_debt:,.2f}")
        st.write("Isso é o que você já deve, independente se gastar mais ou não.")

else:
    st.info("Nenhuma dívida futura registrada. Parabéns ou cadastre em 'Empréstimos'.")