# SupTrace

> Ferramenta interna para otimizar a análise de falhas no suporte e o reporte de erros para a P&D.

Com apenas dois cliques, o usuário reproduz o problema em um navegador controlado pelo SupTrace, que automaticamente:

- 🎥 **Grava a tela** durante todo o teste (vídeo `.webm`, acelerado em 1.5×);
- 📡 **Captura todas as chamadas de API** feitas pelo navegador (arquivo `.har`);
- 📋 **Gera um relatório HTML interativo** a partir do HAR, com endpoints, métodos HTTP, status, headers, payloads, respostas completas e tempos de resposta — filtrável diretamente no navegador;
- 📦 **Compacta tudo em um único `.zip`**, salvo em `C:\Temp`, pronto para ser enviado à equipe técnica.

O objetivo é eliminar a necessidade de solicitar prints, acesso remoto ou orientações de F12 ao usuário para diagnosticar se uma falha está na aplicação, na integração ou na infraestrutura.

---

## Novidades da v1.2

| # | Mudança |
|---|---|
| ✅ | **Fast path FFmpeg**: aceleração de vídeo via `-itsscale` + `-c:v copy` — nenhum frame é decodificado ou reencodado |
| ✅ | **Tempo de processamento drasticamente reduzido**: ~23 s → **< 3 s** no caso comum (sem reescala de resolução) |
| ✅ | **Análise de container otimizada**: `-probesize` e `-analyzeduration` reduzidos (5 MB / 5 s → 500 KB / 0,1 s) |
| ✅ | **Slow path mais rápido**: quando reescala é necessária, usa VP8 `realtime` + `cpu-used 8` em vez do preset padrão |
| ✅ | **Early return**: sem processamento algum quando velocidade = 1,0× e resolução já está no alvo |

---

## Novidades da v1.2

| # | Mudança |
|---|---|
| ✅ | **Janela de processamento dedicada** com barra de progresso e aviso em vermelho — impossível não perceber que o app está trabalhando |
| ✅ | **Bloqueio de fechamento durante o processamento** — fechar a janela enquanto o pacote é gerado exibe aviso e impede a perda dos arquivos |
| ✅ | **Pasta temporária fixa** em `%LOCALAPPDATA%\SupTrace\tmp` — evita erros de permissão causados pelo UAC resolvendo `%TEMP%` para caminhos incorretos |
| ✅ | **Processamento paralelo**: vídeo e relatório HTML gerados simultaneamente (antes era sequencial) |
| ✅ | **ZIP sem recompressão do `.webm`** — formato já comprimido; recomprimir só desperdiçava CPU |
| ✅ | **Limpeza automática de temporários órfãos** na inicialização — evita acúmulo de lixo de execuções anteriores interrompidas |
| ✅ | **Remoção de diretórios com tentativas repetidas** (`_safe_rmtree`) — tolerância a arquivos temporariamente travados por antivírus ou pelo próprio ffmpeg |

---

## Novidades da v1.1

| # | Mudança |
|---|---|
| ✅ | Utiliza o **Google Chrome** ou **Microsoft Edge** instalado na máquina — sem downloads externos |
| ✅ | **Detecção automática** de navegador: prioriza Chrome, usa Edge como fallback |
| ✅ | **Badge visual** no header indicando qual navegador foi detectado |
| ✅ | **Alerta e bloqueio automático** se nenhum navegador compatível for encontrado |
| ✅ | **Correção do erro de ffmpeg** no executável `.exe`: o binário do `imageio-ffmpeg` é copiado automaticamente para o diretório esperado pelo Playwright na primeira execução |
| 🗑️ | Removido o download automático do Chromium e a barra de progresso associada |

---

## Como funciona

1. O usuário abre o SupTrace — a ferramenta detecta automaticamente o navegador disponível (Chrome ou Edge) e exibe no header.
2. Ao clicar em **"Iniciar Gravação"**, o navegador detectado é aberto via [Playwright](https://playwright.dev/) em modo anônimo, com gravação de vídeo e captura de rede (HAR) já ativas.
3. O usuário reproduz o problema normalmente nesse navegador.
4. Ao clicar em **"Salvar e Fechar"**, a ferramenta:
   - encerra o navegador e finaliza a captura;
   - exibe uma **janela de processamento** com barra de progresso enquanto trabalha;
   - acelera o vídeo via manipulação de timestamps (sem decode/encode — operação de I/O puro);
   - converte o `.har` em um relatório HTML navegável, com abas por requisição (headers, query params, payload, response headers e body) — em paralelo ao vídeo;
   - compacta vídeo + relatório em um único `.zip` nomeado com data/hora, salvo em `C:\Temp`.
5. A janela de processamento desaparece e uma notificação confirma o arquivo gerado.

> ⚠️ **Não feche o aplicativo enquanto a janela de processamento estiver visível** — os arquivos serão perdidos. O próprio app impede o fechamento acidental e exibe um aviso caso você tente.

---

## Requisitos

- **Windows 10** ou superior;
- **Google Chrome** ou **Microsoft Edge** instalado na máquina;
- **Python 3.10+** para execução em modo desenvolvimento;
- Dependências Python listadas em [`requirements.txt`](./requirements.txt).

> ⚠️ O SupTrace é exclusivo para Windows — utiliza APIs nativas do sistema para elevação de privilégio (UAC) e para abertura de pastas.

---

## Instalação (modo desenvolvimento)

```bash
git clone https://github.com/dellagnolojoao/SupTrace.git
cd SupTrace
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python suptrace.py
```

> ℹ️ O script solicita elevação de privilégio (UAC) ao iniciar, reabrindo-se como administrador.  
> Isso evita problemas de permissão na execução (gravação de tela, escrita em `C:\Temp`) nos diferentes ambientes dos usuários finais.

---

## Gerando o executável (.exe)

O projeto é distribuído como executável único via [PyInstaller](https://pyinstaller.org/):

```bash
pyinstaller --onefile --windowed --uac-admin --name SupTrace ^
  --collect-all playwright ^
  --collect-all imageio_ffmpeg ^
  suptrace.py
```

| Flag | Motivo |
|---|---|
| `--onefile` | Gera um único `.exe` portátil |
| `--windowed` | Suprime o console cmd ao executar |
| `--uac-admin` | Solicita elevação UAC nativamente pelo manifesto do Windows |
| `--collect-all playwright` | Embarca o driver do Playwright para comunicação com Chrome/Edge |
| `--collect-all imageio_ffmpeg` | Embarca o binário do ffmpeg para aceleração do vídeo |

> ℹ️ **Sobre o ffmpeg no `.exe`:** na primeira execução, o SupTrace copia automaticamente o binário do `imageio-ffmpeg` para `%LOCALAPPDATA%\SupTrace\pw-browsers\ffmpeg-{revision}\`, que é o diretório esperado pelo Playwright. A partir da segunda execução, o binário já estará em cache e nenhuma cópia adicional é feita.

---

## Estrutura do projeto

```
SupTrace/
├── suptrace.py       # Aplicação principal (UI Tkinter + captura + relatório)
├── requirements.txt  # Dependências Python
├── .gitignore
└── README.md
```

---

## Saída gerada

Cada gravação produz em `C:\Temp`:

```
<DDMMYYYY-HHMMSS>.zip
├── <timestamp>_relatorio.html      # Relatório interativo de rede (HAR → HTML)
└── <timestamp>_video_1.5x.webm    # Gravação da tela acelerada
```

O relatório HTML contém, por requisição:

- Método HTTP e endpoint;
- URL completa;
- Status de retorno;
- Headers de requisição e resposta;
- Query params;
- Payload enviado;
- Response body completo (truncado em 10.000 caracteres);
- Tempo de resposta em ms;
- Horário da requisição.

Tudo filtrável por texto em tempo real, sem precisar abrir nenhum arquivo externo.

---

## Privacidade

O SupTrace roda **100% localmente** na máquina do usuário: a gravação de tela, a captura de rede e a geração do relatório acontecem no próprio computador, e o `.zip` resultante fica em `C:\Temp` até ser enviado manualmente à equipe técnica.

> ⚠️ O relatório gerado pode conter informações sensíveis, como tokens de autenticação, cookies, payloads e dados exibidos na tela durante o teste. Revise o conteúdo antes de compartilhar externamente.

Nenhum dado é enviado a servidores externos pela ferramenta.

---

## Releases

| Versão | Data | Destaques |
|---|---|---|
| [v1.2](https://github.com/dellagnolojoao/SupTrace/releases/tag/SupTrace_v1.2) | 2026-08-18 | FFmpeg fast path (`-itsscale` + `-c:v copy`): processamento ~23 s → < 3 s | Janela de processamento, bloqueio de fechamento, fix TEMP/UAC, processamento paralelo |
| [v1.1](https://github.com/dellagnolojoao/SupTrace/releases/tag/SupTrace_v1.1) | 2026-08-17 | Chrome/Edge homologado, detecção automática de navegador, fix ffmpeg no `.exe` |
| [v1.0](https://github.com/dellagnolojoao/SupTrace/releases/tag/SupTrace_v1.0) | — | Versão inicial com Chromium via download automático |

---

## Contribuindo

Sugestões, dúvidas e contribuições sobre o código são bem-vindas — abra uma [*issue*](../../issues) ou um [*pull request*](../../pulls).
