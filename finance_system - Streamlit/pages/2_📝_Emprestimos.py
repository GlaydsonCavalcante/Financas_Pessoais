import streamlit as st
import pandas as pd
from datetime import date
from src.services.loan_service import LoanService

st.set_page_config(page_title="Cadastro de Passivos", layout="centered")

st.title("📝 Gestão de Empréstimos")
st.caption("Cadastre contratos de longo prazo para projetar seu fluxo de caixa futuro.")
st.divider()

# --- ÁREA DE INPUT ---
with st.container(border=True):
    st.subheader("Novo Contrato")
    
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Nome do Credor", placeholder="Ex: Financiamento Imóvel")
        installments = st.number_input("Parcelas Restantes", min_value=1, value=12, step=1)
    
    with col2:
        amount = st.number_input("Valor da Parcela (R$)", min_value=0.0, format="%.2f")
        # Padrão: Data de hoje, facilitando a lógica temporal
        first_date = st.date_input("Próximo Vencimento", value=date.today())

    if st.button("Gerar Projeção", type="primary", use_container_width=True):
        if not name or amount <= 0:
            st.error("Por favor, preencha o nome e um valor válido.")
        else:
            # Invoca a camada de serviço
            service = LoanService()
            plan = service.generate_plan(name, amount, first_date, installments)
            
            # Guarda na sessão para persistência posterior
            st.session_state['loan_preview'] = plan
            st.rerun()

# --- ÁREA DE CONFIRMAÇÃO ---
if 'loan_preview' in st.session_state:
    plan = st.session_state['loan_preview']
    
    st.divider()
    st.subheader("🔎 Pré-visualização do Impacto")
    
    # Métricas Rápidas
    total_divida = sum(t.amount for t in plan)
    final_date = plan[-1].date
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Impacto Total", f"R$ {total_divida:,.2f}")
    m2.metric("Término", final_date.strftime("%d/%m/%Y"))
    m3.metric("Parcelas", len(plan))

    # Tabela Visual
    df = pd.DataFrame([t.to_dict() for t in plan])
    st.dataframe(
        df[['Data', 'Descrição', 'Valor', 'Status Tempo']], 
        use_container_width=True, 
        hide_index=True
    )

    col_btn1, col_btn2 = st.columns([1, 4])
    if col_btn1.button("Cancelar"):
        del st.session_state['loan_preview']
        st.rerun()
        
    if col_btn2.button("💾 Confirmar e Gravar no Banco", type="primary"):
        service = LoanService()
        saved = service.save_plan(plan)
        
        if saved > 0:
            st.success(f"Sucesso! {saved} parcelas foram registradas no seu fluxo futuro.")
            del st.session_state['loan_preview']
        else:
            st.warning("Estas parcelas já constavam no banco de dados.")