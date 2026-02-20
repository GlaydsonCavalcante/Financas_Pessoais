# 🧭 GPS Financeiro - Sistema Avançado de Finanças Pessoais

O **GPS Financeiro** não é apenas um rastreador de despesas; é um motor de planejamento orçamentário estratégico. Ele ingere extratos brutos, categoriza os dados, identifica parcelamentos e utiliza o conceito de **Curvas de Sobrevivência (C1 e C2)** para forçar um orçamento realista baseado na renda líquida ou planejada do usuário.

---

## 📑 Índice

1. [PARTE 1: Arquitetura e Setup](https://www.google.com/search?q=%23-parte-1-arquitetura-e-setup)
2. [PARTE 2: O Motor de Negócios (Core Logic)](https://www.google.com/search?q=%23-parte-2-o-motor-de-neg%C3%B3cios-core-logic)
3. [PARTE 3: Integração IA, UI e Extensibilidade](https://www.google.com/search?q=%23-parte-3-integra%C3%A7%C3%A3o-ia-ui-e-extensibilidade)

---

## 📦 PARTE 1: Arquitetura e Setup

### 1.1. Arquitetura do Sistema

O projeto adota uma arquitetura baseada em **MVC (Model-View-Controller)** adaptada, com forte separação de responsabilidades (SoC - Separation of Concerns). O Flask atua como roteador (View/Controller de borda), enquanto a regra de negócio pesada fica na camada de `Services`.

```text
finance_system/
├── app.py                     # (ROUTER/VIEW) Controladores Flask e Rotas API
├── templates/                 # (VIEW) Templates Jinja2 (HTML)
├── static/                    # (VIEW) CSS e assets estáticos
├── src/
│   ├── database/              # (INFRA)
│   │   ├── connection.py      # Singleton do SQLite
│   │   └── repository.py      # Data Access Layer (Pandas + SQL)
│   ├── models/                # (MODEL)
│   │   ├── transaction.py     # Dataclass base
│   │   └── loan.py            # Dataclass de empréstimos
│   ├── services/              # (BUSINESS LOGIC) - O Coração do Sistema
│   │   ├── ai_advisor.py      # Integração com API Google Gemini (Consultor)
│   │   ├── budget_service.py  # Motor de Cálculos (GPS, Curvas C1/C2)
│   │   ├── categorizer...py   # Motor de classificação e regex
│   │   ├── importer_service.py# Ingestão de CSV/TXT/PDF
│   │   └── loan_service.py    # Projeções de amortização/passivos
│   └── utils/                 # (HELPERS)
│       └── parsers.py         # Higienização de texto e datas
└── requirements.txt

```

### 1.2. Instalação e Execução Local

Para o desenvolvedor que está assumindo o projeto, siga os passos abaixo:

1. **Clone o repositório** e acesse a pasta raiz.
2. **Crie o ambiente virtual:**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

```


3. **Instale as dependências:**
```bash
pip install -r requirements.txt

```


4. **Variáveis de Ambiente (`.env`):**
Crie um arquivo `.env` na raiz do projeto com as seguintes chaves:
```env
GEMINI_API_KEY=sua_chave_do_google_aqui
GEMINI_MODEL=gemini-2.5-flash

```


5. **Inicie o servidor Flask:**
```bash
python app.py

```


Acesse: `http://localhost:5000`

---

## 🧠 PARTE 2: O Motor de Negócios (Core Logic)

Para dar manutenção no projeto, é fundamental entender os três principais serviços e como os dados fluem. O sistema não deleta registros facilmente; ele baseia-se em *Hashes Determinísticos* para evitar duplicidades (`hash_id`).

### 2.1. O Guardião de Dados: `TransactionRepository`

Localizado em `src/database/repository.py`. Nenhuma consulta SQL complexa deve vazar para a UI ou para outros serviços.

* **Prioridade de Receita (Crucial):** No método `get_year_financials`, o sistema tenta buscar primeiro a **Meta de Receita** (o que o usuário planejou ganhar). Se o usuário não tiver configurado uma meta de salário, o sistema faz *fallback* para a **Renda Realizada** (transações do banco). Isso estabiliza as projeções anuais.
* **Filtro Automático:** O repositório já separa o que é `Despesa` do que é `Receita` identificando termos como `('Receita', 'Salário', 'Entrada', 'Rendimento')` na coluna de categorias.

### 2.2. A Inteligência Financeira: `BudgetService`

Este é o arquivo mais complexo (`src/services/budget_service.py`). Ele materializa o conceito do GPS.

* **Cálculo da Cota Mensal (YTD):** O sistema não olha apenas para o mês isolado. Ele pega a Meta Anual, subtrai tudo o que *já foi gasto no ano* e divide o saldo restante pelos meses que faltam. Isso permite "recompensar" o usuário num mês se ele economizou nos anteriores.
* **O Cofre (`Provisions`):** Dinheiro "guardado" não é dinheiro gasto. O sistema lê a tabela `budget_provisions` e trata esse valor como "coberto", protegendo esse montante de aparecer como saldo livre.
* **Motor de Curvas Forçadas (`apply_curve`):**
* **Curva 1 (Equilíbrio):** Limita os gastos a 100% da Renda.
* **Curva 2 (Prosperidade):** Limita os gastos a 90% da Renda.
* **A Lógica do Corte:** O sistema soma todas as despesas **Travadas** (`is_locked == True`), como Aluguel e Energia. Em seguida, subtrai esse montante da Renda. O saldo restante é distribuído de forma **proporcional** (usando fator de redução) apenas nas categorias destravadas. *Nota: Metas de Receita nunca sofrem redução pelas Curvas.*



### 2.3. O Motor Analítico: `CategorizerService`

* **Identificação de Parcelas:** Analisa strings (`descrição`) buscando padrões Regex como `(01/12)`.
* **Modo Férias:** Permite marcar em lote compras de um período específico para não contaminar a análise do custo de vida padrão.
* **Regras de Lote:** Quando um item é classificado, o sistema pode gerar uma regra na tabela `classification_rules` para que, no futuro, o `ImporterService` já categorize automaticamente.

---

## 🤖 PARTE 3: Integração IA, UI e Extensibilidade

### 3.1. Conselheiro de IA (`AIAdvisor`)

A classe `AIAdvisor` (`src/services/ai_advisor.py`) transforma o Google Gemini em um CFO pessoal.

* **Contexto Injetado:** Ao invés de mandar um prompt genérico, o backend constrói um DataFrame em texto contendo todo o histórico de transações reais daquela categoria específica (2024-2026), junto com a Meta atual.
* **Memória:** As conversas são salvas na tabela `ai_chat_logs` vinculadas à categoria. A rota Flask `/api/chat/send` recupera esse histórico para manter o contexto.

### 3.2. Estrutura de Rotas (`app.py`)

O arquivo central utiliza Jinja2 para renderização do lado do servidor (SSR).

* `@app.route('/import')`: Lida com múltiplos arquivos, contornando a limitação do objeto `FileStorage` do Flask para ser compatível com os `parsers`.
* `@app.route('/classify')`: Interface principal de triagem. Possui 3 sub-abas (Individual, Lote, Férias) processadas no mesmo controller via *query parameters*.
* `@app.route('/goals')`: Onde o usuário insere as Metas de Despesa e Receita, Trava categorias e aplica as Curvas.

### 3.3. Próximos Passos & Extensibilidade (Para o Novo Dev)

Se você for implementar novas funcionalidades, siga estas diretrizes arquiteturais:

1. **Novos Dashboards:** Não escreva queries no `app.py`. Crie um método no `TransactionRepository` (ex: `get_cashflow_by_period`) e trate a lógica em `BudgetService`.
2. **Novos Tipos de Arquivo:** Adicione as lógicas de parsing de novos bancos (Nubank, Itaú, Inter) dentro de `src/utils/parsers.py`. O `ImporterService` consome esses *parsers* dinamicamente.
3. **Melhoria Sugerida (Roadmap):** * Implementar WebSockets (ex: Flask-SocketIO) no chat do `AIAdvisor` para streaming de respostas.
* Adicionar autenticação (atualmente o sistema é *Single-Tenant* local).
* Refatorar a captura de Erros do Banco de Dados para um Middleware Global no Flask.



---

*Documentação atualizada em: Fevereiro de 2026.*