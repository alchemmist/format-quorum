CLANG_FORMAT     ?= clang-format
CLANG_FORMAT_CFG := backend/configs/clang-format

RUFF     ?= ruff
RUFF_CFG := backend/configs/ruff.toml

FILE_CPP ?= app/src/demo.cpp
FILE_PY  ?= app/src/demo.py

fmt-cpp: ## Print formatted C++ file (FILE_CPP=path override)
	$(CLANG_FORMAT) --style=file:$(CLANG_FORMAT_CFG) $(FILE_CPP)

fmt-py: ## Print formatted Python file (FILE_PY=path override)
	$(RUFF) format --config $(RUFF_CFG) --diff $(FILE_PY)
