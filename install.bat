@echo off
setlocal enabledelayedexpansion

echo.
echo  ClaudeBoost Installer
echo  =====================
echo.
echo  This installs ClaudeBoost extensions globally so every project
echo  has access to agents, knowledge bases, RAG search, and slash commands.
echo.

:: Get the directory where this script lives (ClaudeBoost root)
set "BOOST_DIR=%~dp0"
set "BOOST_DIR=%BOOST_DIR:~0,-1%"

:: Target directories
set "CLAUDE_DIR=%USERPROFILE%\.claude"
set "GT_DIR=%USERPROFILE%\gt"

echo  Source:  %BOOST_DIR%
echo  Target:  %CLAUDE_DIR%
echo.

:: ============================================================
:: 1. Register RAG MCP server globally
:: ============================================================
echo  [1/4] Registering RAG MCP server...

python -c "import rag_server" >nul 2>&1
if errorlevel 1 (
    echo         Installing rag-server package...
    call pip install -e "%BOOST_DIR%\mcp-rag-server" >nul 2>&1
    if errorlevel 1 (
        echo         WARNING: Could not install rag-server. Install manually:
        echo           pip install -e "%BOOST_DIR%\mcp-rag-server"
    ) else (
        echo         rag-server package installed.
    )
) else (
    echo         rag-server already installed.
)

where claude >nul 2>&1
if not errorlevel 1 (
    call claude mcp remove rag-server --scope user >nul 2>&1
    call claude mcp add rag-server --scope user -e RAG_PROJECT_ROOT="%BOOST_DIR%" -- python -m rag_server >nul 2>&1
    echo         MCP server registered globally (RAG_PROJECT_ROOT=%BOOST_DIR%).
) else (
    echo         Claude CLI not found. Add manually to ~/.claude.json:
    echo           "mcpServers": { "rag-server": { "command": "python", "args": ["-m", "rag_server"], "env": { "RAG_PROJECT_ROOT": "%BOOST_DIR%" } } }
)

:: ============================================================
:: 2. Copy slash commands globally
:: ============================================================
:: Copy CLAUDE.md globally
copy /y "%BOOST_DIR%\CLAUDE.md" "%CLAUDE_DIR%\CLAUDE.md" >nul 2>&1
echo         CLAUDE.md copied to %CLAUDE_DIR%\CLAUDE.md

echo  [2/4] Installing slash commands...

if not exist "%CLAUDE_DIR%\commands" mkdir "%CLAUDE_DIR%\commands"

set "CMD_COUNT=0"
for %%f in ("%BOOST_DIR%\.claude\commands\*.md") do (
    copy /y "%%f" "%CLAUDE_DIR%\commands\" >nul 2>&1
    set /a CMD_COUNT+=1
)
echo         !CMD_COUNT! commands installed.

:: ============================================================
:: 3. Copy agents and knowledge to GT directives (if GT installed)
:: ============================================================
echo  [3/4] Setting up GT directives...

if exist "%GT_DIR%" (
    if not exist "%GT_DIR%\directives\agents" mkdir "%GT_DIR%\directives\agents"
    if not exist "%GT_DIR%\directives\knowledge" mkdir "%GT_DIR%\directives\knowledge"

    xcopy /y /q "%BOOST_DIR%\agents\*" "%GT_DIR%\directives\agents\" >nul 2>&1
    xcopy /y /q "%BOOST_DIR%\knowledge\*" "%GT_DIR%\directives\knowledge\" >nul 2>&1
    echo         Agents and knowledge copied to GT directives.
) else (
    echo         GT not installed. Skipping GT directives.
    echo         Agents and knowledge are still available locally in ClaudeBoost.
)

:: ============================================================
:: 4. Initial RAG index
:: ============================================================
echo  [4/4] Building initial RAG index...

set "RAG_PROJECT_ROOT=%BOOST_DIR%"
python -c "from rag_server.core.embedding import SentenceTransformerEmbedding; from rag_server.core.store import ChromaStore; from rag_server.indexing.engine import IndexingEngine; from rag_server.config import CHROMA_DIR; e=SentenceTransformerEmbedding(); s=ChromaStore(str(CHROMA_DIR)); eng=IndexingEngine(e,s); r=eng.index_all(force=True); print(f'Indexed {r[\"files_indexed\"]} files, {r[\"chunks_created\"]} chunks')" 2>&1
if errorlevel 1 (
    echo         Skipped. Run rag_index from Claude Code to index later.
) else (
    echo         Index built successfully.
)

echo.
echo  ============================================================
echo   ClaudeBoost installed!
echo.
echo   What's available now:
echo     - RAG search in every Claude Code session
echo     - !CMD_COUNT! slash commands (global)
if exist "%GT_DIR%" (
    echo     - Agents and knowledge in GT directives
)
echo.
echo   To verify: open any project in Claude Code and try:
echo     rag_status
echo  ============================================================
echo.

endlocal\r
