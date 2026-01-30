# Financas_Pessoais
Robô para leitura de extratos e composição de orçamento mensal

finance_system/
├── data/                   # Armazenamento local (SQLite e Arquivos temp)
│   └── finance.db
├── pages/
│   ├── 1_Importar.py
│   ├── 2_Classificar.py  <-- AQUI VOCÊ TRABALHA
│   └── 3_Regras.py       <-- AQUI VOCÊ GERENCIA
├── src/
│   ├── __init__.py
│   ├── categorizer.py  
│   ├── database.py
│   ├── models/             # (MODEL) Definições de Dados
│   │   ├── __init__.py
│   │   └── transaction.py  # Dataclass padronizada
│   ├── parsers/            # (LOGIC) Estratégias de ETL
│   │   ├── __init__.py
│   │   ├── interface.py    # Classe Abstrata (Protocol)
│   │   ├── strategy_csv.py # Parser Conta Corrente
│   │   ├── strategy_txt.py # Parser Cartão SISBB (Regex)
│   │   └── strategy_pdf.py # Parser Empréstimo
│   ├── controllers/        # (CONTROLLER) Orquestração
│   │   ├── __init__.py
│   │   └── importer.py     # Recebe arquivo -> Devolve Dados
│   └── utils/
│       ├── __init__.py
│       └── formatters.py   # Tratamento de moeda/data
├── app.py                  # (VIEW) Interface Streamlit
└── requirements.txt
