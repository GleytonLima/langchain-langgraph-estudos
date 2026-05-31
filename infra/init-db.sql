-- Cria os bancos usados pelo stack. langfuse para observabilidade, chassi para
-- sessoes do chassi + checkpoints do LangGraph (PostgresSaver dos agentes).
CREATE DATABASE langfuse;
CREATE DATABASE chassi;
