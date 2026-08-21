# Changelog

Todas as alterações relevantes do SupTrace estão documentadas neste arquivo.

## [1.3] - 2026-08-21

### Adicionado

- Gravação de múltiplas abas simultaneamente, incluindo abas abertas via Ctrl+T, links e pop-ups.
- Cada aba gera um vídeo individual no pacote final, nomeado sequencialmente (`_aba1`, `_aba2`...).
- Barra de progresso determinística com percentual exato e descrição da etapa atual durante o processamento.
- Timer de gravação em tempo real exibido na barra de status (`GRAVANDO — N abas | HH:MM:SS`).
- Indicador piscante na barra de status durante a gravação.
- Contador de abas abertas exibido no corpo da janela, atualizado em tempo real.
- Atalho de teclado `Esc` para encerrar a gravação.
- Tamanho do arquivo ZIP exibido no dialog de conclusão e na barra de status.
- Badge de versão visível no cabeçalho da aplicação.

### Melhorado

- Vídeos de múltiplas abas processados em paralelo, reduzindo o tempo total de processamento.
- Resolução de gravação fixada em 1920×1080, eliminando re-encode em monitores 1440p e 4K.
- Relatório HAR processado em paralelo com o encerramento do navegador.
- Geração do HTML do relatório otimizada para sessões com grande volume de requisições.

### Removido

- Barra de progresso indeterminada (spinner) substituída por barra determinística com percentual real.

---

## [1.2] - 2026-08-18

### Adicionado

- Janela de processamento dedicada com barra de progresso.
- Processamento paralelo do vídeo e do relatório HTML.
- Limpeza automática de arquivos temporários órfãos.

### Melhorado

- Processamento rápido do vídeo utilizando `-itsscale` e `-c:v copy`.
- Redução do tempo de processamento.
- Maior tolerância à remoção de arquivos temporariamente bloqueados.

### Corrigido

- Problemas de permissão relacionados ao uso do diretório temporário.
- Localização do FFmpeg quando a aplicação é executada como `.exe`.

---

## [1.1] - 2026-08-17

### Adicionado

- Suporte ao Google Chrome e ao Microsoft Edge.
- Detecção automática do navegador disponível.
- Indicador visual do navegador selecionado.

### Removido

- Download automático do Chromium.

---

## [1.0] - 2026-08-15

- Versão inicial do SupTrace.
```
