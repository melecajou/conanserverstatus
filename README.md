# Bot de Status para Servidores Conan Exiles

Este bot para Discord monitora o status de um ou mais servidores Conan Exiles e exibe as informações em um canal específico, atualizando-as periodicamente.

## Funcionalidades

- Monitora múltiplos servidores simultaneamente.
- Exibe o status (Online/Offline) e a lista de jogadores conectados.
- Atualiza automaticamente a mensagem de status em um intervalo configurável.
- Fornece um comando de barra (`/status`) para verificação manual.
- Robusto, com tratamento de erros e tentativas de reconexão.

## Idiomas (Internationalization)

O bot suporta múltiplos idiomas. As traduções são gerenciadas pelo sistema `gettext`.

**Idiomas Suportados:**
- `en`: Inglês
- `pt_BR`: Português do Brasil

Você pode definir o idioma desejado no arquivo `config.py`.

## Pré-requisitos

- Python 3.8 ou superior
- Git
- Um servidor com acesso à internet para hospedar o bot.

## Instalação

Siga os passos abaixo para configurar o bot no seu servidor.

**1. Clonar o Repositório**

```bash
git clone https://github.com/melecajou/conanserverstatus.git
cd conanserverstatus
```

**2. Criar um Ambiente Virtual (Recomendado)**

É uma boa prática isolar as dependências do projeto.

```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Instalar as Dependências**

Instale as bibliotecas Python necessárias.

```bash
pip install -r requirements.txt
```

**4. Configurar o Bot**

Copie o arquivo de exemplo e preencha com suas informações.

```bash
cp config.py.example config.py
nano config.py
```

Dentro de `config.py`, você precisará preencher:
- `LANGUAGE`: O idioma que o bot usará. O padrão é `'en'`. Mude para `'pt_BR'` para português.
- `STATUS_BOT_TOKEN`: O token do seu bot do Discord. **Mantenha isso em segredo!**
- `SERVERS`: Uma lista com os dados de cada servidor que você quer monitorar (IP, porta RCON, senha RCON e ID do canal de status).

## Executando o Bot

**Para testar (execução manual):**

Você pode iniciar o bot diretamente no seu terminal. Pressione `CTRL+C` para parar.

```bash
python conan_server_status.py
```

**Para produção (usando systemd):**

Para garantir que o bot rode continuamente em segundo plano e reinicie com o servidor, vamos criar um serviço `systemd`.

**a. Crie o arquivo de serviço:**

```bash
sudo nano /etc/systemd/system/conan_status_bot.service
```

**b. Cole o seguinte conteúdo no arquivo.**

**Importante:** Ajuste os caminhos em `WorkingDirectory` e `ExecStart` para corresponder à localização onde você clonou o repositório.

```ini
[Unit]
Description=Bot de Status para Servidores Conan Exiles
After=network.target

[Service]
User=seu_usuario          # <-- TROQUE PELO SEU NOME DE USUÁRIO (ex: steam)
Group=seu_grupo         # <-- TROQUE PELO SEU GRUPO (ex: steam)

WorkingDirectory=/home/seu_usuario/bots/ConanServerStatus  # <-- AJUSTE O CAMINHO
ExecStart=/home/seu_usuario/bots/ConanServerStatus/venv/bin/python conan_server_status.py # <-- AJUSTE O CAMINHO

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**c. Habilite e inicie o serviço:**

```bash
sudo systemctl daemon-reload         # Recarrega o systemd para ler o novo arquivo
sudo systemctl enable conan_status_bot.service # Habilita o bot para iniciar com o sistema
sudo systemctl start conan_status_bot.service  # Inicia o bot imediatamente
```

**d. Verifique o status do serviço:**

```bash
sudo systemctl status conan_status_bot.service
```

## Uso no Discord

- O bot manterá uma mensagem de status sempre atualizada no canal que você configurou em `config.py`.
- Qualquer membro do servidor pode usar o comando `/status` para receber uma atualização imediata de todos os servidores monitorados.