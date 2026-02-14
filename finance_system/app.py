from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
import pandas as pd
from datetime import date, timedelta
import json
import urllib.parse

# Imports dos seus Serviços
from src.services.categorizer_service import CategorizerService
from src.services.importer_service import ImporterService
from src.services.loan_service import LoanService
from src.database.connection import db_instance
from src.services.budget_service import BudgetService
from src.services.ai_advisor import AIAdvisor

# Instancie o serviço junto com os outros:
ai_advisor = AIAdvisor()
app = Flask(__name__)
app.secret_key = 'chave_super_secreta_glaydson'

# Instâncias dos Serviços
cat_service = CategorizerService()
imp_service = ImporterService()
loan_service = LoanService()
budget_service = BudgetService()

CATEGORY_IGNORE = "⛔ IGNORADO"

# --- Context Global (Menu Lateral) ---
@app.context_processor
def inject_globals():
    return dict(
        pending_count=cat_service.get_pending_count(),
        today=date.today()
    )

# --- ROTAS ---

@app.route('/')
def home():
    return render_template('home.html')

# === 1. IMPORTAÇÃO ===
@app.route('/import', methods=['GET', 'POST'])
def import_files():
    results = None
    if request.method == 'POST':
        # Recebe lista de arquivos
        uploaded_files = request.files.getlist('files')
        
        # Patch Rápido: O ImporterService espera objetos com atributo .name
        # Os FileStorage do Flask têm .filename. Vamos ajustar dinamicamente.
        for f in uploaded_files:
            f.name = f.filename 
            
        if uploaded_files:
            try:
                # Chama seu serviço existente
                results = imp_service.process_files(uploaded_files)
                if results['saved'] > 0:
                    flash(f"Sucesso! {results['saved']} transações importadas.", "success")
                else:
                    flash("Arquivos processados, mas sem novos dados.", "warning")
            except Exception as e:
                flash(f"Erro na importação: {str(e)}", "danger")

    return render_template('import.html', results=results)

# === 2. CLASSIFICAÇÃO (Já tínhamos feito) ===
@app.route('/classify', methods=['GET'])
def classify():
    # 1. Recupera parâmetros (Aba, Ordenação, Datas de Férias)
    active_tab = request.args.get('tab', 'single')
    sort_by = request.args.get('sort', 'description')
    sort_dir = request.args.get('dir', 'asc')
    
    # Parâmetros exclusivos da Aba Férias
    vac_start = request.args.get('vac_start')
    vac_end = request.args.get('vac_end')
    
    # --- ABA 1: Pendências Individuais ---
    df_pending = cat_service.get_pending_transactions()
    
    unique_items = []
    current_item_data = None
    parcel_info = None
    transactions_detail = []
    
    if not df_pending.empty:
        # Ranking alfabético
        ranking = df_pending['description'].value_counts().reset_index()
        ranking.columns = ['description', 'count']
        ranking = ranking.sort_values(by='description', ascending=True)
        unique_items = ranking.to_dict('records')
        
        selected_desc = request.args.get('item')
        if not selected_desc and unique_items:
            selected_desc = unique_items[0]['description']
            
        if selected_desc:
            mask = df_pending['description'] == selected_desc
            transactions_detail = df_pending[mask].to_dict('records')
            current_item_data = {'description': selected_desc, 'count': len(transactions_detail)}

            is_parc, curr, total, clean_name = cat_service.detect_installment(selected_desc)
            if is_parc and curr == 1 and total > 1:
                base_val = transactions_detail[0]['amount']
                parcel_info = {
                    'current': curr, 'total': total, 
                    'total_value': base_val * total, 
                    'clean_name': clean_name
                }

    # --- ABA 2: Pendências em Lote ---
    df_batch = cat_service.get_grouped_pending()
    if not df_batch.empty:
        ascending = (sort_dir == 'asc')
        if sort_by == 'qtd':
            df_batch = df_batch.sort_values(by='qtd', ascending=ascending)
        elif sort_by == 'amount':
            df_batch = df_batch.sort_values(by='avg_amount', ascending=ascending)
        else:
            df_batch = df_batch.sort_values(by='description', ascending=ascending)
    batch_data = df_batch.to_dict('records') if not df_batch.empty else []

    # --- ABA 3: MODO FÉRIAS (NOVO) ---
    vacation_candidates = []
    vacation_protected = []
    
    if active_tab == 'vacation' and vac_start and vac_end:
        try:
            # Chama o serviço que você já tem (preview_vacation_mode)
            df_to_update, df_protected = cat_service.preview_vacation_mode(vac_start, vac_end)
            
            if not df_to_update.empty:
                vacation_candidates = df_to_update.to_dict('records')
            
            if not df_protected.empty:
                vacation_protected = df_protected.to_dict('records')
                
        except Exception as e:
            flash(f"Erro ao buscar período de férias: {e}", "danger")

    # --- GERAL ---
    cats_df = cat_service.get_unique_categories()
    categories = [CATEGORY_IGNORE] + cats_df[cats_df['Categoria'] != CATEGORY_IGNORE]['Categoria'].tolist()

    return render_template(
        'classify.html',
        active_tab=active_tab,
        unique_items=unique_items,
        selected_item=request.args.get('item'),
        current_item=current_item_data,
        transactions=transactions_detail,
        parcel_info=parcel_info,
        batch_data=batch_data,
        # Dados de Férias
        vacation_candidates=vacation_candidates,
        vacation_protected=vacation_protected,
        vac_start=vac_start,
        vac_end=vac_end,
        # Comuns
        categories=categories,
        total_pending=len(df_pending),
        current_sort=sort_by,
        current_dir=sort_dir
    )

@app.route('/classify/batch', methods=['POST'])
def classify_batch():
    """Processa a ação da Aba de Lote (Mantendo a Ordenação)"""
    
    # 1. Recupera o estado atual da ordenação (Inputs Ocultos)
    current_sort = request.form.get('keep_sort', 'description')
    current_dir = request.form.get('keep_dir', 'asc')

    try:
        selected_descriptions = request.form.getlist('selected_descriptions')
        
        raw_category = request.form.get('batch_category')
        new_category = request.form.get('new_batch_category')
        final_category = new_category if raw_category == 'NEW' else raw_category
        
        create_rule = 'create_rule_batch' in request.form
        
        if not selected_descriptions:
            flash("Nenhum item selecionado.", "warning")
        elif not final_category:
            flash("Selecione ou digite uma categoria.", "warning")
        else:
            count = cat_service.apply_batch_by_description(selected_descriptions, final_category, create_rule)
            flash(f"Sucesso! {count} itens classificados como '{final_category}'.", "success")
            
    except Exception as e:
        flash(f"Erro: {e}", "danger")
        
    # 2. Redireciona mantendo a aba E a ordenação
    return redirect(url_for('classify', tab='batch', sort=current_sort, dir=current_dir))

@app.route('/classify/vacation_apply', methods=['POST'])
def vacation_apply():
    """Aplica a categoria 'Férias' nos itens selecionados."""
    try:
        # Recupera IDs marcados no checkbox
        selected_hashes = request.form.getlist('selected_hashes')
        
        if not selected_hashes:
            flash("Nenhum item selecionado para aplicar férias.", "warning")
        else:
            count = cat_service.apply_vacation_batch(selected_hashes)
            flash(f"Sucesso! {count} lançamentos foram marcados como 'Férias'.", "success")
            
    except Exception as e:
        flash(f"Erro ao aplicar férias: {e}", "danger")
        
    # Volta para a aba de férias (sem as datas para limpar a tela ou mantenha se preferir)
    return redirect(url_for('classify', tab='vacation'))

@app.route('/classify/action', methods=['POST'])
def classify_action():
    # ... (Mesmo código que fizemos no passo anterior) ...
    # Para brevidade, replique a lógica de salvar/unificar aqui
    # Copie do passo anterior ou me avise se precisar que eu reescreva inteiro
    description = request.form.get('description')
    category = request.form.get('category')
    new_cat = request.form.get('new_category')
    action = request.form.get('action_type')
    apply_rule = 'apply_rule' in request.form
    
    final_cat = new_cat if new_cat else category
    
    if action == 'unify':
        h_id = request.form.get('first_hash')
        amt = float(request.form.get('amount'))
        tot = int(request.form.get('total_parc'))
        clean = request.form.get('clean_name')
        cat_service.unify_installments(h_id, description, amt, tot, clean, final_cat)
        cat_service.create_rule(clean, CATEGORY_IGNORE)
        flash("Unificado com sucesso!", "success")
        
    elif action == 'save' or action == 'ignore':
        target = CATEGORY_IGNORE if action == 'ignore' else final_cat
        if apply_rule:
            cat_service.create_rule(description, target)
        else:
            df = cat_service.get_pending_transactions()
            ids = df[df['description'] == description]['hash_id'].tolist()
            for h in ids:
                cat_service.manual_update(h, target)
        flash("Classificado!", "success")

    return redirect(url_for('classify'))

# === 3. EMPRÉSTIMOS ===
@app.route('/loans', methods=['GET', 'POST'])
def loans():
    plan = None
    total_value = 0
    
    # Valores padrão para manter o formulário preenchido
    form_data = {
        'name': '',
        'installments': 12,
        'amount': 0.0,
        'first_date': date.today().strftime('%Y-%m-%d')
    }

    if request.method == 'POST':
        try:
            action = request.form.get('action')
            
            # Captura dados do form
            name = request.form.get('name')
            installments = int(request.form.get('installments'))
            amount = float(request.form.get('amount'))
            first_date_str = request.form.get('first_date')
            first_date = date.fromisoformat(first_date_str)

            # Atualiza form_data para repassar ao template (UX)
            form_data = {
                'name': name,
                'installments': installments,
                'amount': amount,
                'first_date': first_date_str
            }
            
            # Gera os objetos Transaction em memória
            # O LoanService retorna objetos, não dicionários
            plan_objs = loan_service.generate_plan(name, amount, first_date, installments)
            
            if action == 'preview':
                # CONVERSÃO CRÍTICA:
                # Transforma Objeto -> Dict com chaves em INGLÊS compatíveis com o HTML
                plan = []
                for t in plan_objs:
                    plan.append({
                        'date': t.date.strftime('%d/%m/%Y'), # Formata data BR
                        'description': t.description,
                        'amount': t.amount
                    })
                
                # Soma usando o valor float dos objetos originais
                total_value = sum(t.amount for t in plan_objs)
                    
            elif action == 'save':
                saved_count = loan_service.save_plan(plan_objs)
                flash(f"Contrato salvo com sucesso! {saved_count} parcelas geradas.", "success")
                return redirect(url_for('loans'))
                
        except ValueError as e:
            flash(f"Erro nos dados: Verifique se todos os campos estão preenchidos. ({e})", "danger")
        except Exception as e:
            flash(f"Erro interno: {str(e)}", "danger")

    # Passamos form_data para manter os campos preenchidos após o clique
    return render_template(
        'loan.html', 
        plan=plan, 
        total_value=total_value, 
        form_data=form_data 
    )

# === 4. DASHBOARD ===
@app.route('/dashboard')
def dashboard():
    today = date.today()
    current_year = today.year
    current_month = today.month
    
    req_date = request.args.get('ref_date')
    if req_date:
        ref_date = date.fromisoformat(req_date)
        current_year = ref_date.year
        current_month = ref_date.month
    else:
        ref_date = today

    overview = budget_service.get_dashboard_overview(current_year, current_month)
    
    # KPIs Básicos de Saldo
    conn = db_instance.get_connection()
    total_income = pd.read_sql_query("SELECT SUM(amount) FROM transactions WHERE amount > 0", conn).iloc[0,0] or 0.0
    total_expense = pd.read_sql_query("SELECT SUM(amount) FROM transactions WHERE amount < 0", conn).iloc[0,0] or 0.0
    conn.close()
    
    real_balance = total_income + total_expense
    provisions_balance = overview['kpis']['provisions_balance']
    free_balance = real_balance - provisions_balance
    
    # Consolidação dos Dados
    kpis = {
        'real_balance': int(real_balance),
        'provisions_balance': int(provisions_balance),
        'free_balance': int(free_balance),
        
        # Dados do Mês (Vindos do Serviço Aprimorado)
        'monthly_income': overview['kpis']['income'],
        'total_spent': overview['kpis']['total_spent'], # Novo
        'cash_burn': overview['kpis']['cash_burn'],     # Novo (Entrada - Saída Real)
        'economic_result': overview['kpis']['economic_result']
    }

    return render_template(
        'dashboard.html',
        kpis=kpis,
        rows=overview['rows'],
        ref_date=ref_date,
        today=today
    )

# === 5. METAS E ORÇAMENTO ===
# === 5. METAS E ORÇAMENTO (CORRIGIDO) ===
@app.route('/goals', methods=['GET', 'POST'])
def goals():
    today = date.today()
    year = int(request.args.get('year', today.year))
    month = int(request.args.get('month', today.month))

    # 1. GARANTIA: Definir categorias logo no início
    cats_df = cat_service.get_unique_categories()
    all_categories = cats_df[cats_df['Categoria'] != CATEGORY_IGNORE]['Categoria'].tolist()

    if request.method == 'POST':
        action = request.form.get('action')
        month = int(request.form.get('month', month))
        
        if action == 'set_goal':
            cat = request.form.get('category')
            val = float(request.form.get('amount'))
            budget_service.set_annual_goal(year, cat, val)
            flash(f"Meta de {cat} atualizada!", "success")
            
        elif action == 'add_provision':
            cat = request.form.get('category')
            val = float(request.form.get('amount'))
            memo = request.form.get('memo')
            budget_service.add_provision(cat, val, memo)
            flash(f"Provisão de {cat} registrada.", "info")
        
        return redirect(url_for('goals', year=year, month=month))

    # 2. Busca dados para as abas
    summary = budget_service.get_budget_summary(year)
    monthly_status = budget_service.get_dashboard_overview(year, month)
    
    return render_template('goals.html', 
                           summary=summary, 
                           monthly_status=monthly_status,
                           all_categories=all_categories,
                           year=year, 
                           month=month)

# --- ROTAS DO CONSELHEIRO ---

@app.route('/goals/auto', methods=['POST'])
def auto_budget():
    year = int(request.form.get('year'))
    count = budget_service.generate_baseline_from_history(year)
    flash(f"Orçamento Base criado! {count} categorias foram calculadas usando a média de 2024/25.", "success")
    return redirect(url_for('goals', year=year))

@app.route('/goals/force', methods=['POST'])
def force_curve():
    year = int(request.form.get('year'))
    savings_pct = float(request.form.get('savings_pct', 0))
    
    report = budget_service.apply_forced_curve(year, savings_pct)
    
    if not report['reductions']:
        flash("Parabéns! Seu orçamento atual já cabe na sua renda (ou você não tem renda cadastrada).", "success")
        return redirect(url_for('goals', year=year))
    
    # Renderiza a página de metas passando o relatório de cortes
    summary = budget_service.get_budget_summary(year)
    cats_df = cat_service.get_unique_categories()
    all_categories = cats_df[cats_df['Categoria'] != CATEGORY_IGNORE]['Categoria'].tolist()
    
    return render_template('goals.html', summary=summary, all_categories=all_categories, year=year, reduction_report=report)

# === ROTA DO CONSELHEIRO IA ===
@app.route('/goals/advisor', methods=['GET', 'POST'])
def goals_advisor():
    year = int(request.args.get('year', date.today().year))
    
    if request.method == 'GET':
        # 1. Gera os cenários (Matemática + IA)
        scenarios = ai_advisor.generate_scenarios()
        return render_template('advisor_modal.html', scenarios=scenarios, year=year)
    
    elif request.method == 'POST':
        # 2. Aplica o cenário escolhido
        chosen_level = request.form.get('chosen_level') # 'level_1', 'level_2', or 'level_3'
        
        # Recalcula contexto rápido (ou poderia passar via form, mas recalcular é mais seguro)
        scenarios = ai_advisor.generate_scenarios()
        categories = scenarios['data']['categories']
        values = scenarios['data'][chosen_level]
        
        # Salva no Banco
        for cat, val in zip(categories, values):
            # Transforma mensal em anual (O sistema trabalha com anual)
            annual_val = val * 12
            budget_service.set_annual_goal(year, cat, annual_val)
            
        flash(f"Plano aplicado com sucesso! Suas metas foram ajustadas.", "success")
        return redirect(url_for('goals', year=year))

# === ROTAS DE GESTÃO ORÇAMENTÁRIA (NOVAS) ===

@app.route('/goals/init_history', methods=['POST'])
def init_history():
    year = int(request.form.get('year'))
    # Usa 2025 como base para preencher 2026
    count = budget_service.init_budget_from_history(target_year=year, base_year=2025)
    flash(f"Orçamento iniciado! {count} categorias copiadas de 2025.", "success")
    return redirect(url_for('goals', year=year))

@app.route('/goals/lock', methods=['POST'])
def toggle_lock():
    year = int(request.form.get('year'))
    month = int(request.form.get('month', date.today().month)) 
    category = request.form.get('category')
    budget_service.toggle_lock(year, category)
    return redirect(url_for('goals', year=year, month=month)) 

@app.route('/goals/curve', methods=['POST'])
def apply_curve():
    """Aplica a Curva 1 (Equilíbrio) ou 2 (Prosperidade)"""
    year = int(request.form.get('year'))
    month = int(request.form.get('month', date.today().month)) 
    curve_type = int(request.form.get('curve_type')) # 1 ou 2
    
    result = budget_service.apply_curve(year, curve_type, month=month)
    
    if "error" in result:
        flash(result['error'], "danger")
    else:
        flash("Curva aplicada com sucesso! Categorias destravadas foram ajustadas.", "success")
        
    return redirect(url_for('goals', year=year))

# === ROTAS DO ESPECIALISTA (GRÁFICO E CHAT) ===
@app.route('/api/category_history/<category>')
def category_history_api(category):
    # Descodifica a URL (Ex: Compras%20Gen%C3%A9ricas -> Compras Genéricas)
    decoded_category = urllib.parse.unquote(category)
    try:
        conn = db_instance.get_connection()
        df = pd.read_sql_query("""
            SELECT strftime('%Y', date) as ano, strftime('%m', date) as mes, SUM(ABS(amount)) as valor
            FROM transactions 
            WHERE category = ? AND strftime('%Y', date) IN ('2024', '2025', '2026') AND amount < 0
            GROUP BY ano, mes
        """, conn, params=(decoded_category,)) # USE A VARIÁVEL DECODIFICADA
        conn.close()
        
        data = {'2024': [0]*12, '2025': [0]*12, '2026': [0]*12}
        
        if not df.empty:
            for _, row in df.iterrows():
                try:
                    idx = int(row['mes']) - 1
                    ano = row['ano']
                    if ano in data:
                        data[ano][idx] = row['valor']
                except:
                    continue
                    
        return jsonify(data)
    except Exception as e:
        print(f"Erro na API do Gráfico: {e}")
        return jsonify({'2024': [], '2025': [], '2026': []}) # Retorna vazio para não quebrar o JS
    
@app.route('/api/chat/init', methods=['POST'])
def chat_init():
    """Inicia o chat (ou recupera histórico)"""
    category = request.json.get('category')
    # Se já tem histórico, retorna ele. Se não, a IA gera a primeira análise.
    history = ai_advisor.get_chat_history(category)
    if not history:
        initial_analysis = ai_advisor.ask_specialist(category) # Gera msg inicial
        return jsonify([{'role': 'model', 'parts': [initial_analysis]}])
    return jsonify(history)

@app.route('/api/chat/send', methods=['POST'])
def chat_send():
    """Envia pergunta do usuário"""
    data = request.json
    category = data.get('category')
    message = data.get('message')
    response = ai_advisor.ask_specialist(category, message)
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(debug=True, port=5000)