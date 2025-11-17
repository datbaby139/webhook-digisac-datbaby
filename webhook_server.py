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

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Permitir requisições de qualquer origem

# Configurações da API Visual ASA
VISUAL_ASA_URL = "http://deskweb2oci.ddns.net:9991"
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
    Salva a confirmação para monitoramento
    """
    try:
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
        
        logger.info(f"💾 Confirmação salva: {id_marcacao}")
        
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
    USA MAPEAMENTO LOCAL + CONFIRMAÇÕES (rápido)
    """
    try:
        resultado = {
            'total_enviados': 0,
            'total_confirmados': 0,
            'total_pendentes': 0,
            'pacientes': []
        }
        
        # Carregar mapeamento (enviados)
        mapeamento = {}
        arquivos_possiveis = ['mapeamento.json', 'mapeamento_telefone_ids.json', 'agenda_mapeamento.json']
        
        for arquivo in arquivos_possiveis:
            if os.path.exists(arquivo):
                with open(arquivo, 'r', encoding='utf-8') as f:
                    mapeamento = json.load(f)
                break
        
        # Carregar confirmações
        confirmacoes = {}
        if os.path.exists('confirmacoes.json'):
            with open('confirmacoes.json', 'r', encoding='utf-8') as f:
                confirmacoes = json.load(f)
        
        # Processar cada telefone
        for telefone, marcacoes_lista in mapeamento.items():
            if isinstance(marcacoes_lista, list):
                for marcacao_info in marcacoes_lista:
                    id_marcacao = str(marcacao_info.get('id_marcacao', ''))
                    
                    # Verificar se foi confirmado
                    confirmado = id_marcacao in confirmacoes
                    
                    paciente_info = {
                        'id_marcacao': id_marcacao,
                        'telefone': telefone,
                        'nome': marcacao_info.get('nome', 'Sem nome'),
                        'data': marcacao_info.get('data', ''),
                        'hora': marcacao_info.get('hora', ''),
                        'medico': marcacao_info.get('medico', ''),
                        'status': 'confirmado' if confirmado else 'pendente',
                        'confirmado_em': confirmacoes.get(id_marcacao, {}).get('confirmado_em') if confirmado else None
                    }
                    
                    resultado['pacientes'].append(paciente_info)
                    resultado['total_enviados'] += 1
                    
                    if confirmado:
                        resultado['total_confirmados'] += 1
                    else:
                        resultado['total_pendentes'] += 1
        
        # Ordenar: confirmados primeiro, depois por nome
        resultado['pacientes'].sort(key=lambda x: (x['status'] != 'confirmado', x['nome']))
        
        logger.info(f"✅ Status: {resultado['total_confirmados']}/{resultado['total_enviados']} confirmados")
        
        return jsonify(resultado), 200
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar status: {str(e)}")
        return jsonify({
            "status": "error",
            "mensagem": str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """
    Endpoint de health check para UptimeRobot manter servidor acordado
    """
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "message": "Servidor webhook ativo!"
    }), 200

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
        
        # Salvar arquivo em múltiplos nomes para garantir
        arquivos = ['mapeamento.json', 'mapeamento_telefone_ids.json', 'agenda_mapeamento.json']
        
        for arquivo in arquivos:
            with open(arquivo, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Contar estatísticas
        total_telefones = len(data)
        total_marcacoes = sum(len(marcacoes) for marcacoes in data.values())
        
        logger.info(f"✅ Mapeamento atualizado: {total_telefones} telefones, {total_marcacoes} marcações")
        
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
                
                # Buscar por telefone (testar várias formatações)
                telefones_testar = [
                    telefone,
                    telefone_normalizado,
                    f"55 {telefone_normalizado[2:4]}-{telefone_normalizado[4:9]}-{telefone_normalizado[9:]}",
                    f"55 {telefone_normalizado[2:4]}-{telefone_normalizado[4:]}"
                ]
                
                encontrado = False
                for tel_teste in telefones_testar:
                    if tel_teste in mapeamento:
                        marcacoes_info = mapeamento[tel_teste]
                        ids_para_confirmar = [m['id_marcacao'] for m in marcacoes_info]
                        logger.info(f"✅ Encontrado {len(ids_para_confirmar)} marcação(ões) para {tel_teste}")
                        encontrado = True
                        break
                
                if not encontrado:
                    logger.error(f"❌ Telefone {telefone} não encontrado no mapeamento")
                    return jsonify({
                        "status": "error",
                        "mensagem": f"Telefone {telefone} não encontrado no mapeamento",
                        "telefone_recebido": telefone
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
def webhook_confirmar():
    """
    Recebe webhook do Digisac e confirma marcação no Visual ASA
    
    Payload esperado:
    {
        "idMarcacao": 495367,
        "paciente": "Nome do Paciente" (opcional)
    }
    
    OU formato Digisac:
    {
        "event": "bot.command",
        "data": {
            "command": "524387"
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
        
        # Extrair ID da marcação de diferentes formatos possíveis
        id_marcacao = None
        
        # Formato 1: Direto no root
        id_marcacao = data.get('idMarcacao') or data.get('id_marcacao') or data.get('id')
        
        # Formato 2: Digisac - dentro de data.command
        if not id_marcacao and 'data' in data:
            data_obj = data.get('data', {})
            id_marcacao = data_obj.get('command')
        
        # Formato 3: Digisac - event wrapper
        if not id_marcacao and 'event' in data:
            if data.get('event') == 'bot.command':
                data_obj = data.get('data', {})
                id_marcacao = data_obj.get('command')
        
        if not id_marcacao:
            logger.error("❌ ID da marcação não encontrado no payload")
            return jsonify({
                "status": "error",
                "mensagem": "ID da marcação não encontrado",
                "payload_recebido": data
            }), 400
        
        # Tentar converter para int
        try:
            id_marcacao = int(id_marcacao)
        except:
            logger.error(f"❌ ID inválido: {id_marcacao}")
            return jsonify({
                "status": "error",
                "mensagem": f"ID inválido: {id_marcacao}"
            }), 400
        
        logger.info(f"🔍 Processando confirmação para ID: {id_marcacao}")
        
        # Confirmar no Visual ASA
        endpoint_confirmar = f"{VISUAL_ASA_URL}/marcacao/{id_marcacao}"
        
        payload_confirmar = {
            "isEmailConfirmado": True,
            "dataUltConfEmail": datetime.now().isoformat()
        }
        
        logger.info(f"📤 Enviando confirmação para Visual ASA: {endpoint_confirmar}")
        
        response = requests.patch(
            endpoint_confirmar,
            headers=headers,
            json=payload_confirmar,
            timeout=30
        )
        
        if response.status_code in [200, 204]:
            logger.info(f"✅ Marcação {id_marcacao} confirmada com sucesso!")
            
            return jsonify({
                "status": "success",
                "mensagem": f"Marcação {id_marcacao} confirmada com sucesso!",
                "idMarcacao": id_marcacao,
                "timestamp": datetime.now().isoformat(),
                "visual_asa_response": response.status_code
            }), 200
        else:
            logger.error(f"❌ Erro ao confirmar no Visual ASA: {response.status_code}")
            logger.error(f"Resposta: {response.text}")
            
            return jsonify({
                "status": "error",
                "mensagem": "Erro ao confirmar no Visual ASA",
                "idMarcacao": id_marcacao,
                "visual_asa_status": response.status_code,
                "visual_asa_response": response.text[:200],
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
        
        # Chamar endpoint de confirmação
        return webhook_confirmar()
        
    except Exception as e:
        logger.error(f"❌ Erro no webhook Digisac: {str(e)}")
        return jsonify({
            "status": "error",
            "mensagem": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
