# dev-nuvem
Desenvolvimento de Software para Nuvem

# 🎬 Cinematix — Sistema Cloud-Native de Reserva de Ingressos de Cinema

O **Cinematix** é uma plataforma full-stack cloud-native desenvolvida para a reserva e venda de ingressos de cinema em tempo real. Projetado para operar com alta disponibilidade, resiliência e escalabilidade automática na **AWS**, o sistema adota uma arquitetura orientada a eventos e desacoplada em microsserviços/workers:

* **Backend & API Web**: Servidor FastAPI rodando em instâncias EC2 sob um **Auto Scaling Group**, com **Nginx** atuando como proxy reverso e balanceado por um **Application Load Balancer (ALB)**.
* **Gerenciamento de Concorrência & Cache**: **Amazon ElastiCache (Redis)** para aceleração na leitura do catálogo e controle de **locks temporários de assentos** (TTL de 5 min) por cliente.
* **Persistência Relacional**: **Amazon RDS (PostgreSQL)** mantido em subnet privada para garantir a integridade relacional de filmes, sessões e ingressos vendidos.
* **Processamento Assíncrono de Mídia**: O upload de pôsteres publica mensagens no **Amazon SNS**, repassadas para uma fila **Amazon SQS**. Um **Worker (EC2)** dedicado consome essa fila, gera os thumbnails das capas e grava os arquivos no **Amazon S3**.
* **Auditoria Centralizada**: Trilha de auditoria unificada de todas as ações da API e do Worker gravada no **Amazon DynamoDB**.
* **Hospedagem Frontend**: Aplicação em React 19 com TypeScript, distribuída como site estático no **Amazon S3 Static Website Hosting**.

---

## 📐 Arquitetura da Infraestrutura (AWS)

A infraestrutura foi implementada dentro de uma **Amazon VPC**, segregando a camada pública de entrada do ambiente privado de armazenamento:


```mermaid
graph TD
    Client[Espectador / Admin] --> S3Front[Amazon S3 - Frontend Estático]
    S3Front -->|Requisições HTTP/API| ALB[Application Load Balancer]
    ALB --> ASG[Auto Scaling Group - FastAPI + Nginx]

    subgraph Private_Subnet [Private Subnet]
        RDS[(Amazon RDS PostgreSQL)]
        Redis[(ElastiCache Redis)]
    end

    ASG --> Private_Subnet
    ASG --> Dynamo[(Amazon DynamoDB - Logs)]
    ASG --> SNS[Amazon SNS Topic]

    SNS --> SQS[Amazon SQS Queue]
    SQS --> Worker[Worker EC2]
    Worker --> S3Assets[Amazon S3 - Posters, Thumbs & PDFs]
    Worker --> Dynamo
```


### Componentes AWS

* **Amazon VPC**: Isolamento lógico de rede dividido em Subnets Públicas e Subnets Privadas.
* **Amazon S3**: Buckets dedicados para hospedagem estática do Frontend e armazenamento de assets (pôsteres originais, thumbnails e arquivos PDF dos ingressos).
* **Application Load Balancer (ALB)**: Distribui as requisições HTTP recebidas entre as instâncias EC2 da aplicação web.
* **Auto Scaling Group (EC2)**: Gerencia o escalamento horizontal do Backend conforme o uso de vCPU das instâncias.
* **Nginx**: Proxy reverso rodando na porta 80 das EC2s direcionando as requisições para o Uvicorn na porta 8000, oferecendo a rota `/health` para os Health Checks do ALB.
* **Amazon ElastiCache (Redis)**: Cache do catálogo e sistema de reservas com TTL de 5 minutos, evitando conflitos simultâneos de assentos.
* **Amazon RDS (PostgreSQL)**: Banco de dados relacional em subnet privada contendo tabelas de filmes, sessões e ingressos com trava de integridade contra vendas duplicadas.
* **Amazon SNS & SQS**: Desacoplamento assíncrono para eventos de imagem via Publish/Subscribe (SNS) e fila de mensagens (SQS).
* **Worker EC2**: Processo continuo escutando o SQS, gerando thumbnails com Pillow e atualizando o S3 e DynamoDB.
* **Amazon DynamoDB**: Tabela NoSQL usada para persistir o histórico de logs de auditoria de todas as entidades (`CREATE`, `READ`, `UPDATE`, `DELETE`, `PROCESS`).

---

## ✨ Funcionalidades do Sistema

### 🎟️ Para o Espectador (Bilheteria Web)
* **Navegação no Catálogo**: Consulta otimizada servida via cache Redis.
* **Mapa Interativo da Sala**: Seleção visual de lugares organizados das fileiras **A até G** com 16 lugares por fileira (112 assentos por sessão).
* **Bloqueio Concorrente de Lugares**: Trava temporária no Redis vinculada ao `client_id` do navegador, válida por 5 minutos.
* **Ingresso em PDF Assinado**: Emissão do bilhete contendo canhoto e dados da compra, com download seguro validado por assinatura HMAC SHA256.

### 🔄 Worker Assíncrono de Imagens
* **Redimensionamento Automático**: Consumo da fila SQS para geração de thumbnails (`300x450px`, JPEG quality 85) dos novos pôsteres enviados.
* **Métricas de Processamento**: Gravação automatizada de logs no DynamoDB com dimensões de conversão (`de` -> `para`).

### 🛠️ Para a Administração (`#/admin`)
* **Gestão do Catálogo (CRUD de Filmes)**: Cadastro e edição de títulos com envio de imagem de capa para o S3.
* **Agendamento de Sessões**: Criação de horários, datas e preços diferenciados para os filmes exibidos.
* **Relatório de Compras**: Consulta consolidada de ingressos vendidos e identificação dos compradores.
* **Visualizador de Auditoria**: Leitura dos logs de operações em tempo real via DynamoDB.
* **Simulador de Stress de CPU**: Ferramenta no painel administrativo para elevar a carga da CPU da instância a 100%, permitindo validar os alarmes do CloudWatch e o Auto Scaling.

---

## 🧰 Tech Stack

### Backend & Worker
* **Linguagem**: Python 3.10+
* **Framework Web**: FastAPI + Uvicorn
* **ORM & Banco**: SQLAlchemy 2.0, Psycopg 3 (PostgreSQL)
* **Cache & Locks**: Redis-py
* **AWS SDK**: Boto3 (S3, SNS, SQS, DynamoDB)
* **Geração de Mídias & PDF**: Pillow (PIL)
* **Proxy & Servidor**: Nginx + Systemd

### Frontend
* **Biblioteca**: React 19 (`react`, `react-dom`)
* **Linguagem**: TypeScript 7 (`typescript`)
* **Build Engine**: Vite 8 (`vite`, `rolldown`, `lightningcss`)
* **Roteamento**: Router por Hash nativo (`#/` e `#/admin`)
* **Estilização**: CSS3 com variáveis globais (Dark Theme)

---

## 📁 Estrutura do Repositório

```text
.
├── backend/
│   ├── app/
│   │   ├── config.py             # Validação do .env com Pydantic Settings
│   │   ├── database.py           # Schemas SQLAlchemy (Filme, Sessao, Ingresso)
│   │   ├── main.py               # API REST FastAPI e lógica AWS/Redis
│   │   ├── pdf.py                # Gerador de PDF via Pillow
│   │   └── seed.py               # Population script para banco e S3
│   ├── seed/
│   │   ├── filmes.json           # Massa de dados de exemplo
│   │   └── posters/              # Arquivos de imagem dos pôsteres
│   ├── .env.example              # Modelo de variáveis de ambiente
│   ├── requirements.txt          # Dependências Python do Backend
│   └── test_app.py               # Testes de fumaça e integração
│
├── worker/
│   ├── requirements.txt          # Dependências Python do Worker
│   └── worker.py                 # Worker SQS de geração de thumbnails
│
├── frontend/
│   ├── src/
│   │   ├── Admin.tsx             # Interface do Painel Administrativo (#/admin)
│   │   ├── App.tsx               # Interface da bilheteria e mapa de assentos
│   │   ├── api.ts                # Cliente HTTP com autenticação Admin
│   │   ├── main.tsx              # Ponto de entrada do React
│   │   └── styles.css            # Folha de estilos globais
│   ├── index.html
│   ├── package.json              # Scripts e dependências Frontend
│   ├── package-lock.json         # Versões travadas das dependências Node
│   └── tsconfig.json             # Configurações do TypeScript
│
├── launch templates/
│   ├── backend.sh                # UserData script para EC2 Backend (Nginx + FastAPI)
│   └── worker.sh                 # UserData script para EC2 Worker (SQS)
│
└── scripts/
    ├── deploy-backend.sh         # Script de atualização da API via SSH
    └── deploy-frontend.sh        # Script de build e sync do Frontend no S3
```
## 🔑 Variáveis de Ambiente (.env)

### Backend (backend/.env)

DATABASE_URL=postgresql+psycopg://postgres:SUA_SENHA@ENDPOINT-RDS.rds.amazonaws.com:5432/ingressos
REDIS_URL=redis://ENDPOINT-REDIS.cache.amazonaws.com:6379
S3_BUCKET=seu-bucket-s3
SNS_TOPIC_ARN=arn:aws:sns:us-east-1:123456789012:dspn-projeto-sns
DYNAMO_TABLE=dspn-projeto-dynamo-logs
ADMIN_TOKEN=senha_segura_admin
AWS_REGION=us-east-1

### Worker (worker/.env)

S3_BUCKET=seu-bucket-s3
SQS_URL=[https://sqs.us-east-1.amazonaws.com/123456789012/dspn-projeto-queue](https://sqs.us-east-1.amazonaws.com/123456789012/dspn-projeto-queue)
DYNAMO_TABLE=dspn-projeto-dynamo-logs
AWS_REGION=us-east-1


--

# 🚀 Guia de Implantação e Execução
## 1. Provisionamento Automático na AWS (Launch Templates)
Os scripts na pasta launch templates/ são executados no UserData das instâncias EC2:

Backend (launch templates/backend.sh):

* Atualiza o SO Debian/Ubuntu e instala python3-pip, python3-venv, nginx, git, awscli e fonts-dejavu-core.

* Clona o repositório em /opt/app, cria o ambiente virtual e instala requirements.txt.

* Configura o serviço no systemd (backend.service).

* Ajusta o Nginx na porta 80 como reverse proxy para o Uvicorn na porta 8000, deixando ativa a rota /health para o Load Balancer.

Worker (launch templates/worker.sh):

* Clona o código em /opt/worker, cria o ambiente virtual e instala as dependências.

* Cria e ativa o serviço worker.service no systemd para escutar a fila SQS continuamente.
  
## 2. Automação de Deploys (scripts/)
* Deploy do Frontend para o S3:
  ./scripts/deploy-frontend.sh <DNS-DO-ALB> <NOME-DO-BUCKET-FRONTEND>

Injeta a URL do ALB na variável VITE_API_URL, compila os arquivos do React e sincroniza com o bucket S3.

* Deploy do Backend na EC2:
  ./scripts/deploy-backend.sh <IP_DA_EC2>
  
Conecta via SSH na instância, executa git pull, atualiza dependências do Python e reinicia o serviço no systemd.

## 3. Execução Local para Desenvolvimento Backend (FastAPI)

* 1. Acesse o diretório do backend e crie o ambiente virtual:
  cd backend
  python -m venv venv
  source venv/bin/activate  # Windows: venv\Scripts\activate
* 2. Instale as dependências:
  pip install -r requirements.txt
* 3. Instale o pacote de fontes para geração de PDFs (Linux):
  sudo apt-get install -y fonts-dejavu-core
* 4. Popule o banco e o bucket S3 (opcional):
  python -m app.seed
* 5. Inicie a API:
  uvicorn app.main:app --reload --port 8000

Worker (Redimensionador de Imagens)

* 1. Em um novo terminal, acesse a pasta do worker:
  cd worker
  pip install -r requirements.txt

* 2. Inicie o worker:
  python worker.py

Frontend (React + TypeScript)

* 1. Acesse a pasta do frontend e instale as dependências Node:
  cd frontend
  npm install
* 2. Inicie o servidor local:
  npm run dev
* 3. Rotas de acesso:
  Bilheteria Pública: http://localhost:5173/
  Painel Administrativo: http://localhost:5173/#/admin

# 🧪 Testes e Validações
## Teste de Fumaça (Smoke Test)

* Para validar o fluxo de ponta a ponta usando instâncias locais do PostgreSQL e Redis (com mocks automatizados das chamadas da AWS):

cd backend
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres \
REDIS_URL=redis://localhost:6379 \
python test_app.py

## Validação do Auto Scaling:

1. Acesse o painel admin em /#/admin.

2. Clique na aba "Stress de CPU".

3. Defina a duração (ex: 180 segundos) e clique em "Gerar carga".

4. O backend ocupará 100% de uso de vCPU, permitindo acompanhar o aumento do tráfego nos alarmes do CloudWatch e o acionamento de novas instâncias EC2 pelo Auto Scaling Group.


  
