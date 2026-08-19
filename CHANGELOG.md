# Changelog

Todas as alterações relevantes do SupTrace estão documentadas neste arquivo.

## [1.2] - 2026-08-18

### Adicionado

- Janela de processamento dedicada com barra de progresso.
- Processamento paralelo do vídeo e do relatório HTML.
- Limpeza automática de arquivos temporários órfãos.
- Detecção e utilização automática do Chrome ou Edge.

### Melhorado

- Processamento rápido do vídeo utilizando `-itsscale` e `-c:v copy`.
- Redução do tempo de processamento.
- Maior tolerância à remoção de arquivos temporariamente bloqueados.

### Corrigido

- Problemas de permissão relacionados ao uso do diretório temporário.
- Localização do FFmpeg quando a aplicação é executada como `.exe`.

## [1.1] - 2026-08-17

### Adicionado

- Suporte ao Google Chrome e ao Microsoft Edge.
- Detecção automática do navegador disponível.
- Indicador visual do navegador selecionado.

### Removido

- Download automático do Chromium.

## [1.0.0] - 2026-08-15

- Versão inicial do SupTrace.
