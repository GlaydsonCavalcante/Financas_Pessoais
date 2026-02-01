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

from src.services.categorizer_service import CategorizerService

st.set_page_config(page_title="Classificação", layout="wide")

service = CategorizerService()
CATEGORY_IGNORE = "⛔ IGNORADO"

st.title("🏷️ Classificação Inteligente")

# --- SIDEBAR: MEMÓRIA ---
with st.sidebar:
    st.header("📚 Memória")
    existing_cats = service.get_unique_categories()
    if not existing_cats.empty:
        clean_list = existing_cats[existing_cats['Categoria'] != CATEGORY_IGNORE]
        st.dataframe(clean_list, hide_index=True, use_container_width=True, height=400)

st.markdown("---")

# 3 ABAS AGORA
tab_pendencias, tab_lote, tab_ferias, tab_regras = st.tabs(["📝 Pendências", "📦 Em Lote (Rápido)", "🏖️ Modo Férias", "⚙️ Regras"])

# --- TAB 1: PENDÊNCIAS ---
with tab_pendencias:
    # 1. Executa auto-classificação primeiro
    auto_count = service.run_auto_classification()
    if auto_count > 0:
        st.toast(f"🤖 {auto_count} itens processados automaticamente!")

    # 2. Carrega pendências
    pending_df = service.get_pending_transactions()
    
    if pending_df.empty:
        st.success("✅ Tudo limpo! Nenhuma pendência.")
    else:
        st.info(f"Pendências Restantes: {len(pending_df)}")
        
        # --- LÓGICA DE ORDENAÇÃO INTELIGENTE (SIMPLIFICADA) ---
        # 1. Conta quantas vezes cada descrição aparece
        ranking = pending_df['description'].value_counts().reset_index()
        ranking.columns = ['description', 'count']
        
        # 2. Ordena por: Quantidade (Descendente) e depois Nome (Ascendente)
        ranking = ranking.sort_values(by=['count', 'description'], ascending=[False, True])
        
        # 3. Gera a lista final ordenada
        unique_descs = ranking['description'].tolist()
        
        # --- SELETOR SIMPLIFICADO ---
        # Removemos os botões de navegação e usamos apenas o selectbox
        selected_desc = st.selectbox(
            f"Selecione o item para classificar (Total: {len(unique_descs)}):", 
            unique_descs,
            key="sb_pendencias"
        )
        
        # --- FIM DA LÓGICA DE NAVEGAÇÃO ---

        col_list, col_action = st.columns([2, 1])
        
        with col_list:
            # Filtra os dados com base na seleção
            affected_rows = pending_df[pending_df['description'] == selected_desc].copy()
            st.markdown(f"**Ocorrências:** {len(affected_rows)}")
            
            # Formatação Visual da Tabela
            def format_source(val):
                val = str(val).lower()
                if 'csv' in val: return 'Conta Corrente'
                if 'card' in val or 'txt' in val: return 'Cartão Visa'
                if 'contrato' in val: return 'Empréstimo'
                return 'Outros'

            affected_rows['Origem'] = affected_rows['source'].apply(format_source)
            
            st.dataframe(
                affected_rows[['date', 'Origem', 'amount']], 
                column_config={
                    "date": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "amount": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                },
                use_container_width=True,
                hide_index=True
            )

        with col_action:
            # --- DETECTOR DE PARCELAMENTO OTIMIZADO ---
            is_parc, curr, total, clean_name = service.detect_installment(selected_desc)
            
            if is_parc and curr == 1 and total > 1:
                # Caixa de destaque visual
                with st.container(border=True):
                    st.warning(f"🧩 Parcelamento Detectado ({curr}/{total})")
                    
                    base_val = affected_rows.iloc[0]['amount']
                    total_val = base_val * total
                    
                    st.markdown(f"""
                    **Resumo da Unificação:**
                    * De: `R$ {base_val:,.2f}` (Parcela)
                    * Para: `R$ {total_val:,.2f}` (Total à Vista)
                    """)
                    
                    # --- NOVIDADE: ESCOLHA A CATEGORIA AQUI DENTRO ---
                    st.markdown("---")
                    st.caption("Já defina a categoria para finalizar:")
                    
                    # Reusa a lógica de categorias existentes
                    existing_cats_parc = service.get_unique_categories()
                    if not existing_cats_parc.empty:
                        opts_parc = existing_cats_parc[existing_cats_parc['Categoria'] != CATEGORY_IGNORE]['Categoria'].tolist()
                        opts_parc.sort()
                    else:
                        opts_parc = []
                        
                    parc_options = ["➕ Nova Categoria..."] + opts_parc
                    
                    # Key única para não conflitar com o outro seletor
                    sel_cat_parc = st.selectbox("Categoria (Unificação):", parc_options, key="cat_parc_unique")
                    
                    if sel_cat_parc == "➕ Nova Categoria...":
                        final_cat_parc = st.text_input("Nome da Nova Categoria:", key="txt_parc_unique")
                    else:
                        final_cat_parc = sel_cat_parc
                    
                    # BOTÃO ÚNICO PODEROSO
                    if st.button("⚡ Unificar, Classificar & Ignorar Futuros", type="primary"):
                        if not cat_parc:
                            st.error("É obrigatório escolher uma categoria para unificar.")
                        else:
                            # 1. Aplica Unificação JÁ COM A CATEGORIA
                            # Isso evita o "Fantasma" pois faz tudo num único acesso ao banco
                            for idx, row in affected_rows.iterrows():
                                service.unify_installments(
                                    hash_id=row['hash_id'], 
                                    description=row['description'], 
                                    amount=row['amount'], 
                                    total_parc=total, 
                                    clean_desc=clean_name,
                                    category=cat_parc # <--- O SEGREDO ESTÁ AQUI
                                )
                            
                            # 2. Cria regra para bloquear futuros
                            service.create_rule(clean_name, CATEGORY_IGNORE)
                            
                            st.success("Resolvido e Classificado!")
                            st.session_state['current_index'] = 0 
                            
                            # Limpa cache para garantir que a tela atualize com o dado novo do banco
                            st.cache_data.clear()
                            st.rerun()

            # -------------------------------

            with st.container(border=True):
                st.subheader("Decisão")
                
                apply_mode = st.radio(
                    "Alcance:",
                    ["Criar Regra (Todo Histórico)", "Apenas estes (Pontual)"],
                    horizontal=True
                )
                
                # --- AUTOCOMPLETE INTELIGENTE ---
                # 1. Busca categorias já existentes na memória do sistema
                existing_cats = service.get_unique_categories()
                
                # Lista de opções: Categorias existentes + Opção de criar nova
                if not existing_cats.empty:
                    # Remove '⛔ IGNORADO' da lista de sugestões úteis (opcional)
                    options = existing_cats[existing_cats['Categoria'] != CATEGORY_IGNORE]['Categoria'].tolist()
                    options.sort()
                else:
                    options = []
                
                # Adiciona opção especial no topo ou fim
                NEW_CAT_LABEL = "➕ Nova Categoria..."
                final_options = [NEW_CAT_LABEL] + options
                
                # O Selectbox funciona como o "Sugestor"
                selected_category_option = st.selectbox(
                    "Categoria:", 
                    final_options,
                    index=0, # Padrão: Nova Categoria (ou pode mudar para index=None para forçar escolha)
                    help="Selecione uma existente ou crie uma nova."
                )
                
                # Lógica de decisão: Se escolheu "Nova", mostra campo de texto. Se não, usa a escolhida.
                if selected_category_option == NEW_CAT_LABEL:
                    new_category = st.text_input("Digite o nome da nova categoria:", placeholder="Ex: Assinaturas")
                else:
                    new_category = selected_category_option
                    # Mostra um feedback visual
                    st.info(f"Usando categoria existente: **{new_category}**")

                # --------------------------------
                
                c1, c2 = st.columns([1, 1]) # Layout ajustado
                
                # --- AÇÃO DE SALVAR ---
                # Agora o botão está sozinho, pois o input já foi resolvido acima
                if st.button("💾 Salvar Classificação", type="primary", use_container_width=True):
                    if not new_category:
                        st.error("Por favor, defina uma categoria.")
                    else:
                        if "Criar Regra" in apply_mode:
                            service.create_rule(selected_desc, new_category)
                        else:
                            for hash_id in affected_rows['hash_id']:
                                service.manual_update(hash_id, new_category)
                        
                        st.success(f"Salvo como: {new_category}")
                        st.rerun()

                st.markdown("---")
                
                # --- AÇÃO DE IGNORAR ---
                if st.button(f"{CATEGORY_IGNORE}", use_container_width=True):
                    if "Criar Regra" in apply_mode:
                        service.create_rule(selected_desc, CATEGORY_IGNORE)
                    else:
                        for hash_id in affected_rows['hash_id']:
                            service.manual_update(hash_id, CATEGORY_IGNORE)
                    st.rerun()

# --- TAB 2: MODO FÉRIAS (NOVO) ---
with tab_ferias:
    st.markdown("### 🏖️ Classificação em Massa: Viagens")
    st.info("Define como **'Férias'** tudo que aconteceu na data selecionada, **EXCETO** contas recorrentes (que existem em outros meses, como Escola, Aluguel, etc).")
    
    c_dates, c_btn = st.columns([3, 1])
    with c_dates:
        vacation_range = st.date_input(
            "Período da Viagem",
            value=(date.today() - timedelta(days=7), date.today()),
            format="DD/MM/YYYY"
        )
    
    if len(vacation_range) == 2:
        start, end = vacation_range
        
        if c_btn.button("🔍 Analisar Período"):
            # Roda a lógica de previsão
            to_update_df, protected_df = service.preview_vacation_mode(start, end)
            
            # Salva na sessão para persistir após reload
            st.session_state['vacation_preview'] = to_update_df
            st.session_state['vacation_protected'] = protected_df
            st.session_state['vacation_ready'] = True

    # Mostra Resultados da Análise
    if st.session_state.get('vacation_ready'):
        to_update = st.session_state['vacation_preview']
        protected = st.session_state['vacation_protected']
        
        c_ok, c_no = st.columns(2)
        
        with c_ok:
            st.success(f"🎯 Serão transformados em Férias ({len(to_update)})")
            st.caption("Gastos pontuais exclusivos deste período.")
            if not to_update.empty:
                st.dataframe(to_update[['Data', 'Descrição', 'Valor']], hide_index=True, use_container_width=True)
            else:
                st.write("Nenhum gasto exclusivo encontrado.")

        with c_no:
            st.warning(f"🛡️ Serão Mantidos/Protegidos ({len(protected)})")
            st.caption("Contas recorrentes identificadas (existem fora da viagem).")
            if not protected.empty:
                st.dataframe(protected[['Data', 'Descrição', 'Valor']], hide_index=True, use_container_width=True)
                
        st.divider()
        
        if not to_update.empty:
            if st.button(f"🚀 Confirmar: Classificar {len(to_update)} itens como Férias", type="primary", use_container_width=True):
                count = service.apply_vacation_batch(to_update['hash_id'].tolist())
                st.balloons()
                st.success(f"{count} transações atualizadas com sucesso!")
                # Limpa sessão
                del st.session_state['vacation_ready']
                del st.session_state['vacation_preview']
                st.rerun()

# --- TAB 3: REGRAS (Mantivemos idêntico) ---
with tab_regras:
    st.markdown("### Regras Ativas")
    rules_df = service.get_rules()
    if not rules_df.empty:
        for index, row in rules_df.iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1: st.text(row['match_term'])
            with c2: st.caption(row['target_category'])
            with c3:
                if st.button("🗑️", key=f"del_{index}"):
                    service.delete_rule(row['match_term'])
                    st.rerun()
            st.divider()

# --- TAB 2: CLASSIFICAÇÃO EM LOTE ---
with tab_lote:
    st.markdown("### 📦 Agrupamento por Similaridade")
    st.caption("Selecione múltiplos itens da lista abaixo para categorizar todos de uma vez.")
    
    # 1. Busca dados agrupados
    df_grouped = service.get_grouped_pending()
    
    if df_grouped.empty:
        st.success("Nada para agrupar! Tudo limpo.")
    else:
        # 2. Prepara o DataFrame para edição
        # Adiciona coluna de seleção (Checkbox)
        df_grouped.insert(0, "Selecionar", False)
        
        # Configuração visual das colunas
        edited_df = st.data_editor(
            df_grouped,
            column_config={
                "Selecionar": st.column_config.CheckboxColumn(
                    "Agrupar",
                    help="Selecione para aplicar a ação em massa",
                    default=False,
                ),
                "description": st.column_config.TextColumn("Descrição Original", disabled=True),
                "qtd": st.column_config.NumberColumn("Qtd", help="Quantas vezes aparece", disabled=True),
                "avg_amount": st.column_config.NumberColumn("Valor Médio", format="R$ %.2f", disabled=True)
            },
            hide_index=True,
            use_container_width=True,
            height=500
        )
        
        # 3. Lógica de Ação
        # Filtra apenas os marcados com True
        selected_rows = edited_df[edited_df["Selecionar"] == True]
        
        st.divider()
        
        if not selected_rows.empty:
            count_items = len(selected_rows)
            total_affected = selected_rows['qtd'].sum()
            
            st.info(f"Selecionados: **{count_items}** descrições (afetará **{total_affected}** transações).")
            
            c1, c2, c3 = st.columns([2, 1, 1])
            
            with c1:
                # Reusa lógica de categorias existentes
                existing_cats = service.get_unique_categories()
                
                # Pega as categorias normais (sem o ignorado)
                valid_cats = existing_cats[existing_cats['Categoria'] != CATEGORY_IGNORE]['Categoria'].tolist()
                valid_cats.sort()
                
                # CORREÇÃO: Adiciona "IGNORADO" explicitamente no topo da lista
                opts = ["", CATEGORY_IGNORE] + valid_cats
                
                batch_category = st.selectbox("Aplicar Categoria:", opts, key="sb_batch")
                
            with c2:
                st.write("") # Espaçamento
                st.write("") 
                create_rule_batch = st.checkbox("Criar Regra?", value=True, help="Aplica para o futuro também")
                
            with c3:
                st.write("") # Espaçamento
                st.write("") 
                if st.button("🚀 Aplicar em Massa", type="primary"):
                    if not batch_category:
                        st.error("Escolha uma categoria.")
                    else:
                        descriptions_to_update = selected_rows['description'].tolist()
                        affected = service.apply_batch_by_description(
                            descriptions_to_update, 
                            batch_category, 
                            create_rule_batch
                        )
                        st.success(f"Feito! {affected} transações atualizadas.")
                        st.rerun()
        else:
            st.caption("Marque as caixas na tabela acima para habilitar as ações.")