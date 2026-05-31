# Apresentação — conceitos e lições aprendidas

Deck em [Marp](https://marp.app/) (Markdown → slides). Fonte única: `slides.md`.
Sem dependências instaladas no repo — roda via `npx`.

## Pré-visualizar (VS Code)

Instale a extensão **Marp for VS Code** (`marp-team.marp-vscode`) e abra `slides.md`.
O preview lateral atualiza ao salvar.

## Exportar

Requer Node.js. Os comandos baixam o `marp-cli` sob demanda (não instala no projeto):

```bash
# HTML (auto-contido, bom para apresentar no navegador)
npx --yes @marp-team/marp-cli@latest apresentacao/slides.md -o apresentacao/slides.html

# PDF
npx --yes @marp-team/marp-cli@latest apresentacao/slides.md --pdf -o apresentacao/slides.pdf

# PPTX (se precisar editar no PowerPoint)
npx --yes @marp-team/marp-cli@latest apresentacao/slides.md --pptx -o apresentacao/slides.pptx
```

Modo apresentador / servidor com hot-reload:

```bash
npx --yes @marp-team/marp-cli@latest -s apresentacao/
```

## Diagrama do grafo

Todos os diagramas vêm de arquivos `.mmd` e são renderizados por
`bash apresentacao/gerar-diagramas.sh`:

- `grafo.svg` (visão geral) e `grafo-foco-*.svg` (walkthrough, um nó destacado por
  slide) — derivam de `grafo.mmd`, topologia fiel ao `agent.get_graph().draw_mermaid()`
  do agente compilado.
- `arquitetura.svg` — diagrama de componentes (estrutura).
- `ciclo-chat.svg` — diagrama de sequência do `/chat` com HITL (condensado de
  `../docs/sequencia.md`).
- `hook-after-model.svg` / `hook-wrap-tool-call.svg` — comparação dos pontos de bloqueio.

```bash
bash apresentacao/gerar-diagramas.sh
```

Os `.svg` são versionados para o deck abrir sem depender do mermaid-cli. Se a fiação do
agente mudar, atualize o `.mmd` correspondente (o `grafo.mmd` contra `draw_mermaid()`)
e rode o script de novo.

## Convenções

- Um slide por bloco separado por `---`.
- O tema (sóbrio: fundo branco, acento azul-escuro, monoespaçada para código) está
  embutido no bloco `<style>` no topo de `slides.md` — sem arquivo de tema externo.
- Saídas geradas (`slides.html`, `slides.pdf`, `slides.pptx`) não precisam ser
  versionadas.
