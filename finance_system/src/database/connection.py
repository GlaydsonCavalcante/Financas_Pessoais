import sqlite3
import os
import logging
from pathlib import Path

# Configuração de Log para rastreabilidade
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- PARAMETRIZAÇÃO DO USUÁRIO ---
# Caminho alvo no Google Drive
DRIVE_PATH = Path(r"G:\Meu Drive\4. Registros\Glaydson\Orçamento\db")
DB_FILENAME = "finance_abs.db"

class DatabaseConnection:
    """
    Singleton responsável pela conexão com o SQLite.
    Gerencia a resiliência do caminho do arquivo (Drive vs Local).
    """
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseConnection, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.db_path = self._resolve_db_path()
        self._init_schema()
        self._initialized = True

    def _resolve_db_path(self) -> Path:
        """
        Tenta usar o caminho do G: Drive. 
        Se falhar (drive não montado), usa pasta local 'data/'.
        """
        try:
            # Tenta criar o diretório no Drive se não existir
            if not DRIVE_PATH.exists():
                DRIVE_PATH.mkdir(parents=True, exist_ok=True)
                logger.info(f"Diretório criado no Drive: {DRIVE_PATH}")
            
            target = DRIVE_PATH / DB_FILENAME
            logger.info(f"Conectado ao Banco Principal: {target}")
            return target
            
        except OSError as e:
            logger.warning(f"Google Drive inacessível ({e}). Usando banco local de fallback.")
            
            # Fallback Local
            local_dir = Path("data")
            local_dir.mkdir(exist_ok=True)
            return local_dir / "finance_fallback.db"

    def get_connection(self) -> sqlite3.Connection:
        """Retorna uma nova conexão ativa."""
        return sqlite3.connect(self.db_path)

    def _init_schema(self):
        """Garante a existência das tabelas nucleares."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classification_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_term TEXT UNIQUE NOT NULL,
                target_category TEXT NOT NULL
            )
        ''')
        
        # Tabela Única e Absoluta de Transações
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                hash_id TEXT PRIMARY KEY,
                date DATE NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                source TEXT,
                category TEXT,
                is_manual BOOLEAN DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()

# Instância global para ser importada pelos Services
db_instance = DatabaseConnection()