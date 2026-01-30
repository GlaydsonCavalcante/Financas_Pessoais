import streamlit as st
from src.database import DatabaseManager

st.set_page_config(page_title="Regras", layout="wide")
db = DatabaseManager()

st.title("⚙️ Gerenciador de Aprendizado")
st.markdown("Regras que o sistema utiliza para categorizar automaticamente.")

rules_df = db.get_rules()

if rules_df.empty:
    st.info("Nenhuma regra criada ainda.")
else:
    # Exibe editor visual
    # O usuário pode deletar linhas selecionando e clicando em delete (dependendo da versão do st)
    # Para garantir, faremos um botão de exclusão explícito
    
    for index, row in rules_df.iterrows():
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            st.text(row['match_term'])
        with c2:
            st.tag(row['target_category']) # Pseudo-badge
        with c3:
            if st.button("🗑️ Excluir", key=f"del_{row['id']}"):
                db.delete_rule(row['match_term'])
                st.rerun()
        st.divider()