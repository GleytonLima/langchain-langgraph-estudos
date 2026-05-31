#!/usr/bin/env bash
# Gera os diagramas do deck a partir de grafo.mmd (fonte única, topologia fiel ao
# agent.get_graph().draw_mermaid()):
#   - grafo.svg                 : visão geral
#   - grafo-foco-<no>.svg       : mesma topologia com um nó destacado (walkthrough)
#
# Requer Node. Roda o mermaid-cli via npx (não instala no projeto).
set -eu
cd "$(dirname "$0")"

MMDC="npx --yes @mermaid-js/mermaid-cli@latest"
RENDER_OPTS="-t neutral -b white"

# visão geral
$MMDC -i grafo.mmd -o grafo.svg $RENDER_OPTS

# diagramas avulsos (não derivam de grafo.mmd)
$MMDC -i react.mmd -o react.svg $RENDER_OPTS
$MMDC -i pregel.mmd -o pregel.svg $RENDER_OPTS
$MMDC -i camadas.mmd -o camadas.svg $RENDER_OPTS
$MMDC -i arquitetura.mmd -o arquitetura.svg $RENDER_OPTS
$MMDC -i ciclo-chat.mmd -o ciclo-chat.svg $RENDER_OPTS
$MMDC -i hook-after-model.mmd -o hook-after-model.svg $RENDER_OPTS
$MMDC -i hook-wrap-tool-call.mmd -o hook-wrap-tool-call.svg $RENDER_OPTS

# uma variante por nó, com o nó em foco destacado
for no in model P S H T tools; do
  f="grafo-foco-$no"
  cp grafo.mmd "$f.mmd"
  echo "  style $no fill:#fde68a,stroke:#0b3d59,stroke-width:3px,color:#1a1a1a" >> "$f.mmd"
  $MMDC -i "$f.mmd" -o "$f.svg" $RENDER_OPTS
  rm -f "$f.mmd"
done

echo "OK: grafo.svg + grafo-foco-{model,P,S,H,T,tools}.svg"
