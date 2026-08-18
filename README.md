```markdown
# SupTrace

> Ferramenta interna para otimizar a análise de falhas no suporte e o reporte de erros para a equipe de P&D.

O SupTrace permite que o usuário reproduza um problema em um navegador controlado pela aplicação. Durante o teste, a ferramenta captura automaticamente as informações necessárias para a investigação técnica.

Ao final, é gerado um único arquivo `.zip` contendo:

- 🎥 Gravação do teste em vídeo `.webm`;
- 📡 Captura das chamadas de rede;
- 📋 Relatório HTML interativo das requisições realizadas;
- 📦 Pacote compactado pronto para ser enviado à equipe técnica.

O objetivo é reduzir a necessidade de solicitar prints, acesso remoto ou instruções para abertura das ferramentas de desenvolvedor do navegador.

---

## Principais recursos

- Utilização do **Google Chrome** ou **Microsoft Edge** instalado na máquina;
- Detecção automática do navegador disponível;
- Gravação do navegador durante a reprodução do problema;
- Captura das requisições de rede realizadas durante o teste;
- Geração de relatório HTML navegável a partir do arquivo HAR;
- Aceleração do vídeo final para 1,5×;
- Processamento paralelo do vídeo e do relatório;
- Geração automática de um arquivo `.zip`;
- Execução totalmente local, sem envio automático de dados para servidores externos.

---

## Como funciona

1. O usuário abre o SupTrace.
2. A aplicação detecta automaticamente o Google Chrome ou o Microsoft Edge disponível.
3. O usuário clica em **Iniciar Gravação**.
4. O navegador é aberto via [Playwright](https://playwright.dev/), em modo anônimo, com gravação de vídeo e captura de rede habilitadas.
5. O usuário reproduz o problema normalmente.
6. Ao clicar em **Salvar e Fechar**, o SupTrace:
   - encerra o navegador;
   - finaliza a captura de vídeo e das requisições;
   - processa o vídeo;
   - gera o relatório HTML a partir do arquivo HAR;
   - compacta os arquivos em um único `.zip`;
   - salva o pacote em `C:\Temp`.

> ⚠️ Não feche o aplicativo enquanto a janela de processamento estiver visível. O SupTrace bloqueia o fechamento durante essa etapa para evitar a perda dos arquivos.

---

## Requisitos

- Windows 10 ou superior;
- Google Chrome ou Microsoft Edge instalado;
- Python 3.10 ou superior para execução em modo de desenvolvimento;
- Dependências listadas em [`requirements.txt`](./requirements.txt).

> O SupTrace é exclusivo para Windows, pois utiliza recursos nativos do sistema para elevação de privilégio via UAC e abertura de pastas.

---

## Instalação e execução

Clone o repositório:

```bash
git clone https://github.com/dellagnolojoao/SupTrace.git
cd SupTrace
```

Crie e ative um ambiente virtual:

```bash
python -m venv venv
venv\Scripts\activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

Execute a aplicação:

```bash
python suptrace.py
```

> O aplicativo pode solicitar elevação de privilégio via UAC ao iniciar. Essa elevação é necessária para evitar problemas de permissão relacionados à gravação e à criação dos arquivos temporários.

---

## Geração do executável

O SupTrace pode ser distribuído como um executável único utilizando [PyInstaller](https://pyinstaller.org/):

```bash
pyinstaller --onefile --windowed --uac-admin --name SupTrace ^
  --collect-all playwright ^
  --collect-all imageio_ffmpeg ^
  suptrace.py
```

O executável será gerado no diretório `dist`.

### Parâmetros utilizados

| Parâmetro | Descrição |
|---|---|
| `--onefile` | Gera um único arquivo `.exe` |
| `--windowed` | Executa sem exibir uma janela de terminal |
| `--uac-admin` | Solicita elevação via UAC no manifesto do Windows |
| `--collect-all playwright` | Inclui os arquivos necessários do Playwright |
| `--collect-all imageio_ffmpeg` | Inclui o binário do FFmpeg utilizado no processamento do vídeo |

### Cache do FFmpeg

Na primeira execução, o SupTrace copia automaticamente o binário do `imageio-ffmpeg` para o diretório esperado pelo Playwright:

```text
%LOCALAPPDATA%\SupTrace\pw-browsers\ffmpeg-{revision}\
```

Nas execuções seguintes, o binário já estará disponível em cache.

---

## Arquivos gerados

Os pacotes são salvos no diretório:

```text
C:\Temp
```

Exemplo de estrutura do arquivo gerado:

```text
26082026-161530.zip
├── 26082026-161530_relatorio.html
└── 26082026-161530_video_1.5x.webm
```

### Relatório HTML

O relatório apresenta informações detalhadas sobre cada requisição capturada, incluindo:

- Método HTTP;
- URL completa;
- Endpoint;
- Status da resposta;
- Headers da requisição e da resposta;
- Query parameters;
- Payload enviado;
- Corpo da resposta;
- Tempo de resposta;
- Horário da requisição.

As requisições podem ser filtradas diretamente no navegador.

---

## Privacidade e segurança

O SupTrace executa o processamento localmente na máquina do usuário:

- A gravação é realizada localmente;
- A captura de rede é realizada localmente;
- O relatório HTML é gerado localmente;
- O arquivo `.zip` permanece em `C:\Temp` até ser enviado manualmente.

A aplicação não envia automaticamente dados para servidores externos.

> ⚠️ O material gerado pode conter informações sensíveis, como tokens de autenticação, cookies, payloads, dados de clientes e informações exibidas na tela. Revise os arquivos antes de compartilhá-los.

---

## Histórico de versões

O histórico detalhado de alterações está disponível no arquivo [`CHANGELOG.md`](./CHANGELOG.md).

As versões publicadas, seus arquivos e respectivos detalhes também podem ser consultados na página de [Releases](https://github.com/dellagnolojoao/SupTrace/releases).

### Versão atual

- [v1.2](https://github.com/dellagnolojoao/SupTrace/releases/tag/SupTrace_v1.2)

---

## Estrutura do projeto

```text
SupTrace/
├── suptrace.py       # Aplicação principal
├── requirements.txt  # Dependências Python
├── CHANGELOG.md      # Histórico de alterações
├── .gitignore
└── README.md
```

---

## Contribuindo

Sugestões, dúvidas e contribuições são bem-vindas.

- Abra uma [issue](../../issues) para relatar problemas ou sugerir melhorias;
- Envie um [pull request](../../pulls) com alterações no projeto.
```
