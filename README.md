# SupTrace

Ferramenta interna para otimizar a análise de falhas no suporte e o reporte de erros para a P&D.

Com apenas dois cliques, o usuário reproduz o problema em um navegador controlado pela ferramenta e o SupTrace:

- **Grava a tela** durante todo o teste (vídeo `.webm`, acelerado em 1.5×);
- **Captura todas as chamadas de API** feitas pelo navegador (arquivo `.har`);
- **Gera um relatório HTML interativo** a partir do HAR, com endpoints, métodos HTTP, status, headers, payloads, respostas completas e tempos de resposta — filtrável diretamente no navegador;
- **Compacta tudo em um único `.zip`**, salvo em `C:\Temp`, pronto para ser enviado à equipe técnica.

O objetivo é eliminar a necessidade de solicitar prints, acesso remoto ou orientações de F12 ao usuário para diagnosticar se uma falha está na aplicação, na integração ou na infraestrutura.

## Como funciona

1. O usuário abre o SupTrace e clica em **"Iniciar Gravação"**.
2. Um navegador Chromium (via [Playwright](https://playwright.dev/)) é aberto em modo anônimo, já com gravação de vídeo e captura de rede (HAR) ativas.
3. O usuário reproduz o problema normalmente nesse navegador.
4. Ao clicar em **"Salvar e Fechar"**, a ferramenta:
   - acelera e normaliza o vídeo (via `ffmpeg`, através do `imageio-ffmpeg`);
   - converte o `.har` em um relatório HTML navegável, com abas por requisição (headers, query params, payload, response headers/body);
   - compacta vídeo + relatório em um único `.zip` nomeado com data/hora, salvo em `C:\Temp`.

## Requisitos

- Windows (a ferramenta usa APIs do Windows para elevação de privilégio e para abrir a pasta de destino).
- Python 3.10+ (testado com `str | None`, sintaxe de union types).
- Dependências Python listadas em [`requirements.txt`](./requirements.txt).
- Navegador Chromium do Playwright (baixado automaticamente na primeira execução, com barra de progresso na própria interface).

## Instalação (modo desenvolvimento)

```bash
git clone https://github.com/dellagnolojoao/SupTrace.git
cd SupTrace
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python suptrace.py
```

Na primeira execução, o SupTrace baixa automaticamente o Chromium necessário (via Playwright) para a pasta `%LOCALAPPDATA%\SupTrace\browsers`.

> ℹ️ O script solicita elevação de privilégio (UAC) ao iniciar (`_elevar()`), reabrindo-se como administrador. Isso evita problemas de permissão na execução (gravação de tela, escrita em `C:\Temp`, instalação do Chromium etc.) nos diferentes ambientes dos usuários finais.

## Gerando o executável (.exe)

O projeto foi desenhado para ser distribuído como executável único via [PyInstaller](https://pyinstaller.org/):

```bash
pyinstaller --onefile --windowed --uac-admin --name SupTrace \
    --collect-all playwright --collect-all imageio_ffmpeg suptrace.py
```

O flag `--uac-admin` garante que o `.exe` já solicite elevação nativamente pelo manifesto do Windows, e os `--collect-all` garantem que o driver do Playwright e o binário do `ffmpeg` sejam embarcados corretamente.

## Estrutura do projeto

```
SupTrace/
├── suptrace.py       # Aplicação principal (UI Tkinter + captura + geração de relatório)
├── requirements.txt  # Dependências Python
├── .gitignore
└── README.md
```

## Saída gerada

Cada gravação produz, em `C:\Temp`:

```
<DDMMYYYY-HHMMSS>.zip
├── <timestamp>_relatorio.html   # Relatório interativo de rede (HAR → HTML)
└── <timestamp>_video[_1.5x].webm  # Gravação da tela
```

## Privacidade

O SupTrace roda 100% localmente na máquina do usuário: a gravação de tela, a captura de rede e a geração do relatório acontecem no próprio computador, e o `.zip` resultante fica em `C:\Temp` até ser enviado manualmente à equipe técnica. Nenhum dado é enviado a servidores externos pela ferramenta em si.

## Contribuindo

Sugestões, dúvidas e contribuições sobre o código são bem-vindas — abra uma *issue* ou um *pull request*.
