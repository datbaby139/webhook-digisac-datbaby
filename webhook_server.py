"""
SERVIDOR WEBHOOK - DIGISAC → VISUAL ASA
Recebe confirmações do Digisac e confirma automaticamente no Visual ASA
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
import os
import logging
import json

# Configurar logging PRIMEIRO
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== CONFIGURAÇÃO POSTGRESQL =====
# IMPORTANTE: Sistema funciona SEM banco! Banco é OPCIONAL.
# Para ativar: definir variável de ambiente DATABASE_URL

USE_DATABASE = False  # Flag de controle
db_conn = None

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    logger.info("✅ psycopg2 importado com sucesso")
    
    # Verificar se tem DATABASE_URL configurada
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    if DATABASE_URL:
        # Ajustar URL se vier do Render (postgres:// → postgresql://)
        if DATABASE_URL.startswith('postgres://'):
            DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        
        USE_DATABASE = True
        logger.info("✅ PostgreSQL disponível - banco será usado quando ativado")
    else:
        logger.info("ℹ️  DATABASE_URL não configurada - usando modo JSON")
        
except ImportError as e:
    logger.error(f"❌ Erro ao importar psycopg2: {e}")
    logger.info("ℹ️  psycopg2 não instalado - usando modo JSON")
except Exception as e:
    logger.error(f"❌ Erro inesperado ao configurar PostgreSQL: {e}")
    logger.info("ℹ️  Usando modo JSON")

# ===== FIM CONFIGURAÇÃO POSTGRESQL =====

# ===== FUNÇÃO AUXILIAR PARA NORMALIZAR TELEFONES =====
def normalizar_telefone(telefone):
    """
    Remove hífens, espaços e caracteres especiais do telefone.
    Necessário porque:
    - CSV envia: 55-21-99083-0202 (com hífens)
    - Digisac retorna: 5521990830202 (sem hífens)
    """
    if not telefone:
        return ""
    # Remove tudo que não é número
    return ''.join(filter(str.isdigit, str(telefone)))

app = Flask(__name__)
CORS(app)  # Permitir requisições de qualquer origem

# ===== FUNÇÕES DO BANCO DE DADOS (DESATIVADAS POR PADRÃO) =====

def get_db_connection():
    """Conecta ao banco PostgreSQL. Retorna None se não configurado."""
    if not USE_DATABASE:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"❌ Erro ao conectar ao banco: {e}")
        return None

def init_database():
    """Cria tabelas se não existirem. Executado automaticamente se banco disponível."""
    if not USE_DATABASE:
        return False
    try:
        conn = get_db_connection()
        if not conn:
            return False
        cur = conn.cursor()
        
        # Tentar criar no schema public primeiro
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.confirmacoes (
                    id SERIAL PRIMARY KEY,
                    id_marcacao TEXT NOT NULL UNIQUE,
                    telefone TEXT,
                    nome_paciente TEXT,
                    data_consulta DATE,
                    hora TIME,
                    medico TEXT,
                    confirmado BOOLEAN DEFAULT FALSE,
                    confirmado_em TIMESTAMP,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_confirmacoes_data ON public.confirmacoes(data_consulta);
                CREATE INDEX IF NOT EXISTS idx_confirmacoes_medico ON public.confirmacoes(medico);
                CREATE INDEX IF NOT EXISTS idx_confirmacoes_confirmado ON public.confirmacoes(confirmado);
            """)
            conn.commit()
            logger.info("✅ Banco de dados inicializado no schema public")
        except Exception as e:
            logger.warning(f"⚠️  Não foi possível criar no schema public: {e}")
            logger.info("🔄 Tentando criar sem especificar schema...")
            
            # Rollback da transação com erro
            conn.rollback()
            
            # Tentar sem especificar schema (cria no schema do usuário)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS confirmacoes (
                    id SERIAL PRIMARY KEY,
                    id_marcacao TEXT NOT NULL UNIQUE,
                    telefone TEXT,
                    nome_paciente TEXT,
                    data_consulta DATE,
                    hora TIME,
                    medico TEXT,
                    confirmado BOOLEAN DEFAULT FALSE,
                    confirmado_em TIMESTAMP,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_confirmacoes_data ON confirmacoes(data_consulta);
                CREATE INDEX IF NOT EXISTS idx_confirmacoes_medico ON confirmacoes(medico);
                CREATE INDEX IF NOT EXISTS idx_confirmacoes_confirmado ON confirmacoes(confirmado);
            """)
            conn.commit()
            logger.info("✅ Banco de dados inicializado no schema do usuário")
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao inicializar banco: {e}")
        return False

def salvar_marcacoes_banco(marcacoes_lista):
    """Salva lista de marcações no banco. Retorna False se banco não disponível."""
    if not USE_DATABASE:
        return False
    try:
        conn = get_db_connection()
        if not conn:
            return False
        cur = conn.cursor()
        for m in marcacoes_lista:
            data_str = m.get('data', '')
            if data_str:
                try:
                    dia, mes, ano = data_str.split('/')
                    data_sql = f"{ano}-{mes}-{dia}"
                except:
                    data_sql = None
            else:
                data_sql = None
            cur.execute("""
                INSERT INTO confirmacoes 
                (id_marcacao, telefone, nome_paciente, data_consulta, hora, medico, confirmado)
                VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                ON CONFLICT (id_marcacao) 
                DO UPDATE SET
                    telefone = EXCLUDED.telefone,
                    nome_paciente = EXCLUDED.nome_paciente,
                    data_consulta = EXCLUDED.data_consulta,
                    hora = EXCLUDED.hora,
                    medico = EXCLUDED.medico,
                    atualizado_em = CURRENT_TIMESTAMP
            """, (m.get('id_marcacao'), m.get('telefone'), m.get('nome'), data_sql, m.get('hora'), m.get('medico')))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"✅ {len(marcacoes_lista)} marcações salvas no banco")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao salvar no banco: {e}")
        return False

def marcar_confirmado_banco(id_marcacao):
    """Marca marcação como confirmada no banco."""
    if not USE_DATABASE:
        return False
    try:
        conn = get_db_connection()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute("""
            UPDATE confirmacoes 
            SET confirmado = TRUE,
                confirmado_em = CURRENT_TIMESTAMP,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id_marcacao = %s
        """, (str(id_marcacao),))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"✅ Marcação {id_marcacao} confirmada no banco")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao confirmar no banco: {e}")
        return False

def buscar_status_banco(data_filtro=None):
    """Busca status das marcações no banco. Retorna formato compatível com JSON."""
    if not USE_DATABASE:
        return None
    try:
        conn = get_db_connection()
        if not conn:
            return None
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if data_filtro:
            cur.execute("""
                SELECT 
                    id_marcacao,
                    telefone,
                    nome_paciente as nome,
                    TO_CHAR(data_consulta, 'DD/MM/YYYY') as data,
                    TO_CHAR(hora, 'HH24:MI') as hora,
                    medico,
                    CASE WHEN confirmado THEN 'confirmado' ELSE 'pendente' END as status,
                    confirmado_em
                FROM confirmacoes
                WHERE data_consulta = %s
                ORDER BY confirmado DESC, nome_paciente
            """, (data_filtro,))
        else:
            cur.execute("""
                SELECT 
                    id_marcacao,
                    telefone,
                    nome_paciente as nome,
                    TO_CHAR(data_consulta, 'DD/MM/YYYY') as data,
                    TO_CHAR(hora, 'HH24:MI') as hora,
                    medico,
                    CASE WHEN confirmado THEN 'confirmado' ELSE 'pendente' END as status,
                    confirmado_em
                FROM confirmacoes
                ORDER BY data_consulta DESC, confirmado DESC, nome_paciente
                LIMIT 1000
            """)
        resultados = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(row) for row in resultados]
    except Exception as e:
        logger.error(f"❌ Erro ao buscar do banco: {e}")
        return None

# Inicializar banco se disponível
if USE_DATABASE:
    logger.info("🔄 Inicializando banco de dados...")
    init_database()

# ===== FIM FUNÇÕES DO BANCO =====

# Configurações da API Visual ASA
VISUAL_ASA_URL = "http://deskweb3oci.ddns.net:9021"
VISUAL_ASA_TOKEN = "c3Vwb3J0ZUB0ZWNub2FydGUuY29tLmJyOnB3ZHRlYzIwMjA="

# Configuração API Digisac
DIGISAC_API_URL = "https://datbaby.digisac.me/api/v1"
DIGISAC_TOKEN = os.environ.get('DIGISAC_TOKEN', '')  # Token configurado no Render

headers = {
    "Authorization": f"Basic {VISUAL_ASA_TOKEN}",
    "Content-Type": "application/json"
}

def buscar_telefone_digisac(contact_id):
    """
    Busca o telefone do contato na API do Digisac usando contactId
    """
    if not DIGISAC_TOKEN:
        logger.warning("⚠️  Token do Digisac não configurado")
        return None
    
    try:
        url = f"{DIGISAC_API_URL}/contacts/{contact_id}"
        headers_digisac = {
            "Authorization": f"Bearer {DIGISAC_TOKEN}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"🔍 Buscando telefone na API Digisac...")
        
        response = requests.get(url, headers=headers_digisac, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Tentar diferentes campos possíveis
            telefone = (
                data.get('phone') or 
                data.get('number') or 
                data.get('phoneNumber') or
                data.get('idFromService') or
                (data.get('data', {}).get('number') if isinstance(data.get('data'), dict) else None) or
                (data.get('data', {}).get('validNumber') if isinstance(data.get('data'), dict) else None)
            )
            
            if telefone:
                logger.info(f"✅ Telefone encontrado: {telefone}")
                return telefone
            else:
                logger.warning(f"⚠️  Sem telefone. Dados: {data}")
                return None
        else:
            logger.error(f"❌ Erro API: {response.status_code} - {response.text[:200]}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Exceção: {str(e)}")
        return None

def salvar_confirmacao(id_marcacao, telefone):
    """
    Salva a confirmação para monitoramento (JSON + BANCO)
    """
    try:
        # PRIORIDADE 1: SALVAR NO BANCO
        if USE_DATABASE:
            if marcar_confirmado_banco(id_marcacao):
                logger.info(f"✅ Confirmação salva no BANCO: {id_marcacao}")
            else:
                logger.warning(f"⚠️  Falha ao salvar no banco, salvando apenas em JSON")
        
        # SEMPRE salvar no JSON também (backup)
        arquivo_confirmacoes = 'confirmacoes.json'
        
        # Carregar confirmações existentes
        if os.path.exists(arquivo_confirmacoes):
            with open(arquivo_confirmacoes, 'r', encoding='utf-8') as f:
                confirmacoes = json.load(f)
        else:
            confirmacoes = {}
        
        # Adicionar nova confirmação
        confirmacoes[str(id_marcacao)] = {
            'telefone': telefone,
            'confirmado_em': datetime.now().isoformat(),
            'status': 'confirmado'
        }
        
        # Salvar de volta
        with open(arquivo_confirmacoes, 'w', encoding='utf-8') as f:
            json.dump(confirmacoes, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Confirmação salva no JSON: {id_marcacao}")
        
        # Invalidar cache para forçar atualização
        try:
            if os.path.exists('cache_status.json'):
                os.remove('cache_status.json')
                logger.info("🗑️  Cache invalidado")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Erro ao salvar confirmação: {e}")

@app.route('/')
def home():
    """Página inicial"""
    return """
    <html>
    <head>
        <title>Webhook Digisac → Visual ASA</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #2E86AB; }
            .status {
                background: #D1ECF1;
                padding: 15px;
                border-radius: 5px;
                margin: 20px 0;
            }
            .endpoint {
                background: #F8F9FA;
                padding: 15px;
                border-radius: 5px;
                font-family: monospace;
                margin: 10px 0;
            }
            .success { color: #06A77D; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏥 Webhook Digisac → Visual ASA</h1>
            <div class="status">
                <p class="success">✅ Servidor Online!</p>
                <p>Pronto para receber confirmações do Digisac</p>
            </div>
            
            <h2>📋 Endpoints Disponíveis:</h2>
            
            <h3>POST /webhook/confirmar</h3>
            <div class="endpoint">
                URL: """ + request.url_root + """webhook/confirmar
                Método: POST
                Body: { "idMarcacao": 123456 }
            </div>
            
            <h3>GET /webhook/status</h3>
            <div class="endpoint">
                URL: """ + request.url_root + """webhook/status
                Método: GET
                Retorna: Status do servidor
            </div>
            
            <h3>POST /webhook/testar</h3>
            <div class="endpoint">
                URL: """ + request.url_root + """webhook/testar
                Método: POST
                Para: Testar conexão com Visual ASA
            </div>
            
            <p style="margin-top: 30px; color: #6C757D; font-size: 12px;">
                Clínica DatBaby - Centro Médico e Medicina Reprodutiva
            </p>
        </div>
    </body>
    </html>
    """

@app.route('/health', methods=['GET'])
def health():
    """Verifica status do servidor (health check)"""
    return jsonify({
        "status": "online",
        "servidor": "Webhook Digisac → Visual ASA",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "confirmar": "/webhook/confirmar",
            "testar": "/webhook/testar",
            "status": "/webhook/status"
        }
    })

@app.route('/webhook/testar', methods=['POST'])
def testar():
    """Testa conexão com Visual ASA"""
    try:
        logger.info("Testando conexão com Visual ASA...")
        
        # Testar endpoint de marcações
        response = requests.get(
            f"{VISUAL_ASA_URL}/marcacao",
            headers=headers,
            params={"data": datetime.now().strftime("%Y-%m-%d")},
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info("✅ Conexão com Visual ASA OK")
            return jsonify({
                "status": "success",
                "mensagem": "Conexão com Visual ASA funcionando!",
                "timestamp": datetime.now().isoformat()
            }), 200
        else:
            logger.error(f"❌ Erro na conexão: {response.status_code}")
            return jsonify({
                "status": "error",
                "mensagem": f"Erro ao conectar: {response.status_code}",
                "timestamp": datetime.now().isoformat()
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Erro ao testar: {str(e)}")
        return jsonify({
            "status": "error",
            "mensagem": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/webhook/status', methods=['GET'])
def status_confirmacoes():
    """
    Retorna o status de todas as confirmações
    PRIORIDADE: BANCO > CACHE > ASA
    
    Parâmetros opcionais:
    - data: DD/MM/YYYY (filtra por data específica)
    """
    try:
        resultado = {
            'total_enviados': 0,
            'total_confirmados': 0,
            'total_pendentes': 0,
            'pacientes': []
        }
        
        # Pegar parâmetro de data (se houver)
        data_filtro = request.args.get('data')  # Formato: DD/MM/YYYY
        data_sql = None
        
        if data_filtro:
            try:
                # Converter DD/MM/YYYY para YYYY-MM-DD
                dia, mes, ano = data_filtro.split('/')
                data_sql = f"{ano}-{mes}-{dia}"
                logger.info(f"📅 Filtro de data: {data_filtro} ({data_sql})")
            except:
                logger.warning(f"⚠️  Data inválida: {data_filtro}")
                data_sql = None
        
        # PRIORIDADE 1: BUSCAR DO BANCO (se disponível)
        if USE_DATABASE:
            logger.info("📊 Buscando status do BANCO...")
            dados_banco = buscar_status_banco(data_sql)
            
            if dados_banco:
                # Converter para formato esperado
                for registro in dados_banco:
                    resultado['pacientes'].append(registro)
                    resultado['total_enviados'] += 1
                    
                    if registro.get('status') == 'confirmado':
                        resultado['total_confirmados'] += 1
                    else:
                        resultado['total_pendentes'] += 1
                
                logger.info(f"✅ Status do BANCO: {resultado['total_confirmados']}/{resultado['total_enviados']} confirmados")
                return jsonify(resultado), 200
            else:
                logger.warning("⚠️  Falha ao buscar do banco, tentando fallback...")
        
        # FALLBACK: Carregar mapeamento (enviados)
        mapeamento = {}
        arquivos_possiveis = ['mapeamento.json', 'mapeamento_telefone_ids.json', 'agenda_mapeamento.json']
        
        for arquivo in arquivos_possiveis:
            if os.path.exists(arquivo):
                with open(arquivo, 'r', encoding='utf-8') as f:
                    mapeamento = json.load(f)
                break
        
        if not mapeamento:
            logger.warning("⚠️  Nenhum mapeamento encontrado")
            return jsonify(resultado), 200
        
        # ESTRATÉGIA COM CACHE:
        # 1. Tenta ler cache (rápido)
        # 2. Se cache expirou, busca do ASA (limitado)
        # 3. Salva novo cache
        
        CACHE_FILE = 'cache_status.json'
        CACHE_EXPIRATION = 300  # 5 minutos (aumentado)
        
        cache_valido = False
        cache_data = None
        
        # Tentar ler cache
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    cache_time = datetime.fromisoformat(cache_data.get('timestamp', '2000-01-01'))
                    idade_cache = (datetime.now() - cache_time).total_seconds()
                    
                    if idade_cache < CACHE_EXPIRATION:
                        cache_valido = True
                        logger.info(f"✅ Usando cache ({int(idade_cache)}s atrás)")
            except:
                pass
        
        # Se cache válido, retornar rapidamente
        if cache_valido and cache_data:
            return jsonify(cache_data.get('resultado', resultado)), 200
        
        # Cache expirado ou inexistente - buscar do ASA
        logger.info("🔄 Cache expirado, buscando do ASA...")
        
        # Coletar IDs de marcação
        ids_marcacao = []
        info_marcacoes = {}
        
        for telefone, marcacoes_lista in mapeamento.items():
            if isinstance(marcacoes_lista, list):
                for marcacao_info in marcacoes_lista:
                    id_marcacao = str(marcacao_info.get('id_marcacao', ''))
                    if id_marcacao:
                        ids_marcacao.append(id_marcacao)
                        info_marcacoes[id_marcacao] = {
                            'telefone': telefone,
                            'nome': marcacao_info.get('nome', 'Sem nome'),
                            'data': marcacao_info.get('data', ''),
                            'hora': marcacao_info.get('hora', ''),
                            'medico': marcacao_info.get('medico', '')
                        }
        
        logger.info(f"📋 Buscando status de {len(ids_marcacao)} marcações no ASA...")
        
        # Buscar status real no Visual ASA
        for id_marc in ids_marcacao:
            try:
                response = requests.get(
                    f"{VISUAL_ASA_URL}/marcacao/{id_marc}",
                    headers=headers,
                    timeout=5
                )
                
                confirmado = False
                if response.status_code == 200:
                    dados = response.json()
                    confirmado = dados.get('confirmada', False) or dados.get('status', '') == 'confirmada'
                
                # Montar info do paciente
                info = info_marcacoes.get(id_marc, {})
                paciente_info = {
                    'id_marcacao': id_marc,
                    'telefone': info.get('telefone', ''),
                    'nome': info.get('nome', 'Sem nome'),
                    'data': info.get('data', ''),
                    'hora': info.get('hora', ''),
                    'medico': info.get('medico', ''),
                    'status': 'confirmado' if confirmado else 'pendente',
                    'confirmado_em': None
                }
                
                resultado['pacientes'].append(paciente_info)
                resultado['total_enviados'] += 1
                
                if confirmado:
                    resultado['total_confirmados'] += 1
                else:
                    resultado['total_pendentes'] += 1
                    
            except Exception as e:
                logger.warning(f"⚠️  Erro ao buscar marcação {id_marc}: {e}")
                # Adicionar como pendente se der erro
                info = info_marcacoes.get(id_marc, {})
                paciente_info = {
                    'id_marcacao': id_marc,
                    'telefone': info.get('telefone', ''),
                    'nome': info.get('nome', 'Sem nome'),
                    'data': info.get('data', ''),
                    'hora': info.get('hora', ''),
                    'medico': info.get('medico', ''),
                    'status': 'pendente',
                    'confirmado_em': None
                }
                resultado['pacientes'].append(paciente_info)
                resultado['total_enviados'] += 1
                resultado['total_pendentes'] += 1
        
        # Ordenar: confirmados primeiro, depois por nome
        resultado['pacientes'].sort(key=lambda x: (x['status'] != 'confirmado', x['nome']))
        
        # Salvar cache
        try:
            cache_content = {
                'timestamp': datetime.now().isoformat(),
                'resultado': resultado
            }
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_content, f, ensure_ascii=False)
            logger.info("💾 Cache atualizado")
        except Exception as e:
            logger.warning(f"⚠️  Erro ao salvar cache: {e}")
        
        logger.info(f"✅ Status do ASA: {resultado['total_confirmados']}/{resultado['total_enviados']} confirmados")
        
        return jsonify(resultado), 200
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar status: {str(e)}")
        return jsonify({
            "status": "error",
            "mensagem": str(e)
        }), 500

@app.route('/webhook/upload-mapeamento', methods=['POST'])
def upload_mapeamento():
    """
    Recebe o JSON de mapeamento telefone → IDs
    Salva no servidor para uso posterior
    """
    try:
        data = request.get_json()
        
        if not data:
            logger.warning("⚠️  Upload sem dados")
            return jsonify({
                "status": "error",
                "mensagem": "Nenhum dado recebido"
            }), 400
        
        # Validar estrutura básica
        if not isinstance(data, dict):
            return jsonify({
                "status": "error",
                "mensagem": "Formato inválido. Esperado: objeto JSON"
            }), 400
        
        # NORMALIZAR TELEFONES (remover hífens)
        mapeamento_normalizado = {}
        for telefone, ids in data.items():
            telefone_normalizado = normalizar_telefone(telefone)
            mapeamento_normalizado[telefone_normalizado] = ids
            if telefone != telefone_normalizado:
                logger.info(f"   📞 Normalizado: {telefone} → {telefone_normalizado}")
        
        # Salvar arquivo em múltiplos nomes para garantir
        arquivos = ['mapeamento.json', 'mapeamento_telefone_ids.json', 'agenda_mapeamento.json']
        
        for arquivo in arquivos:
            with open(arquivo, 'w', encoding='utf-8') as f:
                json.dump(mapeamento_normalizado, f, ensure_ascii=False, indent=2)
        
        # Contar estatísticas
        total_telefones = len(mapeamento_normalizado)
        total_marcacoes = sum(len(marcacoes) for marcacoes in mapeamento_normalizado.values())
        
        logger.info(f"✅ Mapeamento atualizado: {total_telefones} telefones, {total_marcacoes} marcações")
        
        # SALVAR NO BANCO DE DADOS (se disponível)
        if USE_DATABASE:
            try:
                # Preparar lista de marcações para o banco
                marcacoes_para_banco = []
                
                for telefone, marcacoes_lista in mapeamento_normalizado.items():
                    if isinstance(marcacoes_lista, list):
                        for marcacao in marcacoes_lista:
                            marcacoes_para_banco.append({
                                'id_marcacao': marcacao.get('id_marcacao'),
                                'telefone': telefone,
                                'nome': marcacao.get('nome'),
                                'data': marcacao.get('data'),
                                'hora': marcacao.get('hora'),
                                'medico': marcacao.get('medico')
                            })
                
                # Salvar no banco
                if salvar_marcacoes_banco(marcacoes_para_banco):
                    logger.info(f"✅ {len(marcacoes_para_banco)} marcações salvas no banco")
                else:
                    logger.warning("⚠️  Falha ao salvar no banco, usando apenas JSON")
                    
            except Exception as e:
                logger.error(f"❌ Erro ao salvar no banco: {e}")
                logger.info("⚠️  Continuando com JSON apenas")
        
        return jsonify({
            "status": "success",
            "mensagem": "Mapeamento atualizado com sucesso!",
            "estatisticas": {
                "total_telefones": total_telefones,
                "total_marcacoes": total_marcacoes
            },
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erro ao fazer upload do mapeamento: {str(e)}")
        return jsonify({
            "status": "error",
            "mensagem": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/webhook/agenda-medico', methods=['GET'])
def agenda_medico():
    """
    Busca agenda completa de um médico diretamente do Visual ASA
    Parâmetros: medico, data_inicio, data_fim
    OTIMIZADO: Máximo 7 dias por vez
    """
    try:
        nome_medico = request.args.get('medico')
        data_inicio = request.args.get('data_inicio')  # YYYY-MM-DD
        data_fim = request.args.get('data_fim')  # YYYY-MM-DD
        
        if not nome_medico:
            return jsonify({
                "status": "error",
                "mensagem": "Nome do médico é obrigatório"
            }), 400
        
        # Se não informou datas, buscar semana atual
        if not data_inicio or not data_fim:
            hoje = datetime.now()
            # Início da semana (domingo)
            inicio_semana = hoje - timedelta(days=hoje.weekday() + 1)
            # Fim da semana (sábado)
            fim_semana = inicio_semana + timedelta(days=6)
            
            data_inicio = inicio_semana.strftime("%Y-%m-%d")
            data_fim = fim_semana.strftime("%Y-%m-%d")
        
        # PROTEÇÃO: Máximo 7 dias
        data_inicio_obj = datetime.strptime(data_inicio, "%Y-%m-%d")
        data_fim_obj = datetime.strptime(data_fim, "%Y-%m-%d")
        
        diferenca = (data_fim_obj - data_inicio_obj).days
        if diferenca > 7:
            return jsonify({
                "status": "error",
                "mensagem": "Período máximo: 7 dias"
            }), 400
        
        logger.info(f"📅 Buscando agenda de '{nome_medico}' de {data_inicio} até {data_fim}")
        
        # Buscar marcações de cada dia
        data_atual = data_inicio_obj
        data_final = data_fim_obj
        
        todas_consultas = []
        
        while data_atual <= data_final:
            data_str = data_atual.strftime("%Y-%m-%d")
            
            try:
                response = requests.get(
                    f"{VISUAL_ASA_URL}/marcacao",
                    headers=headers,
                    params={"data": data_str},
                    timeout=10
                )
                
                if response.status_code == 200:
                    marcacoes = response.json()
                    
                    # Filtrar por médico
                    for m in marcacoes:
                        medico_info = m.get('medico', {})
                        medico_nome = medico_info.get('medicoDescricao', '') if medico_info else ''
                        
                        # Comparar nome (case insensitive)
                        if medico_nome.lower().strip() == nome_medico.lower().strip():
                            # Extrair informações
                            paciente_nome = m.get('paciente', 'Sem nome')
                            
                            # Telefones
                            telefones = m.get('telefones', [])
                            telefone = ''
                            if telefones and len(telefones) > 0:
                                telefone = telefones[0].get('telefone', '')
                            
                            # Data e hora
                            data_marcada = m.get('dataMarcada', '')
                            hora = ''
                            if data_marcada:
                                try:
                                    dt = datetime.fromisoformat(data_marcada.replace('Z', '+00:00'))
                                    hora = dt.strftime('%H:%M')
                                except:
                                    hora = ''
                            
                            # Status de confirmação
                            confirmada = m.get('confirmada', False)
                            
                            # Especialidade
                            especialidade_info = m.get('especialidade', {})
                            especialidade = especialidade_info.get('nome', '') if especialidade_info else ''
                            
                            consulta = {
                                'id_marcacao': str(m.get('idMarcacao', '')),
                                'paciente': paciente_nome,
                                'telefone': telefone,
                                'data': data_atual.strftime('%d/%m/%Y'),
                                'hora': hora,
                                'medico': medico_nome,
                                'especialidade': especialidade,
                                'confirmada': confirmada,
                                'status': 'confirmado' if confirmada else 'pendente'
                            }
                            
                            todas_consultas.append(consulta)
                
            except Exception as e:
                logger.warning(f"⚠️  Erro ao buscar {data_str}: {e}")
            
            # Próximo dia
            data_atual += timedelta(days=1)
        
        # Ordenar por data e hora
        todas_consultas.sort(key=lambda x: (x['data'], x['hora']))
        
        logger.info(f"✅ Encontradas {len(todas_consultas)} consultas")
        
        return jsonify({
            'medico': nome_medico,
            'periodo': {
                'inicio': data_inicio,
                'fim': data_fim
            },
            'total_consultas': len(todas_consultas),
            'consultas': todas_consultas
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar agenda: {str(e)}")
        return jsonify({
            "status": "error",
            "mensagem": str(e)
        }), 500

@app.route('/webhook/listar-medicos', methods=['GET'])
def listar_medicos():
    """
    Lista todos os médicos que têm consultas nos próximos 7 dias
    OTIMIZADO: Apenas 7 dias para evitar timeout
    """
    try:
        # Buscar próximos 7 dias (não 30)
        hoje = datetime.now()
        data_fim = hoje + timedelta(days=7)
        
        medicos_set = set()
        
        data_atual = hoje
        while data_atual <= data_fim:
            data_str = data_atual.strftime("%Y-%m-%d")
            
            try:
                response = requests.get(
                    f"{VISUAL_ASA_URL}/marcacao",
                    headers=headers,
                    params={"data": data_str},
                    timeout=10
                )
                
                if response.status_code == 200:
                    marcacoes = response.json()
                    
                    for m in marcacoes:
                        medico_info = m.get('medico', {})
                        if medico_info:
                            medico_nome = medico_info.get('medicoDescricao', '')
                            if medico_nome:
                                medicos_set.add(medico_nome)
            except:
                pass
            
            data_atual += timedelta(days=1)
        
        medicos_lista = sorted(list(medicos_set))
        
        logger.info(f"✅ Encontrados {len(medicos_lista)} médicos")
        
        return jsonify({
            'total': len(medicos_lista),
            'medicos': medicos_lista
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erro ao listar médicos: {str(e)}")
        return jsonify({
            "status": "error",
            "mensagem": str(e)
        }), 500

@app.route('/webhook/confirmar', methods=['POST'])
def webhook_confirmar():
    """
    Recebe webhook do Digisac e confirma marcação(ões) no Visual ASA
    
    Payload esperado:
    {
        "telefone": "5521999999999"
    }
    
    OU formato Digisac:
    {
        "event": "bot.command",
        "data": {
            "command": "524387"  (ID fixo - fallback)
        }
    }
    """
    try:
        # Pegar dados do webhook
        data = request.get_json()
        
        if not data:
            logger.warning("⚠️  Webhook recebido sem dados")
            return jsonify({
                "status": "error",
                "mensagem": "Nenhum dado recebido"
            }), 400
        
        # Log do recebimento
        logger.info(f"📩 Webhook recebido: {data}")
        
        # Tentar extrair telefone ou ID
        telefone = None
        id_marcacao = None
        
        # Formato 1: Telefone direto
        telefone = data.get('telefone') or data.get('phone') or data.get('numero')
        
        # Formato 2: Digisac - dentro de data
        if not telefone and 'data' in data:
            data_obj = data.get('data', {})
            
            # Tentar buscar telefone via API Digisac usando contactId
            contact_id = data_obj.get('contactId')
            if contact_id:
                logger.info(f"🆔 contactId encontrado: {contact_id}")
                telefone = buscar_telefone_digisac(contact_id)
            
            # Fallback: Tentar pegar do message
            if not telefone and 'message' in data_obj:
                message = data_obj.get('message', {})
                telefone = message.get('fromId')
            
            # Fallback: Tentar pegar command como ID
            if not telefone:
                id_marcacao = data_obj.get('command')
        
        # Se não tem telefone nem ID, erro
        if not telefone and not id_marcacao:
            logger.error("❌ Telefone ou ID não encontrado no payload")
            return jsonify({
                "status": "error",
                "mensagem": "Telefone ou ID não encontrado",
                "payload_recebido": data
            }), 400
        
        # Se tem telefone, buscar IDs no JSON
        ids_para_confirmar = []
        
        if telefone:
            logger.info(f"📞 Processando confirmação para telefone: {telefone}")
            
            # Normalizar telefone (remover espaços, hífens, etc)
            telefone_normalizado = ''.join(filter(str.isdigit, telefone))
            
            # Tentar carregar mapeamento do JSON
            try:
                # Tentar vários nomes possíveis
                arquivos_possiveis = [
                    'mapeamento_telefone_ids.json',
                    'agenda_mapeamento.json',
                    'mapeamento.json'
                ]
                
                mapeamento = None
                arquivo_encontrado = None
                
                for arquivo in arquivos_possiveis:
                    try:
                        with open(arquivo, 'r', encoding='utf-8') as f:
                            mapeamento = json.load(f)
                            arquivo_encontrado = arquivo
                            break
                    except FileNotFoundError:
                        continue
                
                if not mapeamento:
                    raise FileNotFoundError("Nenhum arquivo de mapeamento encontrado")
                
                logger.info(f"📊 Mapeamento carregado de '{arquivo_encontrado}' com {len(mapeamento)} telefones")
                
                # Buscar por telefone normalizado (sem hífens)
                telefone_normalizado = normalizar_telefone(telefone)
                logger.info(f"   🔍 Buscando telefone normalizado: {telefone_normalizado}")
                
                if telefone_normalizado in mapeamento:
                    marcacoes_info = mapeamento[telefone_normalizado]
                    ids_para_confirmar = [m['id_marcacao'] for m in marcacoes_info]
                    logger.info(f"✅ Encontrado {len(ids_para_confirmar)} marcação(ões)")
                else:
                    logger.error(f"❌ Telefone {telefone_normalizado} não encontrado no mapeamento")
                    logger.error(f"   Primeiras 5 chaves: {list(mapeamento.keys())[:5]}")
                    return jsonify({
                        "status": "error",
                        "mensagem": f"Telefone {telefone} não encontrado no mapeamento",
                        "telefone_recebido": telefone,
                        "telefone_normalizado": telefone_normalizado
                    }), 404
                    
            except FileNotFoundError:
                logger.error("❌ Arquivo mapeamento_telefone_ids.json não encontrado")
                return jsonify({
                    "status": "error",
                    "mensagem": "Arquivo de mapeamento não encontrado. Faça upload do JSON no servidor."
                }), 500
            except Exception as e:
                logger.error(f"❌ Erro ao carregar mapeamento: {str(e)}")
                return jsonify({
                    "status": "error",
                    "mensagem": f"Erro ao carregar mapeamento: {str(e)}"
                }), 500
        
        # Se tem ID direto (fallback), usar ele
        elif id_marcacao:
            try:
                ids_para_confirmar = [int(id_marcacao)]
                logger.info(f"🔍 Usando ID direto: {id_marcacao}")
            except:
                logger.error(f"❌ ID inválido: {id_marcacao}")
                return jsonify({
                    "status": "error",
                    "mensagem": f"ID inválido: {id_marcacao}"
                }), 400
        
        # Confirmar todas as marcações
        confirmadas = []
        erros = []
        
        for id_marc in ids_para_confirmar:
            try:
                id_marc_int = int(id_marc)
            except:
                logger.error(f"❌ ID inválido: {id_marc}")
                erros.append({"id": id_marc, "erro": "ID inválido"})
                continue
            
            logger.info(f"📤 Confirmando marcação ID: {id_marc_int}")
            
            endpoint_confirmar = f"{VISUAL_ASA_URL}/marcacao/{id_marc_int}"
            
            payload_confirmar = {
                "isEmailConfirmado": True,
                "dataUltConfEmail": datetime.now().isoformat()
            }
            
            response = requests.patch(
                endpoint_confirmar,
                headers=headers,
                json=payload_confirmar,
                timeout=30
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"✅ Marcação {id_marc_int} confirmada com sucesso!")
                confirmadas.append(id_marc_int)
                
                # Salvar confirmação para monitoramento
                try:
                    salvar_confirmacao(id_marc_int, telefone if telefone else str(id_marc_int))
                except Exception as e:
                    logger.error(f"Erro ao salvar confirmação: {e}")
            else:
                logger.error(f"❌ Erro ao confirmar marcação {id_marc_int}: {response.status_code}")
                erros.append({"id": id_marc_int, "erro": f"Status {response.status_code}"})
        
        # Resposta final
        if len(confirmadas) > 0:
            mensagem = f"{len(confirmadas)} marcação(ões) confirmada(s) com sucesso!"
            if len(erros) > 0:
                mensagem += f" ({len(erros)} erro(s))"
            
            return jsonify({
                "status": "success",
                "mensagem": mensagem,
                "confirmadas": confirmadas,
                "erros": erros if erros else None,
                "timestamp": datetime.now().isoformat()
            }), 200
        else:
            return jsonify({
                "status": "error",
                "mensagem": "Nenhuma marcação foi confirmada",
                "erros": erros,
                "timestamp": datetime.now().isoformat()
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {str(e)}")
        return jsonify({
            "status": "error",
            "mensagem": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/webhook/digisac', methods=['POST'])
def webhook_digisac():
    """
    Endpoint alternativo que recebe formato padrão do Digisac
    Adapta e chama o endpoint de confirmação
    """
    try:
        data = request.get_json()
        logger.info(f"📩 Webhook Digisac recebido: {data}")
        
        # Tentar extrair ID da marcação de diferentes campos possíveis
        id_marcacao = None
        
        # Possíveis localizações do ID
        if 'command' in data:
            id_marcacao = data['command'].get('identifier')
        elif 'identifier' in data:
            id_marcacao = data['identifier']
        elif 'idMarcacao' in data:
            id_marcacao = data['idMarcacao']
        elif 'id' in data:
            id_marcacao = data['id']
        
        if not id_marcacao:
            logger.error(f"❌ ID não encontrado no payload Digisac: {data}")
            return jsonify({
                "status": "error",
                "mensagem": "ID da marcação não encontrado",
                "payload_recebido": data
            }), 400
        
        # Delegar para a mesma lógica de confirmação
        return webhook_confirmar()
        
    except Exception as e:
        logger.error(f"❌ Erro no webhook Digisac: {str(e)}")
        return jsonify({
            "status": "error",
            "mensagem": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
