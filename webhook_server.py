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

@app.route('/webhook/confirmar', methods=['POST'])
def webhook_confirmar():
    """
    Recebe webhook do Digisac e confirma marcação no Visual ASA
    
    Payload esperado:
    {
        "idMarcacao": 495367,
        "paciente": "Nome do Paciente" (opcional)
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
        
        # Extrair ID da marcação
        id_marcacao = data.get('idMarcacao') or data.get('id_marcacao') or data.get('id')
        
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
