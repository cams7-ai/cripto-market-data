# cripto-market-data

Biblioteca/CLI local para dados públicos Binance Spot, extraída na Sprint 06B. Python 3.13.15, uv 0.12.19, distribuição 0.1.0. Depende de `cripto-core==0.1.0`, HTTPX e Pydantic; não depende de bot, DuckDB, SDK AWS ou execução financeira.

## API

| Módulo | Contrato |
|---|---|
| `domain.market` | Candle/STEP/SCHEMA/PARSER, validação estrita de candles/metadata/quote/janelas e aliases dos helpers puros do core |
| `domain.settings` | MarketSettings com fonte, root/data_dir/fixture explícitos, BTCUSDT/15m e limites de páginas |
| `application.ports` | RawResponse, MarketSource e MarketStore, sem transporte/persistência concretos |
| `application.collect` | Progress e collect_market, paginação/qualidade/checkpoint por portas |
| `application.collection` | execute_collection com proveniência do consumidor e CollectionAdapters; único workflow para as CLIs |
| `adapters.binance` | PublicSource/Budget/guard e fixture_source com MockTransport |
| `adapters.storage` | SQLiteMarketStore v1 e export_market com `package_version` explícito |
| `adapters.config` | MarketInput compartilhado e load_config/market_settings; consumidor mantém seu envelope/módulos financeiros |
| `adapters.inspection` | Inspeção genérica de arquivos efetivamente carregados/RECORD; consumidor define versão/instalações aceitas |
| `adapters.provenance` | Identidade standalone de market-data/core, sem consultar código ou Git do bot |

A biblioteca não decide investimento, cria ordem, reserva capital ou altera ledger. Carteira/risco/backtest permanecem no bot. Seus imports legados são fachadas, não segunda implementação dos parsers/cliente/store.

## CLI com raiz explícita

Os comandos exigem `--root` absoluto/existente dentro de `/home/cams7/Dev/Cripto`. A raiz contém os dados permitidos, não precisa ser o repositório do pacote e nunca é derivada de site-packages. Paths relativos de fixture/data_dir resolvem a partir do cwd; symlinks/paths que escapem da raiz são rejeitados.

```bash
cd /home/cams7/Dev/Cripto/cripto-market-data
uv sync --locked --group dev --offline
uv run --locked --offline cripto-market-data check-config --root "$PWD" --config config/market.fixture.example.toml
uv run --locked --offline cripto-market-data collect-market --root "$PWD" --config config/market.fixture.example.toml --start 2026-10-01T00:00:00Z --end 2026-10-01T00:30:00Z
```

Primeira fixture insere dois candles; repetir insere zero. `check-config` valida sem criar banco/cliente/rede, inclusive se o arquivo fixture ainda não existir. O TOML aceita apenas modo PAPER e tabela market; extras financeiros/estratégicos são rejeitados. Credenciais Binance são proibidas, inclusive vazias; não lê .env. CRIPTO_BOT_MODE só admite PAPER; variáveis desconhecidas nesse namespace são rejeitadas. Não há namespace novo de overrides nem flags de estratégias.

Exit codes: 0 sucesso, 2 argumentos/configuração/opt-in/janela inválidos, 3 coleta incompleta/falha operacional, 1 falha interna. JSON no stdout, evento sanitizado no stderr, mesmo run_id, mode=PAPER/orders_sent=0. Ajuda é textual.

Fonte pública requer `--allow-network` explícito; fixture rejeita esse flag. Esta entrega não executa coleta real. Cliente mantém quatro GETs no host `https://data-api.binance.vision`, HTTPS/TLS, sem auth/proxies herdados/redirects ou endpoint arbitrário; BTCUSDT/15m. Budget monotônico 90 s, retry/429/418/not_before e limites de corpo/páginas preservados. API direta recebe settings validados, callbacks/adapters e autorização explícita; não presume permissão por instalação.

## Persistência e publicação

`market.sqlite3` v1 e `.writer.lock` continuam no data_dir escolhido. O mesmo diretório é compartilhável explicitamente com o bot, com um escritor por vez; não há cópia/migração automática. Bruto/candles/checkpoint são confirmados por página. Lacuna/conflito/ausência de progresso ou schema/corrupção incompatível falham sem reset. not_before cobre os datasets do mesmo banco, não todos os consumidores do IP.

Exportações atômicas incluem manifest.json e exatamente quatro arquivos em files: candles.jsonl.gz, raw.jsonl.gz, snapshots.json e provenance.json. Parser/schema e IDs fixture:<sha>:v1 / binance_public:https://data-api.binance.vision:v1 preservados. Hash de candles exclui relógios/proveniência. Falha de publicação preserva commits e pode ser recuperada por repetição/reexportação; não anunciar temporário como snapshot final.

`export_market(..., context, package_version=...)` recebe a identidade/versão do produtor. O bot fornece seus metadados; a CLI fornece produtor market-data, versão e hash de sua composição/core e data_root explícito, sem consultar Git do diretório dos dados. Inspeção de wheel exige inventário/RECORD coerente; editables só quando explicitamente aceitos pelo consumidor. CLI em desenvolvimento admite seu próprio editable validado; bot aceita market-data apenas por wheel. Core permanece wheel imutável 0.1.0.

## Build, testes e consumo

```bash
uv run --locked --offline ruff check .
uv run --locked --offline ruff format --check .
uv run --locked --offline mypy src
uv run --locked --offline pytest -q --cov=cripto_market_data --cov-branch
uv build --offline --out-dir dist/06b-final
```

Disponibilizar previamente o wheel core em `../cripto-core/dist/06a-final/cripto_core-0.1.0-py3-none-any.whl`. O bot consome o wheel market-data exato em `../cripto-market-data/dist/06b-final/cripto_market_data-0.1.0-py3-none-any.whl`. Locks são próprios; não substituir artefatos ou atualizar versões silenciosamente. Instalação com cache incompleto pode reutilizar distribuições verificadas da baseline conforme o guia, sem alegar cache frio validado.

Os testes standalone usam fixtures, MockTransport, clocks substituídos, processos com guard de sockets e casos de erro/rollback/lock/recuperação. Guias/evidências/compatibilidade e limites: [Sprint 06B](../docs/sprints/sprint-06b.md) e [validação](../docs/testes/sprint-06b-validacao.md). Nenhuma funcionalidade de 06C/06D, rede real ou operação privada é entregue aqui.
