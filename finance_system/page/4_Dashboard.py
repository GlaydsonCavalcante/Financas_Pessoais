import streamlit as st
import pandas as pd
import plotly.express as px
from src.database import DatabaseManager

st.set_page_config(page_title="Dashboard Estratégico", layout="wide")
db = DatabaseManager()

st.title("📊 Painel de Controle Financeiro")

# Carregar dados
df = db.get_all_transactions()

if df.empty:
    st.warning("Sem dados para analisar. Faça a ingestão dos arquivos primeiro.")
    st.stop()

# Converter data para datetime
df['date'] = pd.to_datetime(df['date'])
df['month_year'] = df['date'].dt.to_period('M').astype(str)

# --- FILTROS LATERAIS ---
with st.sidebar:
    st.header("Configuração de Cenário")
    # Filtro de Data
    min_date = df['date'].min().date()
    max_date = df['date'].max().date()
    start_date, end_date = st.date_input("Período de Análise", [min_date, max_date])
    
    # Meta de Economia
    savings_goal_pct = st.slider("Meta de Economia (%)", 1, 30, 10)

# Filtrar DataFrame
mask = (df['date'].dt.date >= start_date) & (df['date'].dt.date <= end_date)
df_filtered = df.loc[mask]

# --- BLOCO 1: FLUXO DE CAIXA REAL (Regime de Caixa) ---
st.subheader("1. Fluxo de Caixa Realizado")
daily_balance = df_filtered.groupby('date')['amount'].sum().cumsum()

# KPI Cards
receitas = df_filtered[df_filtered['amount'] > 0]['amount'].sum()
despesas = df_filtered[df_filtered['amount'] < 0]['amount'].sum()
resultado = receitas + despesas
savings_rate = (resultado / receitas * 100) if receitas > 0 else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Receita Total", f"R$ {receitas:,.2f}")
c2.metric("Despesa Total", f"R$ {despesas:,.2f}", delta_color="inverse")
c3.metric("Saldo do Período", f"R$ {resultado:,.2f}", delta=f"{savings_rate:.1f}% econ.")
c4.metric("Meta de Economia", f"{savings_goal_pct}%", 
          delta=f"{savings_rate - savings_goal_pct:.1f}% (Desvio)",
          delta_color="normal" if savings_rate >= savings_goal_pct else "inverse")

# --- BLOCO 2: A MENSALIZAÇÃO (Sua Visão Central) ---
st.divider()
st.subheader("2. Visão Mensalizada (O Custo Oculto)")
st.markdown("""
Esta tabela converte gastos esporádicos (Férias, IPVA) em custo mensal equivalente. 
**Interpretação:** Se a coluna 'Média Mensal' for alta para categorias sazonais, você deve provisionar este valor todo mês.
""")

# Agrupa por categoria
cat_analysis = df_filtered[df_filtered['amount'] < 0].groupby('category')['amount'].agg(['sum', 'count']).reset_index()
cat_analysis.columns = ['Categoria', 'Total Gasto', 'Frequência']

# Cálculo de meses no período selecionado
n_months = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month + 1
if n_months < 1: n_months = 1

cat_analysis['Custo Mensal Real'] = cat_analysis['Total Gasto'] / n_months
cat_analysis = cat_analysis.sort_values('Custo Mensal Real') # Ordena do maior gasto para o menor (negativo)

# Gráfico de Barras Horizontal
fig = px.bar(
    cat_analysis, 
    x='Custo Mensal Real', 
    y='Categoria', 
    orientation='h',
    text_auto='.2s',
    title="Onde seu dinheiro realmente vai (Média Mensal)",
    color='Custo Mensal Real',
    color_continuous_scale='Reds'
)
st.plotly_chart(fig, use_container_width=True)

# --- BLOCO 3: PROJEÇÃO FUTURA (CDC) ---
st.divider()
st.subheader("3. Radar de Passivos Futuros (Empréstimos)")

# Filtra transações futuras (> hoje)
future_mask = df['date'].dt.date > date.today()
future_df = df.loc[future_mask]

if not future_df.empty:
    future_by_year = future_df.groupby(future_df['date'].dt.year)['amount'].sum().reset_index()
    future_by_year.columns = ['Ano', 'Dívida a Pagar']
    
    c_left, c_right = st.columns(2)
    with c_left:
        st.dataframe(future_by_year, use_container_width=True)
    with c_right:
        st.caption("Este gráfico mostra o impacto do CDC/Empréstimos nos próximos anos.")
        st.bar_chart(future_by_year.set_index('Ano'))
else:
    st.info("Nenhuma dívida futura cadastrada (Importe o PDF do CDC).")