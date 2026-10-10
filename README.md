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
