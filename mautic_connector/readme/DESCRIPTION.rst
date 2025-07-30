Documentação Mautic - Connector Odoo

Este guia explica como configurar a integração entre Mautic e Odoo V14 usando o conector Odoo, incluindo soluções para limitações da API e o fluxo recomendado de importação de dados.

Configuração no Mautic
----------------------

1. Acesse **Configurações** - **Credenciais da API** - *Criar Credencial**
2. Preencha os seguintes campos:

   - **Nome**: ``Connect_Odoo``
   - **URL de redirecionamento**: Exemplo: ``http://localhost:14069/get_auth_code``
   - **ID do Cliente**: Será gerada automaticamente
   - **Senha do Cliente**: Será gerada automaticamente

Configuração no Odoo V14
------------------------

1. Acesse **Definições** - **Selecionar sua Empresa** - **Aba Mautic**
2. Preencha os seguintes campos:

   - **URL da API**: Exemplo: ``https://materiais2.falker.com.br/``
   - **ID do Cliente**: Copie da credencial gerada no Mautic
   - **Senha do Cliente**: Copie da credencial gerada no Mautic
   - **URL de Autorização**: Exemplo: ``https://materiais2.falker.com.br/oauth/v2/authorize``
   - **URL de Redirecionamento**: Exemplo: ``http://localhost:14069/get_auth_code``
   - **Código de Autenticação**: Será gerado após a autenticação
   - **Token de Acesso**: Será gerado após a autenticação

Fluxo de Importação de Dados
----------------------------

**Ordem de Importação (CRUCIAL):**

1. Empresas primeiro
2. Contatos depois

**Motivo:** Muitos contatos estão vinculados a empresas no Mautic. Esta ordem garante que:

- As relações empresa-contato sejam mantidas corretamente
- Evita erros de referência onde contatos referenciam empresas inexistentes
- Mantém a integridade dos dados no Odoo

**Processo de Importação:**

1. **Empresas:**

   - Cron Job roda a cada 1 minuto
   - Importa empresas uma por uma (limitação da API)
   - Cria/atualiza registros no Odoo

2. **Contatos:**

   - Executado após conclusão da importação de empresas
   - Importa todos os contatos de uma só vez
   - Associa automaticamente cada contato à empresa correspondente

Limitações da API e Soluções
----------------------------

**Empresas (Companies):**

- **Limitação:** API só permite criação individual
- **Solução:** Cron Job que processa uma empresa por vez

**Contatos (Contacts):**

- **Processamento:** Exportação em massa possível
- **Solução:** Cron Job para importação completa após empresas

Observações Importantes
-----------------------

1. **Ordem de Importação:** Fundamental seguir empresa- contatos
2. **Sincronização:** URLs de redirecionamento devem ser idênticas
3. **Autenticação:** Campos preenchidos automaticamente
4. **Monitoramento:**

   - Verifique logs dos Cron Jobs
   - Confira relações empresa-contato
   - Valide quantidade de registros importados
