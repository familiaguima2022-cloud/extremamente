# Checador de extremamente — versão online

Cole o link de um vídeo do YouTube e o app conta quantas vezes a palavra "extremamente" aparece, lista os horários (com link para conferir) e gera o texto pronto para copiar.

**Como funciona:** busca a legenda em português do vídeo (pelo serviço Supadata, plano gratuito) e conta a palavra nela. Se o vídeo não tiver legenda em português, o app avisa e não conta.

**Limites do plano gratuito:** cerca de 100 vídeos por mês (1 crédito por vídeo com legenda). Se você checar o mesmo vídeo de novo no mesmo dia, não gasta crédito.

**Arquivos:** só dois são necessários para publicar: `app.py` e `requirements.txt`.

---

## Passo a passo para publicar (uma vez só)

### 1. Pegar a chave do Supadata
1. Entre em **supadata.ai** e crie uma conta gratuita (não pede cartão).
2. No painel (dash.supadata.ai), copie a sua **API key**. Guarde, você vai usar no passo 3.

### 2. Colocar o projeto no GitHub
1. Entre em **github.com** e crie um repositório novo (nome sugerido: `checador-extremamente`). Pode ser **privado**.
2. Clique em **uploading an existing file**, arraste `app.py` e `requirements.txt` e clique em **Commit changes**.

### 3. Publicar no Streamlit Cloud
1. Entre em **share.streamlit.io** com a sua conta do GitHub.
2. Clique em **Create app** e escolha o repositório. Em **Main file path**, escreva `app.py`.
3. Abra **Advanced settings → Secrets** e cole (trocando pelos seus valores):
   ```
   SUPADATA_KEY = "cole-aqui-a-sua-chave"
   SENHA = "escolha-uma-senha"
   ```
4. Clique em **Deploy**. Em alguns minutos o app abre num endereço seu.

> A **SENHA** impede que outras pessoas usem o app e gastem os seus créditos. Nunca coloque a chave dentro do `app.py` nem no GitHub: ela fica só nos Secrets.

(Os nomes dos botões do Streamlit podem mudar um pouco com o tempo, mas o caminho é esse.)

---

## Uso

1. Abra o endereço do app e digite a senha.
2. Cole o link do vídeo e clique em **Checar**.
3. Copie o texto gerado e **confira os horários** pelos links antes de postar.

## Mensagens que podem aparecer

| Mensagem | O que fazer |
|---|---|
| "Esse vídeo não tem legenda disponível" | Não dá para checar online. Use a versão do computador, com Whisper. |
| "Esse vídeo não tem legenda em português" | Mesmo caso acima. |
| "Os créditos gratuitos deste mês acabaram" | Esperar o mês seguinte. |
| "Muitas consultas seguidas" | Esperar alguns segundos e tentar de novo. |
| "A chave do Supadata não foi aceita" | Conferir o `SUPADATA_KEY` nos Secrets. |

## Limitações

- As legendas automáticas do YouTube erram mais que o Whisper, e o horário vem **por frase** (o link abre alguns segundos antes da palavra).
- Quando a contagem precisar ser exata, use a versão do computador com Whisper.
