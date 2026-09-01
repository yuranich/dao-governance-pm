DIAGRAM_DIR := diagrams
FIGURE_DIR  := figures

GRAPHVIZ_SOURCES := $(wildcard $(DIAGRAM_DIR)/*.dot)
GRAPHVIZ_SVGS := $(patsubst $(DIAGRAM_DIR)/%.dot,$(FIGURE_DIR)/%.svg,$(GRAPHVIZ_SOURCES))
GRAPHVIZ_PNGS := $(patsubst $(DIAGRAM_DIR)/%.dot,$(FIGURE_DIR)/%.png,$(GRAPHVIZ_SOURCES))

.PHONY: diagrams diagrams-svg diagrams-png check-diagrams check-graphviz

diagrams: diagrams-svg diagrams-png

diagrams-svg: check-graphviz $(GRAPHVIZ_SVGS)

diagrams-png: check-graphviz $(GRAPHVIZ_PNGS)

check-diagrams: check-graphviz
	@for source in $(GRAPHVIZ_SOURCES); do \
		dot -Tdot "$$source" -o /dev/null; \
	done
	@echo "Graphviz sources are valid."

check-graphviz:
	@command -v dot >/dev/null 2>&1 || { \
		echo "Graphviz is required. Install it with: brew install graphviz" >&2; \
		exit 1; \
	}

$(FIGURE_DIR)/%.svg: $(DIAGRAM_DIR)/%.dot | check-graphviz
	dot -Tsvg "$<" -o "$@"

$(FIGURE_DIR)/%.png: $(DIAGRAM_DIR)/%.dot | check-graphviz
	dot -Tpng "$<" -o "$@"
