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

[ Espectador / Admin ]
                             │
                             ▼
          ┌──────────────────────────────────────┐
          │      Amazon S3 Static Website        │ (Hospedagem Frontend)
          └──────────────────┬───────────────────┘
                             │ (Requisições HTTP/API)
                             ▼
          ┌──────────────────────────────────────┐
          │   Application Load Balancer (ALB)    │ (Public Subnet)
          └──────────────────┬───────────────────┘
                             │
                             ▼
          ┌──────────────────────────────────────┐
          │ Auto Scaling Group (FastAPI + Nginx) │ (Public Subnet)
          └────┬─────────────┬─────────────┬─────┘
               │             │             │

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
