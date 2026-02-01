# Financas_Pessoais - Flask
finance_system/
├── app.py                <-- (Novo) Controlador Flask
├── templates/            <-- (Novo) HTMLs
│   ├── base.html         <-- Layout padrão (menu, rodapé)
│   ├── home.html         <-- Visão geral
│   └── classify.html     <-- A tela de classificação
├── static/               <-- (Novo) CSS e JS
│   └── style.css
├── src/                  <-- (Mantém igual!)
└── db/                   <-- (Mantém igual)


# Financas_Pessoais - Streamlit
Robô para leitura de extratos e composição de orçamento mensal

finance_system/
├── app.py                     # (VIEW) Ponto de entrada (Main Router)
├── pages/                     # (VIEW) Telas do sistema
│   ├── 1_📥_Extratos.py       # Upload de CSV/TXT
│   ├── 2_📝_Emprestimos.py    # Nova tela de Cadastro Manual
│   ├── 3_🏷️_Classificacao.py  # Gestão de categorias
│   └── 4_📊_Dashboard.py      # Visão Gerencial
├── src/
│   ├── __init__.py
│   ├── database/              # (INFRA) Acesso a Dados
│   │   ├── __init__.py
│   │   ├── connection.py      # Gerenciador de conexão Singleton
│   │   └── repository.py      # CRUD genérico e especializado
│   ├── models/                # (MODEL) Definições de Dados
│   │   ├── __init__.py
│   │   ├── transaction.py     # Dataclass Transação
│   │   └── loan.py            # Dataclass Contrato de Empréstimo
│   ├── services/              # (CONTROLLER) Regras de Negócio Puras
│   │   ├── __init__.py
│   │   ├── importer_service.py # Orquestra leituras de arquivos
│   │   ├── loan_service.py     # Gera as parcelas futuras
│   │   └── categorizer.py      # Motor de Inteligência
│   └── utils/                 # (HELPERS)
│       ├── __init__.py
│       └── parsers.py         # Lógica de parsing (CSV, TXT) isolada
└── requirements.txt
