"""
SERVIDOR WEBHOOK - DIGISAC → VISUAL ASA
Recebe confirmações do Digisac e confirma automaticamente no Visual ASA
"""

from flask import Flask, request, jsonify
import requests
from datetime import datetime
import os
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configurações da API Visual ASA
VISUAL_ASA_URL = "http://deskweb2oci.ddns.net:9991"
VISUAL_ASA_TOKEN = "c3Vwb3J0ZUB0ZWNub2FydGUuY29tLmJyOnB3ZHRlYzIwMjA="

headers = {
    "Authorization": f"Basic {VISUAL_ASA_TOKEN}",
    "Content-Type": "application/json"
}

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

@app.route('/webhook/status', methods=['GET'])
def status():
    """Verifica status do servidor"""
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
        
        # Salvar arquivo
        with open('mapeamento_telefone_ids.json', 'w', encoding='utf-8') as f:
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
            
            # Tentar pegar do contato
            if 'message' in data_obj:
                message = data_obj.get('message', {})
                telefone = message.get('fromId')
            
            # Tentar pegar command como ID (fallback)
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
                with open('mapeamento_telefone_ids.json', 'r', encoding='utf-8') as f:
                    mapeamento = json.load(f)
                
                logger.info(f"📊 Mapeamento carregado com {len(mapeamento)} telefones")
                
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
