# Postiz local

1. Instale o **Docker Desktop** (Windows 11 usa WSL2; reinicie se pedir). Confira: `docker --version`.
2. Nesta pasta: `docker compose up -d`. Aguarde ~2 min; abra http://localhost:4007 e crie sua conta.
3. Depois de criar a conta, ponha `DISABLE_REGISTRATION: 'true'` no compose e rode `docker compose up -d` de novo.
4. **Facebook** (precisa de um app na Meta):
   - developers.facebook.com > Criar app (tipo Empresa) > adicionar o produto **Login do Facebook para Empresas**.
   - URI de redirecionamento OAuth: `http://localhost:4007/integrations/social/facebook`.
   - Permissoes usadas pelo Postiz: `pages_show_list`, `business_management`, `pages_manage_posts`, `pages_manage_engagement`, `pages_read_engagement`, `read_insights`, `publish_video`. Em modo de desenvolvimento valem so para contas com funcao no app (voce); publicar para o publico exige App Review.
   - Copie o ID e a chave secreta do app para `FACEBOOK_APP_ID` / `FACEBOOK_APP_SECRET` no `.env` e rode `docker compose up -d`.
   - No Postiz: **Add Channel > Facebook** e escolha a Pagina.
5. API: Postiz > Settings > Developers > Public API -> copie a chave e, no PowerShell:
   ```
   $env:POSTIZ_API_KEY = "..."; $env:POSTIZ_URL = "http://localhost:4007/api/public/v1"
   .venv\Scripts\python.exe -I publish.py --list-integrations
   .venv\Scripts\python.exe -I publish.py --mode draft --yes        # 1o teste: cria rascunho, nao publica
   ```

`docker compose down` para; `docker compose down -v` apaga todos os dados. Nao coloque `.env` em lugar publico.
